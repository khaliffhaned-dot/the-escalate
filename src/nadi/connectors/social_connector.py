"""Social media connector for public posts and webhook payloads (X, Meta, TikTok)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from nadi.connectors.base import BaseConnector
from nadi.domain.enums import PESO, Platform
from nadi.domain.models import Mention
from nadi.services.classifier import analyze_sentiment, classify_3r, detect_geography, detect_language


class SocialMediaConnector(BaseConnector):
    """Processes social media posts and webhook payloads."""

    def __init__(self) -> None:
        super().__init__(name="social_webhook", source_type="social")

    async def fetch_raw_items(self) -> list[dict[str, Any]]:
        return []

    def normalize_to_mention(
        self,
        raw: dict[str, Any],
        org_id: str,
        workspace_id: str,
    ) -> Mention:
        text = raw.get("text") or raw.get("content") or ""
        platform_str = str(raw.get("platform", "x")).lower()

        if "facebook" in platform_str or "meta" in platform_str:
            platform = Platform.FACEBOOK
        elif "instagram" in platform_str:
            platform = Platform.INSTAGRAM
        elif "tiktok" in platform_str:
            platform = Platform.TIKTOK
        elif "youtube" in platform_str:
            platform = Platform.YOUTUBE
        elif "telegram" in platform_str:
            platform = Platform.TELEGRAM
        elif "news" in platform_str:
            platform = Platform.NEWS
        elif "reddit" in platform_str:
            platform = Platform.REDDIT
        else:
            platform = Platform.X

        content_hash = hashlib.md5(f"{platform.value}_{raw.get('id')}_{text[:60]}".encode()).hexdigest()[:10]
        mention_id = f"mnt_{platform.value}_{content_hash}"

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
            platform=platform,
            lang=lang,
            script="latin" if lang in [lang.EN, lang.BM, lang.MIXED] else "native",
            url=raw.get("url"),
            author_handle=raw.get("author_handle"),
            author_name=raw.get("author_name"),
            author_kind=raw.get("author_kind", "public"),
            outlet_name=raw.get("outlet_name"),
            outlet_tier=raw.get("outlet_tier"),
            text=text,
            excerpt=text[:140],
            sentiment=sentiment,
            three_r=three_r,
            state=state,
            east_my=is_east_my,
            engagement=raw.get("engagement") or {},
            codes=codes,
            peso=PESO.SHARED,
            starred=bool(raw.get("starred")),
        )
