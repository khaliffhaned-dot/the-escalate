"""Malaysian news RSS feed connector."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from nadi.connectors.base import BaseConnector
from nadi.domain.enums import PESO, Platform
from nadi.domain.models import Mention
from nadi.services.classifier import analyze_sentiment, classify_3r, detect_geography, detect_language

logger = logging.getLogger(__name__)

MALAYSIAN_NEWS_FEEDS = [
    {
        "outlet_name": "Bernama",
        "outlet_tier": "national",
        "url": "https://www.bernama.com/en/rss/general.xml",
    },
    {
        "outlet_name": "The Star",
        "outlet_tier": "national",
        "url": "https://www.thestar.com.my/rss/news/nation",
    },
    {
        "outlet_name": "Berita Harian",
        "outlet_tier": "national",
        "url": "https://www.bharian.com.my/berita.xml",
    },
    {
        "outlet_name": "Daily Express",
        "outlet_tier": "regional",
        "url": "http://www.dailyexpress.com.my/rss.cfm",
    },
    {
        "outlet_name": "Borneo Post",
        "outlet_tier": "regional",
        "url": "https://www.theborneopost.com/feed/",
    },
]


class RSSNewsConnector(BaseConnector):
    """Fetches and parses Malaysian news RSS and Atom feeds."""

    def __init__(
        self,
        outlet_name: str,
        feed_url: str,
        outlet_tier: str = "national",
    ) -> None:
        super().__init__(name=f"rss_{outlet_name.lower().replace(' ', '_')}", source_type="news_rss")
        self.outlet_name = outlet_name
        self.feed_url = feed_url
        self.outlet_tier = outlet_tier

    async def fetch_raw_items(self) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                res = await client.get(self.feed_url)
                res.raise_for_status()
                return self.parse_xml_feed(res.text)
        except Exception as err:
            logger.warning("Failed to fetch RSS from %s: %s", self.feed_url, err)
            return []

    def parse_xml_feed(self, xml_content: str) -> list[dict[str, Any]]:
        items = []
        try:
            root = ET.fromstring(xml_content)
            # Standard RSS channel/item
            channel = root.find("channel")
            if channel is not None:
                for item in channel.findall("item"):
                    title = item.findtext("title", "")
                    description = item.findtext("description", "")
                    link = item.findtext("link", "")
                    pub_date = item.findtext("pubDate", "")
                    items.append({
                        "title": title,
                        "text": f"{title}\n{description}".strip(),
                        "url": link,
                        "pub_date": pub_date,
                    })
            else:
                # Atom feed entries
                for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                    title = entry.findtext("{http://www.w3.org/2005/Atom}title", "")
                    summary = entry.findtext("{http://www.w3.org/2005/Atom}summary", "")
                    link_elem = entry.find("{http://www.w3.org/2005/Atom}link")
                    link = link_elem.attrib.get("href", "") if link_elem is not None else ""
                    items.append({
                        "title": title,
                        "text": f"{title}\n{summary}".strip(),
                        "url": link,
                        "pub_date": "",
                    })
        except Exception as e:
            logger.error("XML parse error on RSS feed %s: %s", self.outlet_name, e)
        return items

    def normalize_to_mention(
        self,
        raw: dict[str, Any],
        org_id: str,
        workspace_id: str,
    ) -> Mention:
        text = raw.get("text") or raw.get("title") or ""
        url = raw.get("url")
        # Deterministic mention ID hash from URL or text
        content_hash = hashlib.md5((url or text).encode()).hexdigest()[:10]
        mention_id = f"mnt_rss_{content_hash}"

        state, is_east_my = detect_geography(text)
        three_r = classify_3r(text)
        sentiment = analyze_sentiment(text)
        lang = detect_language(text)

        codes = []
        if is_east_my:
            codes.append("east_my")
        if three_r.flags:
            codes.append("three_r_flagged")

        return Mention(
            id=mention_id,
            org_id=org_id,
            workspace_id=workspace_id,
            published_at=datetime.now(timezone.utc),
            ingested_at=datetime.now(timezone.utc),
            platform=Platform.NEWS,
            lang=lang,
            script="latin" if lang in [lang.EN, lang.BM, lang.MIXED] else "native",
            url=url,
            author_name=self.outlet_name,
            author_kind="journalist",
            outlet_name=self.outlet_name,
            outlet_tier=self.outlet_tier,
            text=text,
            excerpt=raw.get("title") or text[:120],
            sentiment=sentiment,
            three_r=three_r,
            state=state,
            east_my=is_east_my,
            engagement={},
            codes=codes,
            peso=PESO.EARNED,
            starred=False,
        )
