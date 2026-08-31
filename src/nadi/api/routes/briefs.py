from fastapi import APIRouter, Depends, HTTPException

from nadi.api.deps import get_ctx, need
from nadi.api.store import store
from nadi.domain.enums import HoldingStatus
from nadi.domain.rbac import WS_BRIEF_RUN
from nadi.services.holding_service import draft_holding_from_mentions, reject_if_ave_requested, transition
from nadi.services.llm_holding import generate_holding_with_llm

router = APIRouter(tags=["briefs"])


@router.post("/workspaces/{ws_id}/briefs")
async def create_brief(ws_id: str, body: dict, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_BRIEF_RUN)
    if ws_id != store.workspace.id:
        raise HTTPException(404, "workspace not found")
    try:
        reject_if_ave_requested(body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    kind = body.get("kind", "holding")
    if kind != "holding":
        raise HTTPException(400, "only kind=holding implemented in this scaffold")

    mention_ids = body.get("mention_ids") or []
    mentions = [m for m in store.mentions if m.id in mention_ids]
    if not mentions and mention_ids:
        raise HTTPException(404, "mentions not found")
    if not mentions:
        mentions = [m for m in store.mentions if m.three_r.flags][:1]

    use_llm = body.get("use_llm", True)
    if use_llm:
        holding = await generate_holding_with_llm(
            mentions=mentions,
            war_room_id=body.get("war_room_id"),
            locale=body.get("locale", "bilingual"),
            audience=body.get("audience", "press"),
            tabletop=bool(body.get("tabletop")),
            extra_context=body.get("extra_context"),
            provider=body.get("provider"),
            model=body.get("model"),
        )
    else:
        holding = draft_holding_from_mentions(
            mentions=mentions,
            war_room_id=body.get("war_room_id"),
            locale=body.get("locale", "bilingual"),
            audience=body.get("audience", "press"),
            tabletop=bool(body.get("tabletop")),
        )
    store.holdings[holding.id] = holding
    if holding.war_room_id and holding.war_room_id in store.war_rooms:
        wr = store.war_rooms[holding.war_room_id]
        wr.holdings.append(
            {
                "id": holding.id,
                "brief_id": holding.brief_id,
                "status": holding.status.value,
                "locale": holding.locale,
                "version": holding.version,
            }
        )
    return holding.model_dump(mode="json")



@router.get("/workspaces/{ws_id}/holdings/{hld_id}")
def get_holding(ws_id: str, hld_id: str, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_BRIEF_RUN)
    h = store.holdings.get(hld_id)
    if not h:
        raise HTTPException(404, "holding not found")
    return h.model_dump(mode="json")


@router.post("/workspaces/{ws_id}/holdings/{hld_id}/transition")
def transition_holding(ws_id: str, hld_id: str, body: dict, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_BRIEF_RUN)
    h = store.holdings.get(hld_id)
    if not h:
        raise HTTPException(404, "holding not found")
    try:
        status = HoldingStatus(body.get("status"))
        transition(h, status)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e)) from e
    return h.model_dump(mode="json")
