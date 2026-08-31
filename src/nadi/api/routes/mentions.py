from fastapi import APIRouter, Depends, HTTPException, Query

from nadi.api.deps import get_ctx, need
from nadi.api.store import store
from nadi.domain.rbac import WS_MENTIONS_CODE, WS_MENTIONS_READ

router = APIRouter(prefix="/workspaces/{ws_id}/mentions", tags=["mentions"])


@router.get("")
def list_mentions(
    ws_id: str,
    east_my: bool | None = None,
    three_r: bool | None = None,
    ctx: dict = Depends(get_ctx),
):
    need(ctx, WS_MENTIONS_READ)
    if ws_id != store.workspace.id:
        raise HTTPException(404, "workspace not found")
    items = store.mentions
    if east_my is not None:
        items = [m for m in items if m.east_my is east_my]
    if three_r:
        items = [m for m in items if m.three_r.flags]
    return {"items": [m.model_dump(mode="json") for m in items], "count": len(items)}


@router.get("/{mention_id}")
def get_mention(ws_id: str, mention_id: str, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_MENTIONS_READ)
    for m in store.mentions:
        if m.id == mention_id and m.workspace_id == ws_id:
            return m.model_dump(mode="json")
    raise HTTPException(404, "mention not found")


@router.post("/{mention_id}/codes")
def code_mention(
    ws_id: str,
    mention_id: str,
    body: dict,
    ctx: dict = Depends(get_ctx),
):
    need(ctx, WS_MENTIONS_CODE)
    for m in store.mentions:
        if m.id == mention_id and m.workspace_id == ws_id:
            codes = body.get("codes") or []
            m.codes = list(dict.fromkeys([*m.codes, *codes]))
            if body.get("three_r_review"):
                m.three_r.review = body["three_r_review"]
            return m.model_dump(mode="json")
    raise HTTPException(404, "mention not found")


@router.post("/ingest/trigger")
async def trigger_ingest(ws_id: str, body: dict = None, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_MENTIONS_CODE)
    if ws_id != store.workspace.id:
        raise HTTPException(404, "workspace not found")

    from nadi.connectors.pipeline import IngestionPipeline
    pipeline = IngestionPipeline(org_id=store.org.id, workspace_id=ws_id)
    ingested = await pipeline.run_rss_sync()
    return {
        "status": "success",
        "ingested_count": len(ingested),
        "items": [m.model_dump(mode="json") for m in ingested],
    }


@router.post("/ingest/webhook")
def ingest_webhook(ws_id: str, body: dict, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_MENTIONS_CODE)
    if ws_id != store.workspace.id:
        raise HTTPException(404, "workspace not found")

    from nadi.connectors.pipeline import IngestionPipeline
    pipeline = IngestionPipeline(org_id=store.org.id, workspace_id=ws_id)
    source_type = body.get("source_type", "social")
    mention = pipeline.ingest_webhook_payload(payload=body, source_type=source_type)
    return {
        "status": "success",
        "mention": mention.model_dump(mode="json"),
    }

