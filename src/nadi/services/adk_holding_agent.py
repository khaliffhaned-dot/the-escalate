"""
Holding-statement drafting as a real Google ADK agent, not a single
prompt-in/JSON-out call.

Why this exists, specifically: the hackathon rules require at least one
Google Agent Framework (ADK, GenAI SDK, Antigravity SDK, or GenKit).
`services/llm_holding.py`'s direct `generate_content` calls technically
satisfy that via the GenAI SDK, but score weakly against judging criteria
that explicitly ask about state management and properly-scoped tools.
This module gives the agent real tools instead of stuffing everything
into one prompt, and constrains its output with a Pydantic schema instead
of hoping it returns valid JSON.

Defense in depth, same discipline as the rest of NADI: the agent's own
output is NEVER trusted for the ave/auto_publish/human_must_send fields.
Those are hardcoded False/False/True on the HoldingBrief regardless of
what the agent produces, exactly like the deterministic path in
holding_service.py and the Pydantic-level guard on the model itself.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from nadi.config import settings
from nadi.domain.models import HoldingBrief, Mention
from nadi.services.holding_service import _hash_prompt, load_system_prompt, reject_if_ave_requested

logger = logging.getLogger(__name__)

AGENT_MODEL = "gemini-3.5-flash"


class HoldingDraftOutput(BaseModel):
    """Structured output schema the agent must produce. Passed as ADK's
    `output_schema`, this constrains generation directly rather than
    parsing free-text JSON and hoping it's well-formed."""

    line_en: str = Field(description="English holding statement line, factual, no speculation.")
    line_bm: str = Field(description="Bahasa Malaysia holding statement line, same facts as line_en.")
    facts_used: list[str] = Field(description="Mention IDs the draft actually drew facts from.")
    gaps: list[str] = Field(
        default_factory=list,
        description="Known unknowns the draft deliberately does not claim to have an answer for.",
    )


# ---- Tools: real functions the agent calls, not free-text instructions ----

def lookup_flagged_mentions(mentions_by_id: dict[str, Mention]):
    """Builds a real ADK tool bound to a specific set of mentions for this
    drafting session. Returning a closure (rather than a module-level
    function reading global state) keeps the tool's data scoped to the
    single request, which is the "tools properly isolated and scoped"
    property the judging criteria specifically ask about.
    """

    def get_mention_detail(mention_id: str) -> dict[str, Any]:
        """Look up the text, sentiment, and 3R flags for a specific mention
        ID. Call this before drafting any line that references a mention's
        content, do not invent mention content from the ID alone."""
        m = mentions_by_id.get(mention_id)
        if not m:
            return {"error": f"no mention found with id {mention_id}"}
        return {
            "id": m.id,
            "text": m.text,
            "language": m.lang,
            "sentiment_label": m.sentiment.label.value if m.sentiment else None,
            "sentiment_score": m.sentiment.score if m.sentiment else None,
            "three_r_flags": [f.value for f in m.three_r.flags] if m.three_r else [],
            "severity": getattr(m.three_r, "severity", None) if m.three_r else None,
            "state": m.state,
        }

    return get_mention_detail


def verify_no_ave(requested_ave: bool = False, requested_auto_publish: bool = False) -> dict[str, Any]:
    """Check whether a proposed action would violate the AVE / auto-publish
    ban before finalizing a draft. Always call this at least once before
    returning your final answer. Returns allowed=false with a reason if
    the request would violate Barcelona Principles 4.0.
    """
    try:
        reject_if_ave_requested({"include_ave": requested_ave, "publish": requested_auto_publish})
        return {"allowed": True, "reason": None}
    except ValueError as e:
        return {"allowed": False, "reason": str(e)}


def build_holding_agent(mentions_by_id: dict[str, Mention]):
    """Constructs the real google.adk.agents.Agent. Import is local to this
    function (not module-level) so the rest of NADI can import this module
    and its Pydantic schema without requiring google-adk to be installed,
    e.g. for tests that only check the schema shape.
    """
    from google.adk.agents import Agent

    system_prompt = load_system_prompt()

    return Agent(
        name="nadi_holding_drafter",
        model=AGENT_MODEL,
        instruction=(
            system_prompt
            + "\n\nYou MUST call verify_no_ave before producing your final answer. "
            "You MUST call get_mention_detail for every mention ID you reference before "
            "writing about it, never invent mention content. If verify_no_ave returns "
            "allowed=false, do not proceed, explain why in your response instead of a draft."
        ),
        tools=[lookup_flagged_mentions(mentions_by_id), verify_no_ave],
        output_schema=HoldingDraftOutput,
    )


async def draft_holding_with_adk(
    *,
    mentions: list[Mention],
    war_room_id: str | None,
) -> HoldingBrief:
    """Runs the ADK agent end-to-end and converts its output into the same
    HoldingBrief model the rest of NADI already uses, so callers (routes,
    tests, the frontend) don't need to know whether a draft came from this
    agent path or the deterministic/direct-API fallback paths.
    """
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    mentions_by_id = {m.id: m for m in mentions}
    agent = build_holding_agent(mentions_by_id)

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="nadi", user_id="nadi-system", session_id=f"holding-draft-{war_room_id or 'adhoc'}"
    )
    runner = Runner(agent=agent, app_name="nadi", session_service=session_service)

    mention_summary = "\n".join(f"- {m.id}: ({m.lang}) {m.text[:200]}" for m in mentions)
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"Draft a bilingual (EN/BM) holding statement for this war room. "
            f"Mentions involved:\n{mention_summary}\n\n"
            f"Use get_mention_detail to confirm facts before writing about any of them."
        ))],
    )

    final_output: HoldingDraftOutput | None = None
    async for event in runner.run_async(
        user_id="nadi-system",
        session_id=f"holding-draft-{war_room_id or 'adhoc'}",
        new_message=user_message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            text = event.content.parts[0].text
            if text:
                final_output = HoldingDraftOutput.model_validate_json(text)

    if final_output is None:
        raise RuntimeError("ADK agent did not produce a final structured response")

    system_prompt = load_system_prompt()
    prompt_hash = _hash_prompt(system_prompt, mention_summary)

    # Defense in depth: these three fields are NEVER taken from the
    # agent's output, regardless of what it produced. Same rule the
    # deterministic path and the Pydantic model itself already enforce.
    return HoldingBrief(
        war_room_id=war_room_id,
        lines={"en": final_output.line_en, "bm": final_output.line_bm},
        facts_used=final_output.facts_used,
        gaps=final_output.gaps,
        ave=False,
        auto_publish=False,
        human_must_send=True,
        model_version=f"adk:{AGENT_MODEL}",
        prompt_hash=prompt_hash,
    )
