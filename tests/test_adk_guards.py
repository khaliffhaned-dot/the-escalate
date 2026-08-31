"""Regression tests for the ADK provider path's text-level guards.

These cover a real defect: the ADK branch in `generate_holding_with_llm`
used to `return` the agent's HoldingBrief directly, which skipped
`sanitize_and_guard_output` entirely. Because ADK is the *highest
priority* provider in auto-selection, that meant the path most likely to
run in a credentialed deployment was the one path with no TABLETOP marker
and no AVE scan of the model's own prose — and it dropped `do_not_say`
and `ops`, so it produced weaker safety guidance than the deterministic
fallback it outranked.
"""

from __future__ import annotations

import inspect

import pytest

from nadi.data.seed_aurora import seed_mentions
from nadi.domain.models import HoldingBrief
from nadi.services import adk_holding_agent, llm_holding
from nadi.services.adk_holding_agent import HoldingDraftOutput, draft_holding_with_adk


def _mentions():
    return [m for m in seed_mentions() if m.id == "mnt_tg_imbi_01"]


def _brief(**overrides) -> HoldingBrief:
    base = dict(
        lines={"en": "Agent English line.", "bm": "Baris Bahasa Malaysia."},
        facts_used=["mnt_tg_imbi_01"],
        do_not_say=["Do not invoke Royal institutions without legal clearance"],
        ops=[{"action": "Legal review", "owner_role": "ws_admin", "sla_hours": 12,
              "objective_ids": ["O4"]}],
        posture="self_regulated_not_directed",
        model_version="adk:gemini-3.5-flash",
        prompt_hash="sha256:test",
    )
    base.update(overrides)
    return HoldingBrief(**base)


@pytest.fixture
def fake_adk(monkeypatch):
    """Installs a stub agent and records the kwargs it was called with."""
    seen: dict = {}

    def _install(brief_factory=lambda **kw: _brief()):
        async def _stub(**kwargs):
            seen.update(kwargs)
            return brief_factory(**kwargs)

        monkeypatch.setattr(adk_holding_agent, "draft_holding_with_adk", _stub)
        return seen

    return _install


def test_adk_entrypoint_accepts_the_drafting_context():
    """If these params ever disappear again, the dispatcher's call silently
    TypeErrors and falls back to mock — the exact failure this guards."""
    params = inspect.signature(draft_holding_with_adk).parameters
    for name in ("mentions", "war_room_id", "locale", "audience", "tabletop", "extra_context"):
        assert name in params, f"draft_holding_with_adk lost the {name!r} parameter"


def test_output_schema_carries_full_safety_guidance():
    fields = HoldingDraftOutput.model_fields
    for name in ("line_en", "line_bm", "facts_used", "gaps", "do_not_say", "ops", "posture"):
        assert name in fields, f"HoldingDraftOutput lost the {name!r} field"


@pytest.mark.asyncio
async def test_adk_path_receives_tabletop_and_locale(fake_adk):
    seen = fake_adk()
    await llm_holding.generate_holding_with_llm(
        mentions=_mentions(), war_room_id=None, provider="adk",
        tabletop=True, locale="en", audience="internal",
        extra_context="drill scenario",
    )
    assert seen["tabletop"] is True
    assert seen["locale"] == "en"
    assert seen["audience"] == "internal"
    assert seen["extra_context"] == "drill scenario"


@pytest.mark.asyncio
async def test_adk_path_applies_tabletop_marker(fake_adk):
    """A simulation draft must never come back looking like a sendable one."""
    fake_adk()
    h = await llm_holding.generate_holding_with_llm(
        mentions=_mentions(), war_room_id=None, provider="adk", tabletop=True,
    )
    assert h.model_version == "adk:gemini-3.5-flash", "should not have fallen back"
    assert h.lines["en"].startswith("[TABLETOP — DO NOT SEND]")
    assert h.lines["bm"].startswith("[TABLETOP — JANGAN HANTAR]")


@pytest.mark.asyncio
async def test_adk_path_omits_marker_when_not_tabletop(fake_adk):
    fake_adk()
    h = await llm_holding.generate_holding_with_llm(
        mentions=_mentions(), war_room_id=None, provider="adk", tabletop=False,
    )
    assert not h.lines["en"].startswith("[TABLETOP")


@pytest.mark.asyncio
async def test_adk_path_preserves_do_not_say_and_ops(fake_adk):
    """The top-priority provider must not return thinner guidance than the
    deterministic fallback it outranks."""
    fake_adk()
    h = await llm_holding.generate_holding_with_llm(
        mentions=_mentions(), war_room_id=None, provider="adk",
    )
    assert h.do_not_say, "ADK path dropped do_not_say"
    assert h.ops, "ADK path dropped ops"
    assert h.posture == "self_regulated_not_directed"


@pytest.mark.asyncio
async def test_adk_ave_prose_is_caught_and_falls_back_safely(fake_adk):
    """If the model emits AVE language despite the system prompt, the guard
    must reject it and the caller must still get a safe, usable draft."""
    fake_adk(lambda **kw: _brief(lines={
        "en": "The campaign delivered RM500,000 in AVE media value.",
        "bm": "Kempen kami berjaya.",
    }))
    h = await llm_holding.generate_holding_with_llm(
        mentions=_mentions(), war_room_id=None, provider="adk",
    )
    assert h.model_version.endswith("-local"), "should have fallen back to the safe draft"
    assert "AVE" not in h.lines["en"]
    assert h.human_must_send is True
    assert h.ave is False


@pytest.mark.asyncio
async def test_adk_path_still_cannot_auto_publish(fake_adk):
    """Belt-and-braces: the invariant holds even if an agent tries to set it."""
    fake_adk(lambda **kw: _brief(auto_publish=True, ave=True, human_must_send=False))
    h = await llm_holding.generate_holding_with_llm(
        mentions=_mentions(), war_room_id=None, provider="adk",
    )
    assert h.auto_publish is False
    assert h.ave is False
    assert h.human_must_send is True
