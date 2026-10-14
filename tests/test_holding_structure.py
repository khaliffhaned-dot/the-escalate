"""Holding statements follow one six-part structure, in EN and BM alike.

The six parts: what happened, care, what is confirmed, what is not yet confirmed,
what is being done, what to do plus the next update. These tests pin the prompt, the
two deterministic fallbacks and the AVE guard that those fallbacks run through.
"""

from __future__ import annotations

import re

import pytest

from nadi.data.seed_aurora import seed_mentions
from nadi.services.adk_holding_agent import HoldingDraftOutput
from nadi.services.holding_service import _AVE_RE, draft_holding_from_mentions, load_system_prompt
from nadi.services.llm_holding import (
    HOLDING_JSON_SCHEMA,
    _generate_mock_holding,
    build_user_prompt,
    generate_holding_with_llm,
    sanitize_and_guard_output,
)


def _flagged():
    return [m for m in seed_mentions() if m.three_r.flags]


def _plain():
    return [m for m in seed_mentions() if not m.three_r.flags]


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def test_system_prompt_names_the_six_parts_in_order():
    prompt = load_system_prompt()
    block = prompt[prompt.index("HOLDING LINES"): prompt.index("LISTED ISSUERS")]
    markers = ["What happened", "Care", "What is confirmed", "What is not yet confirmed",
               "What is being done", "What affected people should do"]
    positions = [block.index(m) for m in markers]
    assert positions == sorted(positions)
    assert [int(n) for n in re.findall(r"^(\d)\) ", block, re.M)] == [1, 2, 3, 4, 5, 6]
    assert "SAME ORDER IN EN AND BM" in block


def test_system_prompt_forbids_unsupported_no_evidence_claims_and_invented_times():
    prompt = load_system_prompt()
    assert 'Never write\n   "no evidence of X"' in prompt
    assert "Do not invent a time" in prompt


def test_system_prompt_carries_the_listed_issuer_rules():
    prompt = load_system_prompt()
    section = prompt[prompt.index("LISTED ISSUERS"):]
    assert "Bursa first" in section
    assert '"material" or "not material"' in section
    assert "hint at it" in section


def test_original_refusals_and_structure_are_untouched():
    prompt = load_system_prompt()
    for kept in ("HARD REFUSALS", "Human must send", "Do not calculate, estimate, or quote AVE",
                 "Do not apologise for a 3R matter", "STRUCTURE (always)"):
        assert kept in prompt


def test_user_prompt_and_schemas_point_at_the_six_parts():
    prompt = build_user_prompt(mentions=_flagged())
    assert "six parts" in prompt and "next update" in prompt
    assert "six parts" in HOLDING_JSON_SCHEMA["properties"]["lines"]["properties"]["en"]["description"]
    assert "six parts" in HoldingDraftOutput.model_fields["line_en"].description
    assert "six parts" in HoldingDraftOutput.model_fields["line_bm"].description


@pytest.mark.parametrize("mentions", [_flagged, _plain])
def test_mock_holding_has_all_six_parts_in_both_languages(mentions):
    out = _generate_mock_holding(mentions(), "bilingual", "press", False)
    en, bm = out["lines"]["en"], out["lines"]["bm"]
    # Same facts, same parts: sentence-for-sentence parity between EN and BM.
    assert len(_sentences(en)) == len(_sentences(bm)) == 7
    # Part 6 always commits to a next update, and never invents the time.
    assert "next update" in en.lower() and "[next update: time to be set by the desk]" in en
    assert "Kemas kini seterusnya" in bm and "[kemas kini seterusnya:" in bm
    # Part 4 says what is not yet confirmed, in plain words.
    assert re.search(r"not (yet )?confirmed|still establishing", en)
    assert re.search(r"belum disahkan|masih mengesahkan", bm)
    # No unsupported "no evidence" claim.
    assert "no evidence" not in en.lower()
    # The desk is told to fill the placeholder before sending.
    assert any("next-update time" in g for g in out["gaps"])


def test_deterministic_starter_follows_the_same_structure():
    h = draft_holding_from_mentions(mentions=_flagged()[:1], war_room_id=None)
    en, bm = h.lines["en"], h.lines["bm"]
    assert len(_sentences(en)) == len(_sentences(bm)) == 7
    assert "[next update: time to be set by the desk]" in en and "[kemas kini seterusnya:" in bm
    assert any("next-update time" in g for g in h.gaps)


def test_bm_does_not_assert_facts_the_english_lacks():
    """The old BM mock said the material was withdrawn "serta-merta" (immediately); the
    English never said immediately. Part 3 now matches in both languages."""
    out = _generate_mock_holding(_flagged(), "bilingual", "press", False)
    assert "serta-merta" not in out["lines"]["bm"]


@pytest.mark.asyncio
async def test_generated_brief_still_passes_the_guard_and_keeps_invariants():
    h = await generate_holding_with_llm(mentions=_flagged(), war_room_id=None, provider="mock")
    assert h.ave is False and h.auto_publish is False and h.human_must_send is True
    assert "next update" in h.lines["en"].lower()


@pytest.mark.parametrize(
    "text",
    ["We have confirmed the report.", "Save the date.", "The notice is available online.",
     "They will behave as agreed.", "Leave it with us."],
)
def test_ave_guard_does_not_trip_on_ordinary_words(text):
    """`ave` used to match inside have/save/available, so a perfectly normal
    holding sentence raised and a real model reply could 500 the route."""
    assert not _AVE_RE.search(text)
    sanitize_and_guard_output({"lines": {"en": text, "bm": "ok"}})


@pytest.mark.parametrize(
    "text",
    ["AVE of RM 1m", "an EMV figure", "advertising value equivalent", "media value of the story",
     "PR value in RM", "worth 2m ave."],
)
def test_ave_guard_still_catches_the_real_terms(text):
    assert _AVE_RE.search(text)
    with pytest.raises(RuntimeError, match="AVE/EMV"):
        sanitize_and_guard_output({"lines": {"en": text, "bm": "ok"}})
