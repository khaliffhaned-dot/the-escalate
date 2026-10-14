from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from nadi.api.deps import get_ctx, need
from nadi.api.store import store
from nadi.domain.enums import WarRoomSeverity
from nadi.domain.listed import Market
from nadi.domain.models import ResidueItem
from nadi.domain.rbac import WS_WAR_ROOM
from nadi.services import listed_issuer
from nadi.services.war_room_service import append_decision, close, contain, open_war_room

router = APIRouter(prefix="/workspaces/{ws_id}/war-rooms", tags=["war-rooms"])


@router.get("")
def list_war_rooms(ws_id: str, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_WAR_ROOM)
    items = [w.model_dump(mode="json") for w in store.war_rooms.values() if w.workspace_id == ws_id]
    return {"items": items, "count": len(items)}


@router.get("/{wr_id}")
def get_war_room(ws_id: str, wr_id: str, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_WAR_ROOM)
    wr = store.war_rooms.get(wr_id)
    if not wr or wr.workspace_id != ws_id:
        raise HTTPException(404, "war room not found")
    return wr.model_dump(mode="json")


@router.post("")
def create_war_room(ws_id: str, body: dict, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_WAR_ROOM)
    if ws_id != store.workspace.id:
        raise HTTPException(404, "workspace not found")
    severity = WarRoomSeverity(body.get("severity", "medium"))
    residue = [ResidueItem.model_validate(r) for r in body.get("residue", [])]
    wr = open_war_room(
        org_id=store.org.id,
        workspace_id=ws_id,
        title=body.get("title") or "Untitled war room",
        severity=severity,
        trigger=body.get("trigger") or {"kind": "manual", "at": "2026-08-24T00:00:00Z"},
        opened_by=store.user.id,
        three_r=body.get("three_r"),
        residue=residue,
    )
    # Optional: open the room straight into listed-issuer mode, e.g.
    # {"listed": {"market": "main"}}. Can also be enabled later via /listed/enable.
    if body.get("listed") is not None:
        try:
            market = Market((body["listed"] or {}).get("market", "main"))
        except ValueError as e:
            raise HTTPException(422, "listed.market must be 'main' or 'ace'") from e
        wr.listed = listed_issuer.new_state(
            market=market, actor=store.user.id, now=datetime.now(timezone.utc)
        )
        append_decision(wr, store.user.id, "listed_enabled", f"{market.value} market")
    store.war_rooms[wr.id] = wr
    return wr.model_dump(mode="json")


@router.post("/{wr_id}/contain")
def contain_war_room(ws_id: str, wr_id: str, body: dict | None = None, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_WAR_ROOM)
    wr = store.war_rooms.get(wr_id)
    if not wr or wr.workspace_id != ws_id:
        raise HTTPException(404, "war room not found")
    contain(wr, store.user.id, (body or {}).get("note", ""))
    return wr.model_dump(mode="json")


@router.post("/{wr_id}/close")
def close_war_room(ws_id: str, wr_id: str, body: dict | None = None, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_WAR_ROOM)
    wr = store.war_rooms.get(wr_id)
    if not wr or wr.workspace_id != ws_id:
        raise HTTPException(404, "war room not found")
    close(wr, store.user.id, (body or {}).get("note", ""))
    return wr.model_dump(mode="json")


@router.post("/{wr_id}/decisions")
def add_decision(ws_id: str, wr_id: str, body: dict, ctx: dict = Depends(get_ctx)):
    need(ctx, WS_WAR_ROOM)
    wr = store.war_rooms.get(wr_id)
    if not wr or wr.workspace_id != ws_id:
        raise HTTPException(404, "war room not found")
    append_decision(wr, store.user.id, body.get("action", "note"), body.get("note", ""))
    return wr.model_dump(mode="json")
