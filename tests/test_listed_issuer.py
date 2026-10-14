"""Listed-issuer war rooms: materiality, insider lock, clock board, halt prompt.

Runs offline, like the rest of the suite. Service tests pass `now` explicitly; API
tests pin the route module's clock so deadlines are deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from nadi.api.app import app
from nadi.api.routes import listed as listed_routes
from nadi.db.firestore_store import FirestoreStore
from nadi.domain.enums import WarRoomSeverity
from nadi.domain.listed import (
    ClockStatus,
    HaltDecision,
    ListedIssuerState,
    Market,
    MaterialityOutcome,
)
from nadi.domain.models import HoldingBrief
from nadi.services import listed_issuer as li
from nadi.services.war_room_service import open_war_room
from tests.test_firestore_store import FakeFirestore

KL = li.KL
# Monday 12 October 2026, 10:00 in Kuala Lumpur (a trading day, market open).
MON_10AM = datetime(2026, 10, 12, 10, 0, tzinfo=KL)


def _state(now: datetime = MON_10AM) -> ListedIssuerState:
    return li.new_state(market=Market.MAIN, actor="usr_test", now=now)


def _assess(**kw):
    base = dict(
        could_affect_price="yes",
        exceptional_and_confidential=False,
        leak_signals=[],
        assessed_by="usr_test",
        now=MON_10AM,
    )
    base.update(kw)
    return li.assess_materiality(**base)


# --------------------------------------------------------------- materiality
def test_not_material_takes_the_normal_route():
    a = _assess(could_affect_price="no")
    assert a.outcome == MaterialityOutcome.NOT_MATERIAL
    assert "normal communications route" in a.next_steps[0]


def test_material_without_an_established_exception_is_announced_now():
    assert _assess().outcome == MaterialityOutcome.ANNOUNCE_NOW
    # "not established" is not "established": None is treated like False.
    assert _assess(exceptional_and_confidential=None).outcome == MaterialityOutcome.ANNOUNCE_NOW


def test_unsure_is_treated_as_yes():
    a = _assess(could_affect_price="unsure")
    assert a.outcome == MaterialityOutcome.ANNOUNCE_NOW
    assert "unsure counts as yes" in a.rationale


def test_exception_holds_only_while_nothing_has_leaked():
    held = _assess(exceptional_and_confidential=True)
    assert held.outcome == MaterialityOutcome.WITHHOLD_AND_MONITOR
    assert any("insider list" in s for s in held.next_steps)

    leaked = _assess(exceptional_and_confidential=True, leak_signals=["  unusual volume  ", ""])
    assert leaked.outcome == MaterialityOutcome.ANNOUNCE_NOW
    assert leaked.leak_signals == ["unusual volume"]
    assert "ends the exception" in leaked.rationale


def test_announce_steps_put_bursa_first_and_mention_a_halt():
    steps = " ".join(_assess().next_steps)
    assert "Bursa first" in steps
    assert "trading halt" in steps


def test_bad_answer_is_rejected():
    with pytest.raises(li.ListedIssuerError):
        _assess(could_affect_price="maybe")


# --------------------------------------------------------------------- clocks
def test_catalogue_has_the_playbook_clocks_and_dependencies():
    keys = {c.key for c in _state().clocks}
    assert {"bursa_material", "bursa_uma", "pdpc_breach", "pdpc_individuals",
            "nacsa_report", "dosh_report"} <= keys
    dep = next(c for c in _state().clocks if c.key == "pdpc_individuals")
    assert dep.depends_on == "pdpc_breach"


def test_immediate_clock_is_running_not_overdue():
    s = _state()
    li.start_clock(s, "bursa_material", now=MON_10AM, owner="CoSec")
    row = next(r for r in li.clock_board(s, MON_10AM + timedelta(hours=3)) if r["key"] == "bursa_material")
    assert row["state"] == "running" and row["immediate"] is True
    assert row["elapsed_minutes"] == 180 and row["minutes_remaining"] is None


def test_timed_clock_counts_down_then_goes_overdue():
    s = _state()
    li.start_clock(s, "pdpc_breach", now=MON_10AM, owner="DPO")
    at = lambda h: next(r for r in li.clock_board(s, MON_10AM + timedelta(hours=h)) if r["key"] == "pdpc_breach")
    assert at(1)["state"] == "running" and at(1)["minutes_remaining"] == 71 * 60
    assert at(73)["state"] == "overdue" and at(73)["minutes_remaining"] == -60


def test_started_at_naive_is_read_as_kuala_lumpur_time():
    s = _state()
    c = li.start_clock(s, "pdpc_breach", now=MON_10AM, started_at=datetime(2026, 10, 12, 9, 0))
    assert c.started_at.utcoffset() == timedelta(hours=8)
    assert c.due_at == datetime(2026, 10, 15, 9, 0, tzinfo=KL)


def test_dependent_clock_waits_for_its_parent_then_runs_from_it():
    s = _state()
    with pytest.raises(li.ListedIssuerError, match="starts when pdpc_breach is done"):
        li.start_clock(s, "pdpc_individuals", now=MON_10AM)
    assert next(r for r in li.clock_board(s, MON_10AM) if r["key"] == "pdpc_individuals")["blocked"]

    li.start_clock(s, "pdpc_breach", now=MON_10AM)
    done_at = MON_10AM + timedelta(hours=30)
    li.complete_clock(s, "pdpc_breach", now=done_at)
    c = li.start_clock(s, "pdpc_individuals", now=done_at + timedelta(hours=5))
    assert c.started_at == done_at  # runs from the PDPC notification, not from "now"
    assert c.due_at == done_at + timedelta(days=7)


def test_source_document_clock_has_no_computed_deadline():
    s = _state()
    li.start_clock(s, "bursa_uma", now=MON_10AM)
    row = next(r for r in li.clock_board(s, MON_10AM) if r["key"] == "bursa_uma")
    assert row["due_at"] is None and row["deadline_in_source"] is True
    li.start_clock(s, "bursa_uma", now=MON_10AM, due_at=MON_10AM + timedelta(hours=4))  # restart with the query's deadline
    assert s.clocks[1].due_at == MON_10AM + timedelta(hours=4)


def test_clock_rules():
    s = _state()
    with pytest.raises(li.ListedIssuerError, match="not running"):
        li.complete_clock(s, "pdpc_breach", now=MON_10AM)
    with pytest.raises(li.ListedIssuerNotFound):
        li.start_clock(s, "no_such_clock", now=MON_10AM)
    with pytest.raises(li.ListedIssuerError, match="why"):
        li.mark_not_applicable(s, "nacsa_notice", note="  ")
    li.mark_not_applicable(s, "nacsa_notice", note="Not a designated NCII entity")
    assert next(c for c in s.clocks if c.key == "nacsa_notice").status == ClockStatus.NOT_APPLICABLE
    li.start_clock(s, "dosh_notice", now=MON_10AM)
    li.complete_clock(s, "dosh_notice", now=MON_10AM)
    with pytest.raises(li.ListedIssuerError, match="already done"):
        li.start_clock(s, "dosh_notice", now=MON_10AM)


# ------------------------------------------------------------- market and halt
@pytest.mark.parametrize(
    "when, expected",
    [
        (datetime(2026, 10, 12, 8, 45, tzinfo=KL), "pre_open"),
        (datetime(2026, 10, 12, 10, 0, tzinfo=KL), "open"),
        (datetime(2026, 10, 12, 12, 45, tzinfo=KL), "midday_break"),
        (datetime(2026, 10, 12, 14, 10, tzinfo=KL), "pre_open"),
        (datetime(2026, 10, 12, 16, 55, tzinfo=KL), "open"),
        (datetime(2026, 10, 12, 17, 30, tzinfo=KL), "closed"),
        (datetime(2026, 10, 12, 7, 0, tzinfo=KL), "closed"),
        (datetime(2026, 10, 17, 10, 0, tzinfo=KL), "closed"),  # Saturday
    ],
)
def test_market_status(when, expected):
    assert li.market_status(when)["status"] == expected


def test_market_status_converts_from_utc():
    # 02:00 UTC is 10:00 in Kuala Lumpur.
    assert li.market_status(datetime(2026, 10, 12, 2, 0, tzinfo=timezone.utc))["status"] == "open"


def _with(outcome_kwargs, now=MON_10AM):
    s = _state(now)
    s.materiality = _assess(now=now, **outcome_kwargs)
    return s


def test_halt_prompt_needs_an_assessment_and_ignores_non_material():
    assert li.halt_prompt(_state(), MON_10AM)["level"] == "none"
    assert li.halt_prompt(_with(dict(could_affect_price="no")), MON_10AM)["level"] == "none"


def test_halt_prompt_when_material_and_market_open():
    p = li.halt_prompt(_with({}), MON_10AM)
    assert p["level"] == "consider"
    assert "Practice Note 2" in " ".join(p["steps"])
    assert p["market"]["status"] == "open"


def test_halt_prompt_after_hours_and_when_withholding():
    evening = datetime(2026, 10, 12, 18, 0, tzinfo=KL)
    assert li.halt_prompt(_with({}, evening), evening)["level"] == "after_hours"
    assert li.halt_prompt(_with(dict(exceptional_and_confidential=True)), MON_10AM)["level"] == "watch"


def test_halt_prompt_goes_quiet_once_bursa_is_done_or_a_halt_is_recorded():
    s = _with({})
    li.start_clock(s, "bursa_material", now=MON_10AM)
    li.complete_clock(s, "bursa_material", now=MON_10AM)
    assert li.halt_prompt(s, MON_10AM)["level"] == "none"

    s2 = _with({})
    li.record_halt(s2, decision=HaltDecision.REQUESTED, actor="usr", note="", now=MON_10AM)
    assert li.halt_prompt(s2, MON_10AM)["level"] == "recorded"


def test_halt_record_follows_the_real_sequence():
    s = _state()
    with pytest.raises(li.ListedIssuerError):
        li.record_halt(s, decision=HaltDecision.APPROVED, actor="u", note="", now=MON_10AM)
    li.record_halt(s, decision=HaltDecision.REQUESTED, actor="u", note="phoned Bursa", now=MON_10AM)
    li.record_halt(s, decision=HaltDecision.APPROVED, actor="u", note="until 5pm", now=MON_10AM)
    li.record_halt(s, decision=HaltDecision.LIFTED, actor="u", note="announced", now=MON_10AM)
    assert s.halt.decision == HaltDecision.LIFTED and s.halt.resolved_at is not None
    with pytest.raises(li.ListedIssuerError):
        li.record_halt(s, decision=HaltDecision.NONE, actor="u", note="", now=MON_10AM)


# ---------------------------------------------------------------- insider lock
def test_adding_an_insider_starts_the_lock_and_rejects_duplicates():
    s = _state()
    assert s.insider_lock.active is False
    e = li.add_insider(s, name="Aisha Rahman", role="CFO", told_by="usr", told_at=MON_10AM, now=MON_10AM)
    assert s.insider_lock.active and s.insider_lock.started_at == MON_10AM
    with pytest.raises(li.ListedIssuerError, match="already on the insider list"):
        li.add_insider(s, name="aisha rahman", role="", told_by="usr", told_at=MON_10AM, now=MON_10AM)
    with pytest.raises(li.ListedIssuerError):
        li.add_insider(s, name="  ", role="", told_by="usr", told_at=MON_10AM, now=MON_10AM)
    assert e.notice_sent_at is None


def test_notice_must_be_sent_before_it_can_be_acknowledged():
    s = _state()
    e = li.add_insider(s, name="Lim", role="GC", told_by="u", told_at=MON_10AM, now=MON_10AM)
    with pytest.raises(li.ListedIssuerError, match="not been sent"):
        li.acknowledge_notice(s, e.id, now=MON_10AM)
    li.mark_notice_sent(s, e.id, now=MON_10AM)
    li.acknowledge_notice(s, e.id, now=MON_10AM + timedelta(minutes=5))
    assert e.acknowledged_at == MON_10AM + timedelta(minutes=5)
    with pytest.raises(li.ListedIssuerNotFound):
        li.mark_notice_sent(s, "ins_nope", now=MON_10AM)


def test_release_needs_a_note_and_reports_who_never_acknowledged():
    s = _state()
    a = li.add_insider(s, name="A", role="", told_by="u", told_at=MON_10AM, now=MON_10AM)
    li.add_insider(s, name="B", role="", told_by="u", told_at=MON_10AM, now=MON_10AM)
    li.mark_notice_sent(s, a.id, now=MON_10AM)
    li.acknowledge_notice(s, a.id, now=MON_10AM)
    with pytest.raises(li.ListedIssuerError, match="release note"):
        li.release_lock(s, actor="u", note=" ", now=MON_10AM)
    out = li.release_lock(s, actor="u", note="CoSec wrote to all insiders 18:00", now=MON_10AM)
    assert out["unacknowledged"] == ["B"] and s.insider_lock.active is False
    with pytest.raises(li.ListedIssuerError, match="not active"):
        li.release_lock(s, actor="u", note="again", now=MON_10AM)


def test_insider_notice_drafts_the_do_not_trade_wording():
    n = li.insider_notice(company="Sinar Berhad", code_name="Project Kuda", secretary="Nur A.",
                          channel="the war-room Signal group", now=MON_10AM)
    body = n["body"]
    assert "Do not buy, sell or otherwise deal" in body
    assert "Sinar Berhad" in body and "Project Kuda" in body and "war-room Signal group" in body
    assert "Capital Markets and Services Act 2007" in body
    assert "counsel" in n["review_note"]
    # Unfilled fields stay visible as placeholders instead of vanishing.
    assert "[Company]" in li.insider_notice(company="", code_name="", secretary="", channel="", now=MON_10AM)["body"]


# ------------------------------------------------------------------ invariants
def test_state_never_claims_to_file_with_a_regulator():
    assert ListedIssuerState(enabled_at=MON_10AM, enabled_by="u", auto_file=True).auto_file is False
    dumped = _state().model_dump(mode="json")
    dumped["auto_file"] = True  # a row tampered with in the database
    assert ListedIssuerState.model_validate(dumped).auto_file is False


# --------------------------------------------------------- holding integration
def _brief(**kw) -> HoldingBrief:
    base = dict(lines={"en": "x", "bm": "y"}, do_not_say=["a"], ops=[{"action": "op1", "owner_role": "editor", "sla_hours": 24, "objective_ids": []}])
    base.update(kw)
    return HoldingBrief(**base)


def test_context_line_never_contains_the_information_itself():
    assert li.listed_context_for_holding(None) is None
    assert li.listed_context_for_holding(_state()) is None  # no assessment yet
    ctx = li.listed_context_for_holding(_with({}))
    assert "announce_now" in ctx and "BEFORE" in ctx and "Insider lock: not started" in ctx
    assert "withheld" in li.listed_context_for_holding(_with(dict(exceptional_and_confidential=True))).lower()


def test_guard_applies_bursa_first_whatever_the_model_wrote():
    b = _brief()
    li.apply_listed_guard(b, _with({}))
    assert any("Bursa first" in d for d in b.do_not_say)
    assert any("material or not material" in d for d in b.do_not_say)
    assert b.ops[0]["owner_role"] == "ws_admin" and "Bursa announcement is released before" in b.ops[0]["action"]
    assert any("Insider lock not started" in g for g in b.gaps)
    assert any("not yet recorded as released" in g for g in b.gaps)


def test_guard_is_idempotent_caps_ops_and_skips_non_material():
    b = _brief(ops=[{"action": f"op{i}", "owner_role": "editor", "sla_hours": 24, "objective_ids": []} for i in range(5)])
    s = _with({})
    li.apply_listed_guard(b, s)
    li.apply_listed_guard(b, s)
    assert len(b.ops) == 5 and b.ops[0]["action"].startswith("Company Secretary")
    assert len(b.do_not_say) == len(set(b.do_not_say))

    untouched = _brief()
    li.apply_listed_guard(untouched, _with(dict(could_affect_price="no")))
    li.apply_listed_guard(untouched, None)
    assert untouched.do_not_say == ["a"] and len(untouched.ops) == 1


def test_guard_withhold_variant_forbids_hinting():
    b = _brief()
    li.apply_listed_guard(b, _with(dict(exceptional_and_confidential=True)))
    assert any("withheld information" in d for d in b.do_not_say)
    assert not any("Bursa announcement is not yet recorded" in g for g in b.gaps)


# ------------------------------------------------------------------------- API
client = TestClient(app)
H = {"X-Nadi-Role": "ws_admin"}
WS = "ws_aurora"


@pytest.fixture
def clock(monkeypatch):
    now = {"t": MON_10AM.astimezone(timezone.utc)}
    monkeypatch.setattr(listed_routes, "_now", lambda: now["t"])
    return now


def _room(listed: dict | None = None, **extra) -> str:
    body = {"title": "Listed-issuer test room", "severity": "high", **extra}
    if listed is not None:
        body["listed"] = listed
    res = client.post(f"/v1/workspaces/{WS}/war-rooms", json=body, headers=H)
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _url(wr: str, path: str = "") -> str:
    return f"/v1/workspaces/{WS}/war-rooms/{wr}/listed{path}"


def test_listed_is_off_by_default_and_other_routes_say_so(clock):
    wr = _room()
    view = client.get(_url(wr), headers=H).json()
    assert view["enabled"] is False and view["listed"] is None and view["board"] == []
    assert client.post(_url(wr, "/materiality"), json={"could_affect_price": "yes"}, headers=H).status_code == 409


def test_enable_is_idempotent_and_never_resets_a_running_board(clock):
    wr = _room()
    assert client.post(_url(wr, "/enable"), json={"market": "ace"}, headers=H).json()["listed"]["market"] == "ace"
    client.post(_url(wr, "/clocks/pdpc_breach/start"), json={"owner": "DPO"}, headers=H)
    again = client.post(_url(wr, "/enable"), json={"market": "main"}, headers=H).json()
    assert again["listed"]["market"] == "ace"
    assert next(r for r in again["board"] if r["key"] == "pdpc_breach")["state"] == "running"


def test_war_room_can_open_straight_into_listed_mode_and_rejects_a_bad_market(clock):
    wr = _room(listed={"market": "main"})
    assert client.get(_url(wr), headers=H).json()["enabled"] is True
    bad = client.post(f"/v1/workspaces/{WS}/war-rooms", json={"title": "x", "listed": {"market": "nasdaq"}}, headers=H)
    assert bad.status_code == 422


def test_full_flow_materiality_lock_clocks_halt_and_audit_trail(clock):
    wr = _room(listed={"market": "main"})

    mat = client.post(_url(wr, "/materiality"), json={"could_affect_price": "yes", "exceptional_and_confidential": False}, headers=H).json()
    assert mat["listed"]["materiality"]["outcome"] == "announce_now"
    assert mat["halt_prompt"]["level"] == "consider"

    ins = client.post(_url(wr, "/insiders"), json={"name": "Aisha Rahman", "role": "CFO"}, headers=H).json()
    iid = ins["listed"]["insider_lock"]["insiders"][0]["id"]
    assert ins["listed"]["insider_lock"]["active"] is True
    assert client.post(_url(wr, f"/insiders/{iid}/acknowledged"), headers=H).status_code == 422
    client.post(_url(wr, f"/insiders/{iid}/notice-sent"), headers=H)
    assert client.post(_url(wr, f"/insiders/{iid}/acknowledged"), headers=H).status_code == 200

    client.post(_url(wr, "/clocks/pdpc_breach/start"), json={"owner": "DPO"}, headers=H)
    clock["t"] += timedelta(hours=80)
    board = client.get(_url(wr), headers=H).json()["board"]
    assert next(r for r in board if r["key"] == "pdpc_breach")["state"] == "overdue"
    assert client.post(_url(wr, "/clocks/pdpc_individuals/start"), headers=H).status_code == 422

    assert client.post(_url(wr, "/halt"), json={"decision": "approved"}, headers=H).status_code == 422
    client.post(_url(wr, "/halt"), json={"decision": "requested", "note": "phoned Bursa"}, headers=H)

    room = client.get(f"/v1/workspaces/{WS}/war-rooms/{wr}", headers=H).json()
    actions = [d["action"] for d in room["decisions"]]
    for a in ("opened", "listed_enabled", "listed_materiality", "listed_insider_added",
              "listed_insider_notice_sent", "listed_insider_acknowledged", "listed_clock_started",
              "listed_halt_requested"):
        assert a in actions, a
    assert room["listed"]["auto_file"] is False


def test_release_lock_reports_unacknowledged_insiders(clock):
    wr = _room(listed={})
    client.post(_url(wr, "/insiders"), json={"name": "Lim"}, headers=H)
    assert client.post(_url(wr, "/insider-lock/release"), json={"note": ""}, headers=H).status_code == 422
    out = client.post(_url(wr, "/insider-lock/release"), json={"note": "told in writing 18:00"}, headers=H).json()
    assert out["unacknowledged"] == ["Lim"] and out["listed"]["insider_lock"]["active"] is False


def test_unknown_clock_and_unknown_insider_are_404(clock):
    wr = _room(listed={})
    assert client.post(_url(wr, "/clocks/nope/start"), headers=H).status_code == 404
    assert client.post(_url(wr, "/insiders/ins_nope/notice-sent"), headers=H).status_code == 404


def test_insider_notice_endpoint_returns_a_draft_only(clock):
    wr = _room(listed={})
    n = client.get(_url(wr, "/insider-notice"), params={"company": "Sinar Berhad"}, headers=H).json()
    assert "Sinar Berhad" in n["body"] and n["subject"].startswith("STRICTLY CONFIDENTIAL")


def test_rbac_viewer_cannot_touch_listed_controls(clock):
    wr = _room(listed={})
    viewer = {"X-Nadi-Role": "viewer"}
    assert client.get(_url(wr), headers=viewer).status_code == 403
    assert client.post(_url(wr, "/materiality"), json={"could_affect_price": "no"}, headers=viewer).status_code == 403


def test_closed_room_is_read_only_and_unknown_room_is_404(clock):
    wr = _room(listed={})
    client.post(f"/v1/workspaces/{WS}/war-rooms/{wr}/close", json={}, headers=H)
    assert client.post(_url(wr, "/materiality"), json={"could_affect_price": "no"}, headers=H).status_code == 409
    assert client.get(_url(wr), headers=H).status_code == 200
    assert client.get(_url("wr_nope"), headers=H).status_code == 404


def test_brief_for_a_listed_room_carries_the_bursa_first_guard(clock):
    wr = _room(listed={})
    client.post(_url(wr, "/materiality"), json={"could_affect_price": "yes"}, headers=H)
    res = client.post(
        f"/v1/workspaces/{WS}/briefs",
        json={"kind": "holding", "mention_ids": ["mnt_tg_imbi_01"], "war_room_id": wr, "use_llm": True},
        headers=H,
    )
    assert res.status_code == 200, res.text
    brief = res.json()
    assert any("Bursa first" in d for d in brief["do_not_say"])
    assert brief["ops"][0]["owner_role"] == "ws_admin"
    assert brief["human_must_send"] is True and brief["auto_publish"] is False
    # And without the listed assessment, nothing changes.
    plain = client.post(
        f"/v1/workspaces/{WS}/briefs",
        json={"kind": "holding", "mention_ids": ["mnt_tg_imbi_01"], "use_llm": False},
        headers=H,
    ).json()
    assert not any("Bursa" in d for d in plain["do_not_say"])


# ------------------------------------------------------- persistence (Firestore)
def test_listed_state_round_trips_through_the_firestore_store():
    fs = FirestoreStore(client=FakeFirestore())
    wr = open_war_room(org_id=fs.org.id, workspace_id=fs.workspace.id, title="t",
                       severity=WarRoomSeverity.HIGH, trigger={"kind": "manual"}, opened_by="u")
    wr.listed = _with({})
    li.add_insider(wr.listed, name="Aisha", role="CFO", told_by="u", told_at=MON_10AM, now=MON_10AM)
    fs.war_rooms[wr.id] = wr

    back = fs.war_rooms[wr.id]
    assert back.listed is not None
    assert back.listed.materiality.outcome == MaterialityOutcome.ANNOUNCE_NOW
    assert back.listed.insider_lock.insiders[0].name == "Aisha"
    assert back.listed.auto_file is False and len(back.listed.clocks) == len(li.CLOCK_KEYS)


# ------------------------------------------------------- persistence (SQL path)
def test_listed_state_round_trips_through_the_sql_repository():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from nadi.data.seed_aurora import ORG, WS
    from nadi.db.repository import TenantRepository
    from nadi.db.session import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    repo = TenantRepository(db, org_id=ORG.id, workspace_id=WS.id)

    wr = open_war_room(org_id=ORG.id, workspace_id=WS.id, title="t", severity=WarRoomSeverity.HIGH,
                       trigger={"kind": "manual"}, opened_by="u")
    wr.listed = _with({})
    repo.save_war_room(wr)
    first = repo.get_war_room(wr.id)
    assert first.listed.materiality.outcome == MaterialityOutcome.ANNOUNCE_NOW

    # The update branch persists it too, not just the insert.
    li.start_clock(first.listed, "pdpc_breach", now=MON_10AM)
    repo.save_war_room(first)
    db.expire_all()
    again = repo.get_war_room(wr.id)
    assert next(c for c in again.listed.clocks if c.key == "pdpc_breach").status == ClockStatus.RUNNING
    assert again.listed.auto_file is False

    # A war room without listed mode stays null.
    plain = open_war_room(org_id=ORG.id, workspace_id=WS.id, title="p", severity=WarRoomSeverity.LOW,
                          trigger={"kind": "manual"}, opened_by="u")
    repo.save_war_room(plain)
    assert repo.get_war_room(plain.id).listed is None


def test_sql_migration_adds_the_listed_column_with_the_no_auto_file_check():
    from pathlib import Path

    sql = (Path(__file__).resolve().parent.parent / "schemas" / "migrations"
           / "002_war_room_listed_issuer.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS listed JSONB" in sql
    assert "chk_war_room_listed_no_auto_file" in sql and "auto_file" in sql


def test_listed_routes_persist_through_a_store_that_returns_copies(monkeypatch, clock):
    """Firestore reads return fresh copies, so a route that only mutates the object it
    read would silently lose the change. Drive the routes against that kind of store."""
    fs = FirestoreStore(client=FakeFirestore())
    monkeypatch.setattr(listed_routes, "store", fs)
    wr = open_war_room(org_id=fs.org.id, workspace_id=fs.workspace.id, title="copy store",
                       severity=WarRoomSeverity.HIGH, trigger={"kind": "manual"}, opened_by="u")
    fs.war_rooms[wr.id] = wr

    assert client.post(_url(wr.id, "/enable"), json={}, headers=H).status_code == 200
    client.post(_url(wr.id, "/materiality"), json={"could_affect_price": "yes"}, headers=H)
    client.post(_url(wr.id, "/insiders"), json={"name": "Aisha"}, headers=H)
    client.post(_url(wr.id, "/clocks/bursa_material/start"), json={"owner": "CoSec"}, headers=H)

    saved = fs.war_rooms[wr.id]
    assert saved.listed.materiality.outcome == MaterialityOutcome.ANNOUNCE_NOW
    assert saved.listed.insider_lock.insiders[0].name == "Aisha"
    assert next(c for c in saved.listed.clocks if c.key == "bursa_material").owner == "CoSec"
    assert [d.action for d in saved.decisions][-1] == "listed_clock_started"


def test_contain_close_and_decisions_persist_through_a_copying_store(monkeypatch):
    """Same trap as the listed routes: against Firestore every read is a copy, so
    contain, close and add-decision were returning a change they never saved."""
    from nadi.api.routes import war_rooms as war_room_routes
    from nadi.domain.enums import WarRoomStatus

    fs = FirestoreStore(client=FakeFirestore())
    monkeypatch.setattr(war_room_routes, "store", fs)
    wr_id = next(iter(fs.war_rooms))
    base = f"/v1/workspaces/{WS}/war-rooms/{wr_id}"
    before = len(fs.war_rooms[wr_id].decisions)

    assert client.post(f"{base}/decisions", json={"action": "escalate", "note": "n"}, headers=H).status_code == 200
    assert len(fs.war_rooms[wr_id].decisions) == before + 1

    client.post(f"{base}/contain", json={"note": "contained"}, headers=H)
    assert fs.war_rooms[wr_id].status == WarRoomStatus.CONTAINED
    assert fs.war_rooms[wr_id].contained_at is not None

    client.post(f"{base}/close", json={"note": "done"}, headers=H)
    saved = fs.war_rooms[wr_id]
    assert saved.status == WarRoomStatus.CLOSED and saved.closed_at is not None
    assert [d.action for d in saved.decisions][-2:] == ["contained", "closed"]
