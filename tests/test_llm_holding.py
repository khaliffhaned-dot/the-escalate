import pytest
from httpx import ASGITransport, AsyncClient

from nadi.api.app import app
from nadi.data.seed_aurora import seed_mentions
from nadi.domain.enums import HoldingStatus
from nadi.domain.models import HoldingBrief
from nadi.services.llm_holding import (
    build_user_prompt,
    generate_holding_with_llm,
    sanitize_and_guard_output,
)


@pytest.mark.asyncio
async def test_llm_holding_basic_mock_generation():
    mentions = [m for m in seed_mentions() if m.id == "mnt_tg_imbi_01"]
    h: HoldingBrief = await generate_holding_with_llm(
        mentions=mentions,
        war_room_id="wr_aurora_01",
        locale="bilingual",
        audience="press",
        tabletop=False,
    )
    assert h.ave is False
    assert h.auto_publish is False
    assert h.human_must_send is True
    assert "en" in h.lines and len(h.lines["en"]) > 0
    assert "bm" in h.lines and len(h.lines["bm"]) > 0
    assert h.facts_used == ["mnt_tg_imbi_01"]
    assert h.status == HoldingStatus.DRAFT
    assert len(h.ops) > 0
    assert len(h.do_not_say) > 0


@pytest.mark.asyncio
async def test_llm_holding_tabletop_mode():
    mentions = [m for m in seed_mentions() if m.id == "mnt_x_kl_01"]
    h = await generate_holding_with_llm(
        mentions=mentions,
        war_room_id=None,
        locale="bilingual",
        audience="press",
        tabletop=True,
    )
    assert h.lines["en"].startswith("[TABLETOP — DO NOT SEND]")
    assert h.lines["bm"].startswith("[TABLETOP — JANGAN HANTAR]")


def test_prompt_builder_includes_3r_and_mentions():
    mentions = [m for m in seed_mentions() if m.three_r.flags]
    prompt = build_user_prompt(
        mentions=mentions,
        locale="bilingual",
        audience="press",
        tabletop=False,
        extra_context="CEO requested 12h update cycle",
    )
    assert "Target Locale: bilingual" in prompt
    assert "Target Audience: press" in prompt
    assert "CEO requested 12h update cycle" in prompt
    assert "3R Flags Detected in Payload" in prompt
    assert "Mention #1" in prompt


def test_sanitize_guard_catches_ave_attempt():
    bad_data = {
        "lines": {
            "en": "Our campaign delivered RM 500,000 in AVE media value.",
            "bm": "Kempen kami mencapai nilai media tinggi.",
        },
        "gaps": [],
        "do_not_say": [],
        "ops": [],
        "posture": "defensive",
    }
    with pytest.raises(RuntimeError, match="AVE/EMV"):
        sanitize_and_guard_output(bad_data)


@pytest.mark.asyncio
async def test_vertex_selected_when_gcp_project_configured(monkeypatch):
    """auto provider selection should prefer vertex over the direct Gemini
    API key when a GCP project is configured, matching the Cloud Run
    deployment path. No real credentials exist in test, so this exercises
    the clean-failure-and-fallback path, not an actual Vertex AI call."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "fake-test-project")
    mentions = [m for m in seed_mentions() if m.id == "mnt_tg_imbi_01"]

    h = await generate_holding_with_llm(mentions=mentions, war_room_id=None)

    # No real ADC in the test environment, so the vertex call fails and
    # falls back to mock — the point of this test is that it fails
    # *cleanly* (no crash, no AVE leak) rather than that vertex actually
    # produced content here.
    assert h.ave is False
    assert h.auto_publish is False
    assert "en" in h.lines and len(h.lines["en"]) > 0


@pytest.mark.asyncio
async def test_direct_gemini_key_still_works_without_gcp_project(monkeypatch):
    """Without GOOGLE_CLOUD_PROJECT set, provider selection should not
    route to vertex at all, preserving the original direct-API-key path
    for local development without any GCP setup."""
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    mentions = [m for m in seed_mentions() if m.id == "mnt_tg_imbi_01"]

    h = await generate_holding_with_llm(mentions=mentions, war_room_id=None)
    # No gemini/openai key configured in test env either, so this lands
    # on mock — asserting it still produces a valid, AVE-free brief.
    assert h.ave is False
    assert "en" in h.lines and len(h.lines["en"]) > 0


@pytest.mark.asyncio
async def test_create_brief_api_route_with_llm():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/workspaces/ws_aurora/briefs",
            headers={"X-Nadi-Role": "ws_admin"},
            json={
                "kind": "holding",
                "mention_ids": ["mnt_tg_imbi_01"],
                "war_room_id": "wr_aurora_01",
                "use_llm": True,
                "locale": "bilingual",
                "audience": "press",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ave"] is False
        assert data["auto_publish"] is False
        assert data["human_must_send"] is True
        assert "en" in data["lines"]
        assert "bm" in data["lines"]
        assert data["facts_used"] == ["mnt_tg_imbi_01"]


@pytest.mark.asyncio
async def test_create_brief_rejects_ave_header_or_body():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/workspaces/ws_aurora/briefs",
            headers={"X-Nadi-Role": "ws_admin"},
            json={
                "kind": "holding",
                "include_ave": True,
            },
        )
        assert res.status_code == 422
