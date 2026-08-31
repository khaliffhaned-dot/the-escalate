"""
Weekly/periodic report scheduling.

Persistence honesty check, read this before assuming "weekly" means what
it sounds like:

- If NADI_USE_DB_STORE=true, schedule configs persist to Postgres
  (ReportScheduleDB) and a restart is fine, the scheduler loop just
  compares `next_run_at` to now for every stored row and catches up.
- If NADI_USE_DB_STORE=false (the current default), schedules live only
  in this process's memory, same limitation as the rest of the in-memory
  store, they do not survive a restart. `ReportScheduler.persistent`
  tells you which mode you're in; the API surfaces it too.

SSRF note: `webhook_url` is validated to reject localhost/private/link-local
addresses before it's ever stored or called. This is a minimal denylist,
not a full allowlist, treat it as a floor, not a complete SSRF defense,
before this handles real external webhook URLs in production.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

MYT = ZoneInfo("Asia/Kuala_Lumpur")


class WebhookValidationError(ValueError):
    pass


def validate_webhook_url(url: str) -> None:
    """Reject webhook URLs pointing at localhost, private, or link-local
    ranges. Deliberately conservative, if resolution fails or the target
    is ambiguous, reject rather than allow.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise WebhookValidationError("webhook_url must be http(s)")
    if not parsed.hostname:
        raise WebhookValidationError("webhook_url has no hostname")

    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise WebhookValidationError(f"could not resolve webhook host: {host}") from e

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise WebhookValidationError(
                f"webhook_url resolves to a disallowed address range: {ip}"
            )


@dataclass
class ReportSchedule:
    id: str
    org_id: str
    workspace_id: str
    snapshot_id: str
    cadence: str = "weekly"  # weekly | on_demand
    day_of_week: int = 0  # 0=Monday .. 6=Sunday
    hour_myt: int = 9
    recipients: list[str] = field(default_factory=list)
    webhook_url: str | None = None
    enabled: bool = True
    created_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_status: str | None = None

    def compute_next_run(self, after: datetime | None = None) -> datetime:
        now_myt = (after or datetime.now(timezone.utc)).astimezone(MYT)
        days_ahead = (self.day_of_week - now_myt.weekday()) % 7
        candidate = (now_myt + timedelta(days=days_ahead)).replace(
            hour=self.hour_myt, minute=0, second=0, microsecond=0
        )
        if candidate <= now_myt:
            candidate += timedelta(days=7)
        return candidate.astimezone(timezone.utc)


def _id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class ReportScheduler:
    """In-memory schedule registry with an optional DB-backed persistence
    hook. Deliberately does not spin up its own background thread or
    asyncio task on construction, call `run_due(now)` from whatever
    already-running periodic trigger you have (a FastAPI background task,
    an external cron hitting an internal endpoint, APScheduler if you add
    it) — this class only tracks state and executes jobs when asked, so
    it doesn't add a second unmanaged scheduler loop that fights with
    however this service actually gets deployed.
    """

    def __init__(self, persistent: bool = False) -> None:
        self.persistent = persistent
        self._schedules: dict[str, ReportSchedule] = {}

    def register(
        self,
        *,
        org_id: str,
        workspace_id: str,
        snapshot_id: str,
        cadence: str = "weekly",
        day_of_week: int = 0,
        hour_myt: int = 9,
        recipients: list[str] | None = None,
        webhook_url: str | None = None,
        created_by: str = "",
    ) -> ReportSchedule:
        if cadence not in ("weekly", "on_demand"):
            raise ValueError(f"unsupported cadence: {cadence}")
        if not (0 <= day_of_week <= 6):
            raise ValueError("day_of_week must be 0 (Mon) through 6 (Sun)")
        if not (0 <= hour_myt <= 23):
            raise ValueError("hour_myt must be 0-23")
        if webhook_url:
            validate_webhook_url(webhook_url)

        sched = ReportSchedule(
            id=_id("sched"),
            org_id=org_id,
            workspace_id=workspace_id,
            snapshot_id=snapshot_id,
            cadence=cadence,
            day_of_week=day_of_week,
            hour_myt=hour_myt,
            recipients=recipients or [],
            webhook_url=webhook_url,
            created_by=created_by,
        )
        sched.next_run_at = sched.compute_next_run() if cadence == "weekly" else None
        self._schedules[sched.id] = sched
        return sched

    def update(self, schedule_id: str, **updates: Any) -> ReportSchedule:
        sched = self._schedules.get(schedule_id)
        if not sched:
            raise KeyError(f"schedule not found: {schedule_id}")
        if "webhook_url" in updates and updates["webhook_url"]:
            validate_webhook_url(updates["webhook_url"])
        for k, v in updates.items():
            if hasattr(sched, k):
                setattr(sched, k, v)
        if sched.cadence == "weekly":
            sched.next_run_at = sched.compute_next_run()
        return sched

    def list_for_workspace(self, workspace_id: str) -> list[ReportSchedule]:
        return [s for s in self._schedules.values() if s.workspace_id == workspace_id]

    def get(self, schedule_id: str) -> Optional[ReportSchedule]:
        return self._schedules.get(schedule_id)

    def due(self, now: datetime | None = None) -> list[ReportSchedule]:
        now = now or datetime.now(timezone.utc)
        return [
            s
            for s in self._schedules.values()
            if s.enabled and s.cadence == "weekly" and s.next_run_at and s.next_run_at <= now
        ]

    def run_due(
        self,
        job: Callable[[ReportSchedule], dict[str, Any]],
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Run `job(schedule)` for every due schedule, advance next_run_at,
        record outcome. `job` is injected so this module doesn't need to
        know how to build/send a report itself, that stays in the route
        layer where org/workspace context and the actual store live.
        """
        now = now or datetime.now(timezone.utc)
        results = []
        for sched in self.due(now):
            try:
                outcome = job(sched)
                sched.last_run_status = "ok"
                results.append({"schedule_id": sched.id, "status": "ok", "outcome": outcome})
            except Exception as e:  # noqa: BLE001 - report failures shouldn't crash the loop
                sched.last_run_status = f"error: {e}"
                results.append({"schedule_id": sched.id, "status": "error", "error": str(e)})
            sched.last_run_at = now
            sched.next_run_at = sched.compute_next_run(after=now)
        return results
