"""
Executive report compilation + rendering.

Two things worth being explicit about, per the implementation plan's own
"User Review Required" banner:

1. NO AVE. This module never computes or renders an advertising-value
   equivalent, media value, or PR value figure. `build_executive_report`
   pulls its numbers straight from an already-locked EvaluationSnapshot,
   which itself enforces this at the Pydantic model level
   (see domain/models.Methodology / evaluation_service). There is nothing
   here that could reintroduce it.

2. This renders PRINT-STYLED HTML, not a PDF file. The implementation plan
   says "printable PDF document" — that's what the browser's own
   print-to-PDF does with this HTML, there is no PDF-generation library in
   this project and this module does not produce a `.pdf` byte stream. The
   route docstrings and API responses say this explicitly so nobody
   mistakes GET /reports/preview for an endpoint that returns real PDF
   bytes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from html import escape
from typing import Any

from nadi.domain.models import EvaluationSnapshot, HoldingBrief, Mention, WarRoom

REPORT_TEMPLATE_VERSION = "nadi-exec-report-2026-08"


def _canonical_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _three_r_summary(mentions: list[Mention]) -> dict[str, Any]:
    flagged = [m for m in mentions if m.three_r.flags]
    by_flag: dict[str, int] = {}
    for m in flagged:
        for f in m.three_r.flags:
            by_flag[f.value] = by_flag.get(f.value, 0) + 1
    high_severity = [m.id for m in flagged if m.three_r.severity == "high"]
    return {
        "total_mentions": len(mentions),
        "flagged_count": len(flagged),
        "by_flag": by_flag,
        "high_severity_mention_ids": high_severity,
        "in_review_count": sum(1 for m in flagged if m.three_r.review == "in_review"),
    }


def _east_my_summary(mentions: list[Mention]) -> dict[str, Any]:
    east = [m for m in mentions if m.east_my]
    by_state: dict[str, int] = {}
    for m in mentions:
        if m.state:
            by_state[m.state] = by_state.get(m.state, 0) + 1
    share = round(len(east) / len(mentions), 4) if mentions else 0.0
    return {
        "east_my_count": len(east),
        "total_mentions": len(mentions),
        "share": share,
        "by_state": by_state,
    }


def build_executive_report(
    *,
    org_id: str,
    workspace_id: str,
    snapshot: EvaluationSnapshot,
    mentions: list[Mention],
    war_rooms: list[WarRoom],
    holdings: list[HoldingBrief],
    generated_by: dict[str, Any],
) -> dict[str, Any]:
    """Compile a locked snapshot plus current mentions/war-rooms/holdings
    into a report data structure. Takes an already-locked snapshot as
    input rather than building one, this is a reporting layer, not a
    second place that computes contribution scores.
    """
    if snapshot.status != "locked":
        raise ValueError("report can only be generated from a locked evaluation snapshot")

    active_war_rooms = [wr for wr in war_rooms if wr.status.value != "closed"]
    pending_holdings = [h for h in holdings if h.status.value not in ("sent_external", "superseded")]

    moves = snapshot.moves
    if len(moves) != 3:
        # Mirrors the invariant already enforced when the snapshot was
        # locked (evaluation_service requires exactly 3). Re-checking here
        # rather than trusting it silently means a corrupted/hand-edited
        # snapshot fails loudly in the report instead of producing a
        # report that quietly has the wrong number of board moves.
        raise ValueError(f"expected exactly 3 board moves on the snapshot, found {len(moves)}")

    report: dict[str, Any] = {
        "report_id": None,  # set after hashing, so the id can include the hash
        "template_version": REPORT_TEMPLATE_VERSION,
        "org_id": org_id,
        "workspace_id": workspace_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": generated_by,
        "snapshot_id": snapshot.id,
        "snapshot_content_sha256": snapshot.integrity.get("content_sha256"),
        "title": snapshot.title,
        "window": snapshot.window,
        "contribution": snapshot.contribution,
        "ladder": {k: v.model_dump(mode="json") for k, v in snapshot.ladder.items()},
        "objectives": [o.model_dump(mode="json") for o in snapshot.objectives],
        "moves": moves,
        "three_r": _three_r_summary(mentions),
        "east_my": _east_my_summary(mentions),
        "active_war_rooms": [
            {"id": wr.id, "title": wr.title, "severity": wr.severity.value, "status": wr.status.value}
            for wr in active_war_rooms
        ],
        "pending_holdings": [
            {"id": h.id, "status": h.status.value, "war_room_id": h.war_room_id}
            for h in pending_holdings
        ],
        "governance": snapshot.governance,
        "ave_included": False,  # explicit, not just implied by absence
    }
    report["report_id"] = "rpt_" + _canonical_hash(report)[:16]
    return report


_STATUS_COLORS = {
    "green": "#2e7d32", "amber": "#c77700", "red": "#c62828", "not_started": "#6b7280",
}
_BAND_COLORS = {
    "off_track": "#c62828", "at_risk": "#c77700", "on_track": "#2e7d32", "exceeding": "#1e5c8a",
}


def generate_report_html(report: dict[str, Any]) -> str:
    """Render the report dict as standalone, print-friendly HTML.

    Standalone: all CSS is inlined, no external requests, safe to email as
    a single HTML document. Print-friendly: includes @media print rules
    so a browser's own print-to-PDF produces a clean one-column layout,
    this is NOT a PDF generation library and does not emit PDF bytes.
    """
    c = report["contribution"]
    band = c.get("band", "on_track")
    band_color = _BAND_COLORS.get(band, "#1e5c8a")

    objectives_rows = "".join(
        f"""<tr>
            <td>{escape(o['id'])}</td>
            <td>{escape(o['label_en'])}</td>
            <td style="text-align:right">{o['actual']} / {o['target']}</td>
            <td><span class="pill" style="background:{_STATUS_COLORS.get(o['status'], '#6b7280')}">{escape(o['status'])}</span></td>
        </tr>"""
        for o in report["objectives"]
    )

    ladder_rows = "".join(
        f"""<div class="ladder-stage">
            <div class="ladder-label">{escape(key)}</div>
            <div class="ladder-bar-track"><div class="ladder-bar-fill" style="width:{v['score']}%"></div></div>
            <div class="ladder-score">{v['score']}</div>
        </div>"""
        for key, v in report["ladder"].items()
    )

    moves_items = "".join(
        f"""<li><strong>{escape(m.get('en', ''))}</strong>
            <span class="muted"> — horizon {escape(str(m.get('horizon_days', '?')))} days</span></li>"""
        for m in report["moves"]
    )

    three_r = report["three_r"]
    three_r_flags = "".join(
        f'<span class="pill" style="background:#8B0000">{escape(k)}: {v}</span>' for k, v in three_r["by_flag"].items()
    ) or '<span class="muted">none this window</span>'

    east = report["east_my"]

    war_rooms_html = "".join(
        f"""<tr><td>{escape(w['title'])}</td><td>{escape(w['severity'])}</td><td>{escape(w['status'])}</td></tr>"""
        for w in report["active_war_rooms"]
    ) or '<tr><td colspan="3" class="muted">No active war rooms this window</td></tr>'

    holdings_html = "".join(
        f"""<tr><td>{escape(h['id'])}</td><td>{escape(h['status'])}</td></tr>"""
        for h in report["pending_holdings"]
    ) or '<tr><td colspan="2" class="muted">No holdings pending this window</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(report['title'])} — Executive Brief</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; color: #1a1d21; max-width: 780px; margin: 0 auto; padding: 32px 20px; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .subtitle {{ color: #6b7280; font-size: 12px; margin-bottom: 24px; }}
  .band-badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; color: #fff; font-size: 12px; font-weight: 600; background: {band_color}; }}
  .score {{ font-size: 32px; font-weight: 700; margin: 8px 0; }}
  .muted {{ color: #6b7280; font-size: 12px; }}
  section {{ margin: 28px 0; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b7280; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  td, th {{ padding: 6px 4px; border-bottom: 1px solid #f0f0f0; text-align: left; }}
  .pill {{ display: inline-block; padding: 2px 8px; border-radius: 3px; color: #fff; font-size: 11px; }}
  .ladder-stage {{ display: flex; align-items: center; gap: 10px; margin: 6px 0; }}
  .ladder-label {{ width: 90px; font-size: 12px; text-transform: capitalize; }}
  .ladder-bar-track {{ flex: 1; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }}
  .ladder-bar-fill {{ height: 100%; background: #1e5c8a; }}
  .ladder-score {{ width: 32px; text-align: right; font-size: 12px; }}
  .footer {{ margin-top: 32px; padding-top: 12px; border-top: 1px solid #e5e7eb; font-size: 10px; color: #9ca3af; }}
  .no-ave {{ background: #fff8e1; border: 1px solid #f0d060; border-radius: 4px; padding: 10px 14px; font-size: 12px; margin: 16px 0; }}
  @media print {{
    body {{ padding: 0; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
  <h1>{escape(report['title'])}</h1>
  <div class="subtitle">
    {escape(report['window'].get('from', ''))} &rarr; {escape(report['window'].get('to', ''))}
    &middot; generated {escape(report['generated_at'])}
    &middot; report {escape(report['report_id'])}
  </div>

  <div class="no-ave">
    No AVE / advertising value equivalent is included in this report, by design.
    Barcelona Principles 4.0 compliant. Snapshot integrity hash:
    <code>{escape(str(report.get('snapshot_content_sha256', '')))}</code>
  </div>

  <section>
    <h2>Contribution score</h2>
    <div class="score">{c.get('score', '—')}</div>
    <span class="band-badge">{escape(band)}</span>
    <div class="muted" style="margin-top:6px">{escape(c.get('formula', ''))}</div>
  </section>

  <section>
    <h2>Evaluation ladder</h2>
    {ladder_rows}
  </section>

  <section>
    <h2>Objectives</h2>
    <table>
      <tr><th>ID</th><th>Objective</th><th style="text-align:right">Actual / Target</th><th>Status</th></tr>
      {objectives_rows}
    </table>
  </section>

  <section>
    <h2>3 board moves</h2>
    <ul>{moves_items}</ul>
  </section>

  <section>
    <h2>3R risk summary</h2>
    <p class="muted">{three_r['flagged_count']} of {three_r['total_mentions']} mentions flagged this window, {three_r['in_review_count']} in review.</p>
    <div>{three_r_flags}</div>
  </section>

  <section>
    <h2>East Malaysia distribution</h2>
    <p class="muted">{east['east_my_count']} of {east['total_mentions']} mentions ({east['share']*100:.1f}%) tagged East MY.</p>
  </section>

  <section>
    <h2>Active war rooms</h2>
    <table><tr><th>Title</th><th>Severity</th><th>Status</th></tr>{war_rooms_html}</table>
  </section>

  <section>
    <h2>Holding statements pending</h2>
    <table><tr><th>ID</th><th>Status</th></tr>{holdings_html}</table>
  </section>

  <div class="footer">
    {escape(report['governance'].get('footer_en', ''))}<br>
    Rendered by {escape(REPORT_TEMPLATE_VERSION)}. This is print-styled HTML, not a generated PDF file,
    use your browser's Print &rarr; Save as PDF for a PDF copy.
  </div>
</body>
</html>"""
