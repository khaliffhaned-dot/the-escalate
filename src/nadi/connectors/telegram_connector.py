"""Telegram public channel message parser & webhook normalizer."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from nadi.connectors.base import BaseConnector
from nadi.domain.enums import PESO, Platform
from nadi.domain.models import Mention
from nadi.services.classifier import analyze_sentiment, classify_3r, detect_geography, detect_language


class TelegramConnector(BaseConnector):
    """Processes broadcast alerts and messages from public Telegram channels."""

    def __init__(self, channel_name: str = "Telegram Public Feed") -> None:
        super().__init__(name="telegram_public", source_type="telegram")
        self.channel_name = channel_name

    async def fetch_raw_items(self) -> list[dict[str, Any]]:
        # Telegram live polling via bot API or webhook
        return []

    def normalize_to_mention(
        self,
        raw: dict[str, Any],
        org_id: str,
        workspace_id: str,
    ) -> Mention:
        text = raw.get("text") or raw.get("caption") or ""
        channel = raw.get("chat_title") or raw.get("channel_username") or self.channel_name
        message_id = raw.get("message_id")
        
        content_hash = hashlib.md5(f"{channel}_{message_id}_{text[:50]}".encode()).hexdigest()[:10]
        mention_id = f"mnt_tg_{content_hash}"

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
            platform=Platform.TELEGRAM,
            lang=lang,
            script="latin" if lang in [lang.EN, lang.BM, lang.MIXED] else "native",
            url=raw.get("url"),
            author_handle=raw.get("author_handle") or f"@{channel}",
            author_name=raw.get("author_name") or channel,
            author_kind="public",
            outlet_name=channel,
            text=text,
            excerpt=text[:140],
            sentiment=sentiment,
            three_r=three_r,
            state=state,
            east_my=is_east_my,
            engagement=raw.get("engagement") or {},
            codes=codes,
            peso=PESO.SHARED,
            starred=False,
        )
