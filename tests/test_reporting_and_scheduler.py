"""
Tests for the report scheduler and executive brief generator.

Covers what the implementation plan asked for (compilation from seed data,
HTML rendering, AVE rejection, scheduler registration/execution, the three
routes) plus the specific things flagged before implementation started:
permission gating on every route, and the webhook SSRF guard.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from nadi.api.app import app
from nadi.api.store import store
from nadi.services.reporting_service import build_executive_report, generate_report_html
from nadi.services.scheduler import ReportScheduler, WebhookValidationError, validate_webhook_url

client = TestClient(app)
WS = store.workspace.id


def _headers(role: str) -> dict:
    return {"X-Nadi-Role": role}


def _seed_snapshot_id() -> str:
    return next(iter(store.snapshots.keys()))


# ---- report compilation ----

def test_build_executive_report_from_seed_data():
    snap = store.snapshots[_seed_snapshot_id()]
    report = build_executive_report(
        org_id=store.org.id,
        workspace_id=WS,
        snapshot=snap,
        mentions=store.mentions,
        war_rooms=list(store.war_rooms.values()),
        holdings=list(store.holdings.values()),
        generated_by={"user_id": "test"},
    )
    assert report["ave_included"] is False
    assert len(report["moves"]) == 3
    assert report["three_r"]["total_mentions"] == len(store.mentions)
    assert 0.0 <= report["east_my"]["share"] <= 1.0
    assert report["report_id"].startswith("rpt_")


def test_report_rejects_unlocked_snapshot():
    snap = store.snapshots[_seed_snapshot_id()].model_copy()
    snap.status = "draft"  # bypasses the field_validator by mutating post-construction
    with pytest.raises(ValueError, match="locked"):
        build_executive_report(
            org_id=store.org.id,
            workspace_id=WS,
            snapshot=snap,
            mentions=store.mentions,
            war_rooms=[],
            holdings=[],
            generated_by={},
        )


def test_generate_report_html_contains_no_ave_banner_and_no_pdf_claim():
    snap = store.snapshots[_seed_snapshot_id()]
    report = build_executive_report(
        org_id=store.org.id, workspace_id=WS, snapshot=snap,
        mentions=store.mentions, war_rooms=list(store.war_rooms.values()),
        holdings=list(store.holdings.values()), generated_by={},
    )
    html = generate_report_html(report)
    assert "No AVE" in html
    assert "not a generated PDF file" in html
    assert str(report["contribution"]["score"]) in html


# ---- webhook SSRF guard ----

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/hook",
    "http://localhost/hook",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
    "http://10.0.0.5/hook",
    "ftp://example.com/hook",
])
def test_webhook_validation_rejects_unsafe_targets(url):
    with pytest.raises(WebhookValidationError):
        validate_webhook_url(url)


def test_webhook_validation_accepts_public_host():
    # example.com resolves publicly and isn't in a reserved range
    validate_webhook_url("https://example.com/hook")


# ---- scheduler unit behavior ----

def test_scheduler_compute_next_run_is_in_the_future():
    sched = ReportScheduler()
    s = sched.register(org_id="o", workspace_id="w", snapshot_id="s", day_of_week=0, hour_myt=9)
    assert s.next_run_at > datetime.now(timezone.utc)


def test_scheduler_run_due_advances_and_records_status():
    sched = ReportScheduler()
    s = sched.register(org_id="o", workspace_id="w", snapshot_id="s", day_of_week=0, hour_myt=9)
    future = s.next_run_at + timedelta(seconds=1)

    results = sched.run_due(job=lambda sc: {"ok": True}, now=future)
    assert len(results) == 1
    assert results[0]["status"] == "ok"
    assert s.last_run_status == "ok"
    assert s.next_run_at > future


def test_scheduler_run_due_records_error_without_crashing():
    sched = ReportScheduler()
    s = sched.register(org_id="o", workspace_id="w", snapshot_id="s", day_of_week=0, hour_myt=9)
    future = s.next_run_at + timedelta(seconds=1)

    def _boom(_sc):
        raise RuntimeError("simulated failure")

    results = sched.run_due(job=_boom, now=future)
    assert results[0]["status"] == "error"
    assert "simulated failure" in s.last_run_status


# ---- API routes: permission gating ----

def test_viewer_cannot_generate_report():
    snap_id = _seed_snapshot_id()
    resp = client.post(
        f"/v1/workspaces/{WS}/reports/generate",
        json={"snapshot_id": snap_id},
        headers=_headers("viewer"),
    )
    assert resp.status_code == 403


def test_analyst_cannot_generate_report():
    """analyst has ws.brief.run but not ws.reports.run, matching the RBAC
    matrix — this route intentionally does not treat brief-drafting
    permission as report-running permission."""
    snap_id = _seed_snapshot_id()
    resp = client.post(
        f"/v1/workspaces/{WS}/reports/generate",
        json={"snapshot_id": snap_id},
        headers=_headers("analyst"),
    )
    assert resp.status_code == 403


def test_editor_can_generate_report():
    snap_id = _seed_snapshot_id()
    resp = client.post(
        f"/v1/workspaces/{WS}/reports/generate",
        json={"snapshot_id": snap_id},
        headers=_headers("editor"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ave_included"] is False
    assert len(body["moves"]) == 3


def test_preview_returns_html_not_pdf_content_type():
    snap_id = _seed_snapshot_id()
    resp = client.get(
        f"/v1/workspaces/{WS}/reports/preview",
        params={"snapshot_id": snap_id},
        headers=_headers("ws_admin"),
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_generate_report_404s_on_unknown_snapshot():
    resp = client.post(
        f"/v1/workspaces/{WS}/reports/generate",
        json={"snapshot_id": "snap_does_not_exist"},
        headers=_headers("ws_admin"),
    )
    assert resp.status_code == 404


# ---- API routes: scheduling ----

def test_viewer_cannot_create_schedule():
    snap_id = _seed_snapshot_id()
    resp = client.post(
        f"/v1/workspaces/{WS}/reports/schedule",
        json={"snapshot_id": snap_id},
        headers=_headers("viewer"),
    )
    assert resp.status_code == 403


def test_ws_admin_can_create_schedule_and_it_lists():
    snap_id = _seed_snapshot_id()
    created = client.post(
        f"/v1/workspaces/{WS}/reports/schedule",
        json={"snapshot_id": snap_id, "day_of_week": 2, "hour_myt": 10},
        headers=_headers("ws_admin"),
    )
    assert created.status_code == 200
    sched_id = created.json()["id"]

    listing = client.get(f"/v1/workspaces/{WS}/reports/schedules", headers=_headers("ws_admin"))
    assert listing.status_code == 200
    ids = [s["id"] for s in listing.json()["schedules"]]
    assert sched_id in ids


def test_schedule_rejects_ssrf_webhook_at_the_route():
    snap_id = _seed_snapshot_id()
    resp = client.post(
        f"/v1/workspaces/{WS}/reports/schedule",
        json={"snapshot_id": snap_id, "webhook_url": "http://127.0.0.1:1234/x"},
        headers=_headers("ws_admin"),
    )
    assert resp.status_code == 422


def test_schedule_requires_known_snapshot():
    resp = client.post(
        f"/v1/workspaces/{WS}/reports/schedule",
        json={"snapshot_id": "snap_nope"},
        headers=_headers("ws_admin"),
    )
    assert resp.status_code == 404


def test_run_due_schedules_requires_permission():
    resp = client.post(f"/v1/workspaces/{WS}/reports/schedules/run-due", headers=_headers("viewer"))
    assert resp.status_code == 403
