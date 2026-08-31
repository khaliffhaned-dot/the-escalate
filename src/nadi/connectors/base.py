"""Base connector contract for ingestion feeds."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nadi.domain.models import Mention


class BaseConnector(ABC):
    """Abstract interface for all ingestion sources."""

    def __init__(self, name: str, source_type: str) -> None:
        self.name = name
        self.source_type = source_type

    @abstractmethod
    async def fetch_raw_items(self) -> list[dict[str, Any]]:
        """Fetches raw payload items from the source."""
        pass

    @abstractmethod
    def normalize_to_mention(
        self,
        raw: dict[str, Any],
        org_id: str,
        workspace_id: str,
    ) -> Mention:
        """Transforms a raw item into a NADI Mention."""
        pass
