import pytest
from httpx import ASGITransport, AsyncClient

from nadi.api.app import app
from nadi.api.store import store
from nadi.connectors.pipeline import IngestionPipeline
from nadi.connectors.rss_connector import RSSNewsConnector
from nadi.connectors.social_connector import SocialMediaConnector
from nadi.connectors.telegram_connector import TelegramConnector
from nadi.domain.enums import Lang, Platform, ThreeRFlag
from nadi.services.classifier import (
    analyze_sentiment,
    classify_3r,
    detect_geography,
    detect_language,
)

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Bernama General News</title>
    <link>https://www.bernama.com</link>
    <description>Malaysian National News Agency</description>
    <item>
      <title>Sabah SME producers achieve record exports in KK festival</title>
      <link>https://www.bernama.com/en/news-101.php</link>
      <description>Producers in Kota Kinabalu, Sabah celebrate massive growth with great optimism and support.</description>
      <pubDate>Mon, 24 Aug 2026 08:00:00 +0800</pubDate>
    </item>
    <item>
      <title>Istana Negara issues statement regarding official ceremonies</title>
      <link>https://www.bernama.com/en/news-102.php</link>
      <description>Yang di-Pertuan Agong graces national event in Kuala Lumpur.</description>
      <pubDate>Mon, 24 Aug 2026 09:00:00 +0800</pubDate>
    </item>
  </channel>
</rss>
"""


def test_classifier_3r_detection():
    r1 = classify_3r("Kenyataan rasmi daripada pihak Istana dan Yang di-Pertuan Agong.")
    assert ThreeRFlag.ROYALTY in r1.flags
    assert r1.severity == "high"

    r2 = classify_3r("Perbincangan isu agama dan pensijilan halal JAKIM.")
    assert ThreeRFlag.RELIGION in r2.flags

    r3 = classify_3r("Isu hak kaum Melayu dan perkauman di media sosial.")
    assert ThreeRFlag.RACE in r3.flags

    r4 = classify_3r("Kempen jualan Merdeka di pusat beli-belah Pavillion.")
    assert len(r4.flags) == 0
    assert r4.severity == "none"


def test_detect_geography_east_vs_west_my():
    state1, is_east1 = detect_geography("Pesta buah di Kota Kinabalu, Sabah meriah.")
    assert state1 == "Sabah"
    assert is_east1 is True

    state2, is_east2 = detect_geography("Projek pembinaan jambatan di Kuching, Sarawak.")
    assert state2 == "Sarawak"
    assert is_east2 is True

    state3, is_east3 = detect_geography("Pameran automotif di Shah Alam, Selangor.")
    assert state3 == "Selangor"
    assert is_east3 is False


def test_detect_language_multilingual():
    assert detect_language("Kami telah melancarkan kempen baharu untuk semua pengguna.") == Lang.BM
    assert detect_language("We have launched the new media initiative for our community.") == Lang.EN
    assert detect_language("Kenyataan ini is very important for our campaign.") == Lang.MIXED


def test_rss_connector_parsing():
    conn = RSSNewsConnector(outlet_name="Bernama", feed_url="https://test.com/rss.xml", outlet_tier="national")
    raw_items = conn.parse_xml_feed(SAMPLE_RSS_XML)
    assert len(raw_items) == 2
    assert "Sabah SME producers" in raw_items[0]["title"]

    mention = conn.normalize_to_mention(raw_items[0], org_id="org_aurora", workspace_id="ws_aurora")
    assert mention.platform == Platform.NEWS
    assert mention.outlet_name == "Bernama"
    assert mention.east_my is True
    assert mention.state == "Sabah"
    assert "east_my" in mention.codes


def test_telegram_and_social_connectors():
    tg_conn = TelegramConnector()
    tg_mention = tg_conn.normalize_to_mention(
        {
            "text": "Breaking: Istana Negara update on Jalan Imbi royal delegation.",
            "chat_title": "Buletin Utama Rasmi",
            "message_id": "99182",
        },
        org_id="org_aurora",
        workspace_id="ws_aurora",
    )
    assert tg_mention.platform == Platform.TELEGRAM
    assert ThreeRFlag.ROYALTY in tg_mention.three_r.flags

    social_conn = SocialMediaConnector()
    x_mention = social_conn.normalize_to_mention(
        {
            "platform": "x",
            "text": "SME products on pack looking great! #BanggaBuatanMalaysia",
            "author_handle": "@malaysia_fan",
        },
        org_id="org_aurora",
        workspace_id="ws_aurora",
    )
    assert x_mention.platform == Platform.X
    assert x_mention.author_handle == "@malaysia_fan"


@pytest.mark.asyncio
async def test_ingest_webhook_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/workspaces/ws_aurora/mentions/ingest/webhook",
            headers={"X-Nadi-Role": "ws_admin"},
            json={
                "platform": "x",
                "text": "Sabah tourism campaign received positive feedback in KK.",
                "author_handle": "@sabah_watcher",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["mention"]["east_my"] is True
        assert data["mention"]["state"] == "Sabah"
