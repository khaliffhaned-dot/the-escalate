"""
Report generation and scheduling routes.

Every route here requires WS_REPORTS_RUN, which already existed in the
RBAC matrix (ws_admin, editor) but nothing previously checked it, this
is the same shape of gap as the earlier holding-approval and war-room-close
issues, so it's wired explicitly here rather than left implicit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from nadi.api.deps import get_ctx, need
from nadi.api.store import store
from nadi.domain.rbac import WS_REPORTS_RUN
from nadi.services.reporting_service import build_executive_report, generate_report_html
from nadi.services.scheduler import WebhookValidationError

router = APIRouter(prefix="/workspaces/{ws_id}/reports", tags=["reports"])


class ScheduleIn(BaseModel):
    snapshot_id: str
    cadence: str = "weekly"
    day_of_week: int = Field(default=0, ge=0, le=6)
    hour_myt: int = Field(default=9, ge=0, le=23)
    recipients: list[str] = Field(default_factory=list)
    webhook_url: str | None = None


class ScheduleUpdateIn(BaseModel):
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    hour_myt: int | None = Field(default=None, ge=0, le=23)
    recipients: list[str] | None = None
    webhook_url: str | None = None
    enabled: bool | None = None


def _get_snapshot_or_404(ws_id: str, snapshot_id: str):
    snap = store.snapshots.get(snapshot_id)
    if not snap or snap.workspace_id != ws_id:
        raise HTTPException(404, "evaluation snapshot not found")
    return snap


def _compile_report(ws_id: str, snapshot_id: str, ctx: dict) -> dict:
    snap = _get_snapshot_or_404(ws_id, snapshot_id)
    return build_executive_report(
        org_id=store.org.id,
        workspace_id=ws_id,
        snapshot=snap,
        mentions=store.mentions,
        war_rooms=list(store.war_rooms.values()),
        holdings=list(store.holdings.values()),
        generated_by={"user_id": store.user.id, "role": str(ctx.get("ws_role"))},
    )


@router.post("/generate")
def generate_report(ws_id: str, body: dict, ctx: dict = Depends(get_ctx)):
    """On-demand executive brief. Returns the compiled report data
    structure (not HTML) — use GET /reports/preview for the rendered
    document.
    """
    need(ctx, WS_REPORTS_RUN)
    snapshot_id = body.get("snapshot_id")
    if not snapshot_id:
        raise HTTPException(422, "snapshot_id is required")
    try:
        return _compile_report(ws_id, snapshot_id, ctx)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/preview", response_class=HTMLResponse)
def preview_report(ws_id: str, snapshot_id: str, ctx: dict = Depends(get_ctx)):
    """Renders print-styled HTML for browser preview or print-to-PDF.

    IMPORTANT: this returns HTML, not a PDF file. There is no PDF
    generation library in this project. Use your browser's own
    Print -> Save as PDF on the returned page if you need a PDF.
    """
    need(ctx, WS_REPORTS_RUN)
    try:
        report = _compile_report(ws_id, snapshot_id, ctx)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return generate_report_html(report)


@router.post("/schedule")
def create_or_update_schedule(ws_id: str, body: ScheduleIn, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_REPORTS_RUN)
    _get_snapshot_or_404(ws_id, body.snapshot_id)
    try:
        sched = store.report_scheduler.register(
            org_id=store.org.id,
            workspace_id=ws_id,
            snapshot_id=body.snapshot_id,
            cadence=body.cadence,
            day_of_week=body.day_of_week,
            hour_myt=body.hour_myt,
            recipients=body.recipients,
            webhook_url=body.webhook_url,
            created_by=store.user.id,
        )
    except (ValueError, WebhookValidationError) as e:
        raise HTTPException(422, str(e)) from e
    return {
        "id": sched.id,
        "cadence": sched.cadence,
        "day_of_week": sched.day_of_week,
        "hour_myt": sched.hour_myt,
        "next_run_at": sched.next_run_at.isoformat() if sched.next_run_at else None,
        "enabled": sched.enabled,
        "persistent": store.report_scheduler.persistent,
    }


@router.patch("/schedule/{schedule_id}")
def update_schedule(ws_id: str, schedule_id: str, body: ScheduleUpdateIn, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_REPORTS_RUN)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        sched = store.report_scheduler.update(schedule_id, **updates)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except (ValueError, WebhookValidationError) as e:
        raise HTTPException(422, str(e)) from e
    if sched.workspace_id != ws_id:
        raise HTTPException(404, "schedule not found in this workspace")
    return {
        "id": sched.id,
        "enabled": sched.enabled,
        "next_run_at": sched.next_run_at.isoformat() if sched.next_run_at else None,
    }


@router.get("/schedules")
def list_schedules(ws_id: str, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_REPORTS_RUN)
    schedules = store.report_scheduler.list_for_workspace(ws_id)
    return {
        "persistent": store.report_scheduler.persistent,
        "schedules": [
            {
                "id": s.id,
                "snapshot_id": s.snapshot_id,
                "cadence": s.cadence,
                "day_of_week": s.day_of_week,
                "hour_myt": s.hour_myt,
                "recipients": s.recipients,
                "webhook_url": s.webhook_url,
                "enabled": s.enabled,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                "last_run_status": s.last_run_status,
            }
            for s in schedules
        ],
    }


@router.post("/schedules/run-due")
def run_due_schedules(ws_id: str, ctx: dict = Depends(get_ctx)):
    """Executes any due weekly schedules now. In production this endpoint
    (or the equivalent internal call) needs an external periodic trigger,
    a cron job, APScheduler, or your hosting platform's scheduled-task
    feature, since this process does not run its own background loop.
    Exposed as a route specifically so that trigger can be "hit this URL
    on a timer" without needing in-process async scheduling.
    """
    need(ctx, WS_REPORTS_RUN)

    def _job(sched):
        report = _compile_report(sched.workspace_id, sched.snapshot_id, ctx)
        # NOTE: no actual email/webhook delivery is implemented here yet,
        # this compiles the report and records that a run happened. Wiring
        # real SMTP/webhook delivery is next-step work, not silently
        # implied by this endpoint's name.
        return {"report_id": report["report_id"], "recipients": sched.recipients}

    results = store.report_scheduler.run_due(_job)
    return {"ran": len(results), "results": results}
