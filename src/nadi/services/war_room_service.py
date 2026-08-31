"""War room lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone

from nadi.domain.enums import WarRoomSeverity, WarRoomStatus
from nadi.domain.models import Decision, ResidueItem, WarRoom


def open_war_room(
    *,
    org_id: str,
    workspace_id: str,
    title: str,
    severity: WarRoomSeverity,
    trigger: dict,
    opened_by: str,
    three_r: dict | None = None,
    residue: list[ResidueItem] | None = None,
) -> WarRoom:
    now = datetime.now(timezone.utc)
    wr = WarRoom(
        org_id=org_id,
        workspace_id=workspace_id,
        status=WarRoomStatus.OPEN,
        severity=severity,
        title=title,
        trigger=trigger,
        three_r=three_r
        or {
            "flags": [],
            "posture": "self_regulated_not_directed",
            "review": "pending",
        },
        queues={
            "three_r": trigger.get("mention_id") and [trigger["mention_id"]] or [],
            "residue": [r.model_dump(mode="json") for r in (residue or [])],
            "queries": [],
            "assignments": [],
        },
        opened_at=now,
        opened_by=opened_by,
        decisions=[
            Decision(
                at=now,
                actor_user_id=opened_by,
                action="opened",
                note="War room opened",
            )
        ],
    )
    return wr


def append_decision(wr: WarRoom, actor_user_id: str, action: str, note: str = "") -> WarRoom:
    wr.decisions.append(
        Decision(
            at=datetime.now(timezone.utc),
            actor_user_id=actor_user_id,
            action=action,
            note=note,
        )
    )
    return wr


def contain(wr: WarRoom, actor_user_id: str, note: str = "") -> WarRoom:
    wr.status = WarRoomStatus.CONTAINED
    wr.contained_at = datetime.now(timezone.utc)
    return append_decision(wr, actor_user_id, "contained", note)


def close(wr: WarRoom, actor_user_id: str, note: str = "") -> WarRoom:
    wr.status = WarRoomStatus.CLOSED
    wr.closed_at = datetime.now(timezone.utc)
    return append_decision(wr, actor_user_id, "closed", note)
