"""Listed-issuer controls inside a war room: materiality, insider lock, clock board, halt record.

Everything here records or prompts. Nothing submits to Bursa or any regulator
(`ListedIssuerState.auto_file` is forced False), and every change is written to the
war room's decision log so the after-action review can replay who decided what, when.

Mutations write the war room back to the store. That is required, not tidy: with the
Firestore store every read returns a fresh copy, so an in-place change is lost unless
the room is assigned back.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nadi.api.deps import get_ctx, need
from nadi.api.store import store
from nadi.domain.enums import WarRoomStatus
from nadi.domain.listed import HaltDecision, Market
from nadi.domain.models import WarRoom
from nadi.domain.rbac import WS_WAR_ROOM
from nadi.services import listed_issuer as li
from nadi.services.war_room_service import append_decision

router = APIRouter(
    prefix="/workspaces/{ws_id}/war-rooms/{wr_id}/listed", tags=["listed-issuer"]
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- request bodies
class EnableBody(BaseModel):
    market: Market = Market.MAIN


class MaterialityBody(BaseModel):
    could_affect_price: Literal["yes", "no", "unsure"]
    exceptional_and_confidential: bool | None = None
    leak_signals: list[str] = Field(default_factory=list)


class ConfirmBody(BaseModel):
    note: str = ""


class InsiderBody(BaseModel):
    name: str
    role: str = ""
    told_by: str | None = None
    told_at: datetime | None = None


class ReleaseBody(BaseModel):
    note: str


class ClockStartBody(BaseModel):
    owner: str = ""
    started_at: datetime | None = None
    due_at: datetime | None = None


class ClockDoneBody(BaseModel):
    completed_at: datetime | None = None
    note: str = ""


class ClockNaBody(BaseModel):
    note: str


class HaltBody(BaseModel):
    decision: HaltDecision
    note: str = ""


# ------------------------------------------------------------------------ helpers
def _load(ctx: dict, ws_id: str, wr_id: str, *, mutate: bool) -> WarRoom:
    need(ctx, WS_WAR_ROOM)
    wr = store.war_rooms.get(wr_id)
    if not wr or wr.workspace_id != ws_id:
        raise HTTPException(404, "war room not found")
    if mutate and wr.status == WarRoomStatus.CLOSED:
        raise HTTPException(409, "war room is closed")
    return wr


def _listed(wr: WarRoom):
    if wr.listed is None:
        raise HTTPException(409, "listed-issuer mode is not enabled for this war room")
    return wr.listed


def _view(wr: WarRoom) -> dict:
    now = _now()
    state = wr.listed
    return {
        "enabled": state is not None,
        "now": now.isoformat(),
        "listed": state.model_dump(mode="json") if state else None,
        "board": li.clock_board(state, now) if state else [],
        "halt_prompt": li.halt_prompt(state, now) if state else None,
        "market": li.market_status(now),
    }


def _save(wr: WarRoom, action: str, note: str = "") -> dict:
    append_decision(wr, store.user.id, action, note)
    store.war_rooms[wr.id] = wr
    return _view(wr)


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except li.ListedIssuerNotFound as e:
        raise HTTPException(404, str(e)) from e
    except li.ListedIssuerError as e:
        raise HTTPException(422, str(e)) from e


# ------------------------------------------------------------------------- routes
@router.get("")
def get_listed(ws_id: str, wr_id: str, ctx: dict = Depends(get_ctx)):
    return _view(_load(ctx, ws_id, wr_id, mutate=False))


@router.post("/enable")
def enable_listed(ws_id: str, wr_id: str, body: EnableBody | None = None, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    if wr.listed is not None:
        return _view(wr)  # idempotent: never reset a running clock board
    market = (body or EnableBody()).market
    wr.listed = li.new_state(market=market, actor=store.user.id, now=_now())
    return _save(wr, "listed_enabled", f"{market.value} market")


@router.post("/materiality")
def run_materiality(ws_id: str, wr_id: str, body: MaterialityBody, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    state = _listed(wr)
    assessment = _guard(
        li.assess_materiality,
        could_affect_price=body.could_affect_price,
        exceptional_and_confidential=body.exceptional_and_confidential,
        leak_signals=body.leak_signals,
        assessed_by=store.user.id,
        now=_now(),
    )
    state.materiality = assessment
    return _save(wr, "listed_materiality", f"{assessment.outcome.value}: {assessment.rationale}")


@router.post("/materiality/confirm")
def confirm_materiality(ws_id: str, wr_id: str, body: ConfirmBody | None = None, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    state = _listed(wr)
    if state.materiality is None:
        raise HTTPException(422, "run the materiality check first")
    state.materiality.counsel_confirmed = True
    note = (body.note if body else "").strip()
    return _save(wr, "listed_materiality_confirmed", note or "Company Secretary / counsel confirmed")


@router.post("/insiders")
def add_insider(ws_id: str, wr_id: str, body: InsiderBody, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    state = _listed(wr)
    now = _now()
    entry = _guard(
        li.add_insider,
        state,
        name=body.name,
        role=body.role,
        told_by=body.told_by or store.user.id,
        told_at=li.aware(body.told_at, now),
        now=now,
    )
    return _save(wr, "listed_insider_added", f"{entry.name} ({entry.role or 'no role'})")


@router.get("/insider-notice")
def get_insider_notice(
    ws_id: str,
    wr_id: str,
    company: str = "",
    code_name: str = "",
    secretary: str = "",
    channel: str = "",
    ctx: dict = Depends(get_ctx),
):
    _load(ctx, ws_id, wr_id, mutate=False)
    return li.insider_notice(
        company=company, code_name=code_name, secretary=secretary, channel=channel, now=_now()
    )


@router.post("/insiders/{insider_id}/notice-sent")
def insider_notice_sent(ws_id: str, wr_id: str, insider_id: str, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    entry = _guard(li.mark_notice_sent, _listed(wr), insider_id, now=_now())
    return _save(wr, "listed_insider_notice_sent", entry.name)


@router.post("/insiders/{insider_id}/acknowledged")
def insider_acknowledged(ws_id: str, wr_id: str, insider_id: str, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    entry = _guard(li.acknowledge_notice, _listed(wr), insider_id, now=_now())
    return _save(wr, "listed_insider_acknowledged", entry.name)


@router.post("/insider-lock/release")
def release_insider_lock(ws_id: str, wr_id: str, body: ReleaseBody, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    result = _guard(li.release_lock, _listed(wr), actor=store.user.id, note=body.note, now=_now())
    note = body.note.strip()
    if result["unacknowledged"]:
        note += " | not acknowledged: " + ", ".join(result["unacknowledged"])
    out = _save(wr, "listed_insider_lock_released", note)
    out["unacknowledged"] = result["unacknowledged"]
    return out


@router.post("/clocks/{key}/start")
def start_clock(ws_id: str, wr_id: str, key: str, body: ClockStartBody | None = None, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    b = body or ClockStartBody()
    clock = _guard(
        li.start_clock, _listed(wr), key,
        now=_now(), owner=b.owner, started_at=b.started_at, due_at=b.due_at,
    )
    return _save(wr, "listed_clock_started", f"{clock.key} owner={clock.owner or '-'}")


@router.post("/clocks/{key}/done")
def finish_clock(ws_id: str, wr_id: str, key: str, body: ClockDoneBody | None = None, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    b = body or ClockDoneBody()
    clock = _guard(li.complete_clock, _listed(wr), key, now=_now(), completed_at=b.completed_at, note=b.note)
    return _save(wr, "listed_clock_done", clock.key)


@router.post("/clocks/{key}/not-applicable")
def clock_not_applicable(ws_id: str, wr_id: str, key: str, body: ClockNaBody, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    clock = _guard(li.mark_not_applicable, _listed(wr), key, note=body.note)
    return _save(wr, "listed_clock_not_applicable", f"{clock.key}: {clock.note}")


@router.post("/halt")
def record_halt(ws_id: str, wr_id: str, body: HaltBody, ctx: dict = Depends(get_ctx)):
    wr = _load(ctx, ws_id, wr_id, mutate=True)
    _guard(
        li.record_halt, _listed(wr),
        decision=body.decision, actor=store.user.id, note=body.note, now=_now(),
    )
    return _save(wr, f"listed_halt_{body.decision.value}", body.note)
