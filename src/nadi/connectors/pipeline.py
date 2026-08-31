"""Ingestion pipeline coordinator for multi-source listening."""

from __future__ import annotations

import logging
from typing import Any

from nadi.api.store import store
from nadi.config import settings
from nadi.connectors.base import BaseConnector
from nadi.connectors.rss_connector import MALAYSIAN_NEWS_FEEDS, RSSNewsConnector
from nadi.connectors.social_connector import SocialMediaConnector
from nadi.connectors.telegram_connector import TelegramConnector
from nadi.domain.models import Mention

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Manages connectors and synchronizes live mentions into NADI workspaces."""

    def __init__(self, org_id: str, workspace_id: str) -> None:
        self.org_id = org_id
        self.workspace_id = workspace_id
        self.rss_connectors = [
            RSSNewsConnector(
                outlet_name=f["outlet_name"],
                feed_url=f["url"],
                outlet_tier=f["outlet_tier"],
            )
            for f in MALAYSIAN_NEWS_FEEDS
        ]
        self.telegram_connector = TelegramConnector()
        self.social_connector = SocialMediaConnector()

    async def run_rss_sync(self, custom_connectors: list[RSSNewsConnector] | None = None) -> list[Mention]:
        """Polls Malaysian news RSS connectors and saves new mentions."""
        connectors = custom_connectors or self.rss_connectors
        ingested: list[Mention] = []

        existing_ids = {m.id for m in store.mentions}
        existing_urls = {m.url for m in store.mentions if m.url}

        for conn in connectors:
            try:
                raw_items = await conn.fetch_raw_items()
                for item in raw_items:
                    mention = conn.normalize_to_mention(
                        raw=item,
                        org_id=self.org_id,
                        workspace_id=self.workspace_id,
                    )
                    # Deduplicate by ID and URL
                    if mention.id not in existing_ids and (not mention.url or mention.url not in existing_urls):
                        store.mentions.insert(0, mention)
                        existing_ids.add(mention.id)
                        if mention.url:
                            existing_urls.add(mention.url)
                        ingested.append(mention)
            except Exception as e:
                logger.error("Error running connector %s: %s", conn.name, e)

        return ingested

    def ingest_webhook_payload(
        self,
        payload: dict[str, Any],
        source_type: str = "social",
    ) -> Mention:
        """Processes an incoming external webhook mention."""
        if source_type == "telegram":
            mention = self.telegram_connector.normalize_to_mention(
                raw=payload,
                org_id=self.org_id,
                workspace_id=self.workspace_id,
            )
        else:
            mention = self.social_connector.normalize_to_mention(
                raw=payload,
                org_id=self.org_id,
                workspace_id=self.workspace_id,
            )

        # Prepend to store
        existing_ids = {m.id for m in store.mentions}
        if mention.id not in existing_ids:
            store.mentions.insert(0, mention)

        return mention
