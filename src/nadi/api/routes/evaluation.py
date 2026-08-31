from fastapi import APIRouter, Depends, HTTPException

from nadi.api.deps import get_ctx, need
from nadi.api.store import store
from nadi.data.seed_aurora import seed_ladder, seed_moves, seed_objectives
from nadi.domain.rbac import WS_EVALUATION_LOCK, WS_EVALUATION_READ
from nadi.services.evaluation_service import build_snapshot

router = APIRouter(prefix="/workspaces/{ws_id}/evaluation", tags=["evaluation"])


@router.get("")
def get_evaluation(ws_id: str, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_EVALUATION_READ)
    if ws_id != store.workspace.id:
        raise HTTPException(404, "workspace not found")
    # latest snapshot as live view for demo
    if not store.snapshots:
        raise HTTPException(404, "no evaluation")
    latest = max(store.snapshots.values(), key=lambda s: s.created_at)
    return latest.model_dump(mode="json")


@router.get("/snapshots/{snap_id}")
def get_snapshot(ws_id: str, snap_id: str, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_EVALUATION_READ)
    snap = store.snapshots.get(snap_id)
    if not snap or snap.workspace_id != ws_id:
        raise HTTPException(404, "snapshot not found")
    if snap.methodology.ave is not False:
        raise HTTPException(500, "invalid snapshot: AVE must be false")
    return snap.model_dump(mode="json")


@router.post("/lock")
def lock_evaluation(ws_id: str, body: dict | None = None, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_EVALUATION_LOCK)
    if ws_id != store.workspace.id:
        raise HTTPException(404, "workspace not found")
    body = body or {}
    if body.get("include_ave"):
        raise HTTPException(422, "AVE not allowed under Barcelona Principles 4.0")
    snap = build_snapshot(
        org_id=store.org.id,
        workspace_id=ws_id,
        title=body.get("title") or "Jalur Kita · locked window",
        campaign={"id": "cmp_jalur_kita", "name": "Jalur Kita Merdeka 2026", "client": "Aurora Group"},
        window=body.get("window")
        or {
            "from": "2026-08-18T00:00:00Z",
            "to": "2026-08-24T15:59:59Z",
            "timezone": "Asia/Kuala_Lumpur",
            "label": "18–24 Aug 2026",
        },
        objectives=seed_objectives(),
        ladder=seed_ladder(),
        moves=seed_moves(),
        created_by={"user_id": store.user.id, "name": store.user.name, "role": "ws_admin"},
        campaign_cost_myr=body.get("campaign_cost_myr", 180000),
        narrative_en="Contribution held back by East MY and dual-calendar, not volume.",
        narrative_bm="Sumbangan tertahan oleh MY Timur dan kalendar dual, bukan volume.",
    )
    store.snapshots[snap.id] = snap
    return snap.model_dump(mode="json")
