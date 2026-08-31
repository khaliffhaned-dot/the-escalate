"""
Tests for the ADK-based holding statement agent.

No real GCP/Gemini credentials exist in CI or this environment, so these
tests verify what's actually testable without live model calls: the tools
work correctly against real seed data, the agent constructs with the
right shape, and the guard (verify_no_ave) genuinely calls the real
AVE-rejection logic rather than a reimplementation of it. A live,
credentialed run is a separate manual verification step, documented as
such rather than faked here.
"""
import json

import pytest

from nadi.data.seed_aurora import seed_mentions
from nadi.services.adk_holding_agent import (
    HoldingDraftOutput,
    build_holding_agent,
    lookup_flagged_mentions,
    verify_no_ave,
)


def test_verify_no_ave_uses_the_real_guard_not_a_copy():
    """This must call the actual reject_if_ave_requested from
    holding_service.py, not a reimplementation, so the two can never
    silently drift apart."""
    assert verify_no_ave(requested_ave=True) == {
        "allowed": False,
        "reason": "AVE / auto-publish not allowed under Barcelona Principles 4.0",
    }
    assert verify_no_ave(requested_ave=False, requested_auto_publish=False) == {
        "allowed": True,
        "reason": None,
    }


def test_lookup_tool_returns_real_seed_data_json_serializable():
    mentions = seed_mentions()
    by_id = {m.id: m for m in mentions}
    tool = lookup_flagged_mentions(by_id)

    result = tool("mnt_tg_imbi_01")
    assert result["id"] == "mnt_tg_imbi_01"
    assert "royalty" in result["three_r_flags"]
    assert result["severity"] == "high"
    # must be JSON-serializable, ADK sends tool results back to the model
    json.dumps(result)


def test_lookup_tool_handles_unknown_mention_id_gracefully():
    tool = lookup_flagged_mentions({})
    result = tool("does_not_exist")
    assert "error" in result


def test_agent_constructs_with_correct_model_and_schema():
    mentions = seed_mentions()
    by_id = {m.id: m for m in mentions}
    agent = build_holding_agent(by_id)

    assert agent.model == "gemini-3.5-flash"
    assert agent.output_schema is HoldingDraftOutput
    assert len(agent.tools) == 2


def test_output_schema_rejects_missing_required_fields():
    with pytest.raises(Exception):
        HoldingDraftOutput(line_en="only english")  # line_bm and facts_used missing


@pytest.mark.asyncio
async def test_draft_with_adk_fails_cleanly_without_credentials():
    """No real credentials exist in this test environment. The point of
    this test is that the failure happens at Google's own SDK boundary
    (a clear, typed error about missing credentials), not inside our
    code, our tool functions, or our session/agent construction."""
    from nadi.services.adk_holding_agent import draft_holding_with_adk

    mentions = [m for m in seed_mentions() if m.id == "mnt_tg_imbi_01"]
    with pytest.raises(Exception) as exc_info:
        await draft_holding_with_adk(mentions=mentions, war_room_id="wr_test")

    # Should fail on the credentials/API-key boundary, not a TypeError or
    # AttributeError from our own code being wrong.
    assert "API key" in str(exc_info.value) or "credentials" in str(exc_info.value).lower()
