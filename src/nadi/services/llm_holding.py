"""LLM-backed holding statement generation conforming to AMEC / Barcelona Principles 4.0."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

from nadi.config import settings
from nadi.domain.enums import HoldingStatus
from nadi.domain.models import HoldingBrief, Mention
from nadi.services.holding_service import _AVE_RE, _hash_prompt, load_system_prompt, reject_if_ave_requested

logger = logging.getLogger(__name__)

HOLDING_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "object",
            "properties": {
                "en": {"type": "string", "description": "English holding statement lines"},
                "bm": {"type": "string", "description": "Bahasa Melayu holding statement lines"},
            },
            "required": ["en", "bm"],
        },
        "gaps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Known facts not yet verified or missing",
        },
        "do_not_say": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Taboo, ungrounded, or risky talking points",
        },
        "ops": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "owner_role": {"type": "string"},
                    "sla_hours": {"type": "number"},
                    "objective_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["action", "owner_role", "sla_hours"],
            },
            "description": "Operational next steps (max 5)",
        },
        "posture": {
            "type": "string",
            "description": "Framing posture, e.g. self_regulated_not_directed",
        },
    },
    "required": ["lines", "gaps", "do_not_say", "ops", "posture"],
}


def build_user_prompt(
    *,
    mentions: list[Mention],
    locale: str = "bilingual",
    audience: str = "press",
    tabletop: bool = False,
    extra_context: str | None = None,
) -> str:
    facts_summary = []
    all_3r_flags = set()
    for idx, m in enumerate(mentions, 1):
        flags = [f.value for f in m.three_r.flags]
        all_3r_flags.update(flags)
        facts_summary.append(
            f"Mention #{idx} (ID: {m.id}):\n"
            f"- Platform: {m.platform.value}\n"
            f"- Outlet/Handle: {m.outlet_name or m.author_handle or 'Unknown'}\n"
            f"- Language: {m.lang.value}\n"
            f"- 3R Flags: {', '.join(flags) if flags else 'None'}\n"
            f"- Excerpt/Text: {m.excerpt or m.text}\n"
        )


    mentions_block = "\n".join(facts_summary) if facts_summary else "No specific mentions provided. General holding inquiry."

    prompt = f"""DRAFT REQUEST CONTEXT:
Target Locale: {locale}
Target Audience: {audience}
Tabletop Simulation Mode: {'YES (prefix outputs with [TABLETOP — DO NOT SEND])' if tabletop else 'NO'}
3R Flags Detected in Payload: {', '.join(sorted(all_3r_flags)) if all_3r_flags else 'None'}
{f'Additional Comms Context: {extra_context}' if extra_context else ''}

SOURCED FACTS (MENTIONS):
{mentions_block}

TASK:
Produce a JSON response matching the following schema strictly:
{{
  "lines": {{
    "en": "<English holding lines, short, sopan, grounded in facts above>",
    "bm": "<Bahasa Melayu holding lines, natural phrasing, not mechanical translation>"
  }},
  "gaps": ["<gap 1>", "<gap 2>"],
  "do_not_say": ["<forbidden or ungrounded statement 1>", "<forbidden statement 2>"],
  "ops": [
    {{
      "action": "<Operational next step>",
      "owner_role": "editor|ws_admin|analyst",
      "sla_hours": 24,
      "objective_ids": ["O4"]
    }}
  ],
  "posture": "self_regulated_not_directed"
}}

IMPORTANT INVARIANTS:
1. Respond ONLY with valid JSON.
2. Absolutely NO AVE, EMV, or PR Value.
3. If facts are insufficient, keep lines minimal and list missing items in 'gaps'.
4. Do not invent government, PDRM, MCMC, or Royal directives.
"""
    return prompt


def _generate_mock_holding(
    mentions: list[Mention],
    locale: str,
    audience: str,
    tabletop: bool,
) -> dict[str, Any]:
    """High-quality deterministic generator when no external LLM API key is present."""
    flags = sorted({f.value for m in mentions for f in m.three_r.flags})
    has_royalty = "royalty" in flags
    has_religion = "religion" in flags
    has_race = "race" in flags

    if has_royalty or has_religion or has_race:
        en = (
            "We are aware of circulating materials and public commentary concerning a prior creative asset. "
            "The material in question has been withdrawn and is not part of our active campaign. "
            "Our team is currently auditing all residual distribution points and retail assets. "
            "We remain dedicated to respectful communication across all communities."
        )
        bm = (
            "Pihak kami mengambil maklum mengenai bahan yang sedang tular dan perbincangan awam berhubung aset kreatif terdahulu. "
            "Bahan berkenaan telah ditarik balik serta-merta dan bukan sebahagian daripada kempen aktif kami. "
            "Pasukan kami sedang menjalankan semakan menyeluruh ke atas semua baki saluran edaran dan aset runcit. "
            "Kami kekal komited terhadap komunikasi yang saling menghormati di kalangan semua lapisan masyarakat."
        )
    else:
        en = (
            "We are actively monitoring reports and community feedback regarding recent campaign materials. "
            "We are verifying the facts across our distribution channels and will provide updates as appropriate. "
            "Our commitment remains focused on clear and transparent communication."
        )
        bm = (
            "Pihak kami sedang memantau maklum balas dan laporan komuniti mengenai bahan kempen terkini. "
            "Kami sedang menyemak fakta merentasi seluruh saluran edaran kami dan akan mengemukakan perkembangan lanjut sekiranya perlu. "
            "Keutamaan kami adalah mengekalkan komunikasi yang jelas dan telus."
        )

    gaps = [
        "Verify full chain of asset distribution and physical POS presence",
        "Confirm timeline of initial social media post and engagement volume",
    ]
    do_not_say = [
        "Any calculation or reference to AVE / EMV / PR Value",
        "Claims that the creative was mandated or approved by any regulatory ministry",
        "Speculation regarding individual intent or unnamed parties",
    ]

    ops = [
        {
            "action": "Complete residual asset / POS sweep within 48h",
            "owner_role": "editor",
            "sla_hours": 48,
            "objective_ids": ["O4"],
        },
        {
            "action": "Maintain single-line holding stance on all reactive media queries",
            "owner_role": "editor",
            "sla_hours": 24,
            "objective_ids": ["O4"],
        },
    ]

    if has_royalty:
        ops.insert(
            0,
            {
                "action": "Comms and legal review of 3R sensitivity posture before any external issuance",
                "owner_role": "ws_admin",
                "sla_hours": 12,
                "objective_ids": ["O4"],
            },
        )
        do_not_say.append("Do not issue public apologies invoking Royal institutions without prior legal clearance")

    return {
        "lines": {"en": en, "bm": bm},
        "gaps": gaps,
        "do_not_say": do_not_say,
        "ops": ops,
        "posture": "self_regulated_not_directed",
    }


async def _call_vertex_ai(
    system_prompt: str,
    user_prompt: str,
    project: str,
    location: str,
    model: str = "gemini-3.5-flash",
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Calls Gemini through Vertex AI (Google Cloud), not the direct
    Gemini Developer API. Uses the `google-genai` SDK's Vertex AI mode,
    which authenticates via Application Default Credentials (gcloud auth
    application-default login locally, or the service account attached to
    Cloud Run in deployment), not an API key.
    """
    from google import genai
    from google.genai import types

    def _sync_call() -> str:
        client = genai.Client(vertexai=True, project=project, location=location)
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        return response.text

    import asyncio

    raw_text = await asyncio.to_thread(_sync_call)
    return json.loads(raw_text)


async def _call_gemini_api(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str = "gemini-3.5-flash",
    temperature: float = 0.2,
) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(url, json=payload)
        res.raise_for_status()
        data = res.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw_text)


async def _call_openai_api(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.2,
) -> dict[str, Any]:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(url, json=payload, headers=headers)
        res.raise_for_status()
        data = res.json()
        raw_text = data["choices"][0]["message"]["content"]
        return json.loads(raw_text)


def sanitize_and_guard_output(
    parsed: dict[str, Any],
    tabletop: bool = False,
) -> dict[str, Any]:
    lines = parsed.get("lines") or {}
    en = lines.get("en", "")
    bm = lines.get("bm", "")

    # AVE Guard
    if _AVE_RE.search(en) or _AVE_RE.search(bm):
        raise RuntimeError("LLM generated output containing prohibited AVE/EMV terms")

    # Tabletop formatting
    if tabletop:
        if not en.startswith("[TABLETOP — DO NOT SEND]"):
            en = f"[TABLETOP — DO NOT SEND] {en}"
        if not bm.startswith("[TABLETOP — JANGAN HANTAR]"):
            bm = f"[TABLETOP — JANGAN HANTAR] {bm}"

    lines["en"] = en
    lines["bm"] = bm
    parsed["lines"] = lines
    return parsed


async def generate_holding_with_llm(
    *,
    mentions: list[Mention],
    war_room_id: str | None = None,
    locale: str = "bilingual",
    audience: str = "press",
    tabletop: bool = False,
    extra_context: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> HoldingBrief:
    reject_if_ave_requested({})
    system_prompt = load_system_prompt()
    user_prompt = build_user_prompt(
        mentions=mentions,
        locale=locale,
        audience=audience,
        tabletop=tabletop,
        extra_context=extra_context,
    )

    selected_provider = provider or settings.llm_provider
    gemini_key = settings.gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    gcp_project = settings.gcp_project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")

    try:
        import google.adk  # noqa: F401

        adk_available = True
    except ImportError:
        adk_available = False

    parsed_result: dict[str, Any] | None = None
    resolved_model = model or settings.llm_model

    if selected_provider == "auto":
        if adk_available and (gcp_project or gemini_key):
            selected_provider = "adk"
        elif gcp_project:
            selected_provider = "vertex"
        elif gemini_key:
            selected_provider = "gemini"
        elif openai_key:
            selected_provider = "openai"
        else:
            selected_provider = "mock"

    if selected_provider == "adk" and adk_available:
        try:
            from nadi.services.adk_holding_agent import draft_holding_with_adk

            # A real tool-using ADK agent, not a prompt-in/JSON-out call. It
            # returns a HoldingBrief whose ave/auto_publish/human_must_send
            # booleans are already hardcoded inside that module.
            #
            # The *text* guards are a separate concern and must still run here:
            # returning this brief directly used to skip both the AVE scan of
            # the model's own prose and the TABLETOP marker, which meant a
            # simulation draft could come back indistinguishable from a real
            # one. Every provider now passes through sanitize_and_guard_output.
            brief = await draft_holding_with_adk(
                mentions=mentions,
                war_room_id=war_room_id,
                locale=locale,
                audience=audience,
                tabletop=tabletop,
                extra_context=extra_context,
            )
            brief.lines = sanitize_and_guard_output(
                {"lines": dict(brief.lines)}, tabletop=tabletop
            )["lines"]
            return brief
        except Exception as err:
            logger.warning("ADK agent run failed, falling back: %s", err)
            # fall through to vertex/gemini/openai/mock below

    if selected_provider in ("adk", "vertex") and gcp_project:
        try:
            parsed_result = await _call_vertex_ai(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                project=gcp_project,
                location=settings.gcp_location,
                model=resolved_model if "gemini" in resolved_model else "gemini-3.5-flash",
                temperature=settings.llm_temperature,
            )
        except Exception as err:
            logger.warning("Vertex AI call failed, falling back: %s", err)
            parsed_result = None

    if parsed_result is None and selected_provider in ("adk", "vertex", "gemini") and gemini_key:
        try:
            parsed_result = await _call_gemini_api(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                api_key=gemini_key,
                model=resolved_model if "gemini" in resolved_model else "gemini-3.5-flash",
                temperature=settings.llm_temperature,
            )
        except Exception as err:
            logger.warning("Gemini API call failed, falling back to mock provider: %s", err)
            parsed_result = None

    elif selected_provider == "openai" and openai_key:
        try:
            parsed_result = await _call_openai_api(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                api_key=openai_key,
                model=resolved_model if "gpt" in resolved_model else "gpt-4o-mini",
                temperature=settings.llm_temperature,
            )
        except Exception as err:
            logger.warning("OpenAI API call failed, falling back to mock provider: %s", err)
            parsed_result = None

    if parsed_result is None:
        parsed_result = _generate_mock_holding(
            mentions=mentions,
            locale=locale,
            audience=audience,
            tabletop=tabletop,
        )
        resolved_model = f"{settings.brief_model_version}-local"

    guarded = sanitize_and_guard_output(parsed_result, tabletop=tabletop)
    mention_ids = [m.id for m in mentions]
    mention_texts = " | ".join((m.excerpt or m.text)[:180] for m in mentions)

    return HoldingBrief(
        war_room_id=war_room_id,
        status=HoldingStatus.DRAFT,
        locale=locale,
        audience=audience,
        facts_used=mention_ids,
        gaps=guarded.get("gaps", []),
        lines=guarded.get("lines", {}),
        do_not_say=guarded.get("do_not_say", []),
        ops=guarded.get("ops", []),
        posture=guarded.get("posture", "self_regulated_not_directed"),
        auto_publish=False,
        ave=False,
        human_must_send=True,
        model_version=resolved_model,
        prompt_hash=_hash_prompt(system_prompt, mention_texts),
    )
