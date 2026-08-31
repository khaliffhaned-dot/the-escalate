"""Store selection: in-memory demo scaffolding, or Firestore when configured."""

from __future__ import annotations

import logging

from nadi.config import settings
from nadi.data.seed_aurora import (
    ORG,
    USER,
    WS,
    seed_mentions,
    seed_snapshot,
    seed_war_room_and_holding,
)
from nadi.domain.models import EvaluationSnapshot, HoldingBrief, Mention, WarRoom
from nadi.services.scheduler import ReportScheduler

logger = logging.getLogger(__name__)


class MemoryStore:
    def __init__(self) -> None:
        self.org = ORG
        self.workspace = WS
        self.user = USER
        self.mentions: list[Mention] = seed_mentions()
        self.snapshots: dict[str, EvaluationSnapshot] = {}
        snap = seed_snapshot()
        self.snapshots[snap.id] = snap
        wr, hld = seed_war_room_and_holding()
        self.war_rooms: dict[str, WarRoom] = {wr.id: wr}
        self.holdings: dict[str, HoldingBrief] = {hld.id: hld}
        self.report_scheduler = ReportScheduler(persistent=False)


def build_store():
    """Selects the store backend.

    Firestore when configured, in-memory otherwise. A Firestore failure at
    startup degrades to the in-memory store rather than taking the service
    down — losing persistence is bad, refusing to boot during a demo is worse.
    The chosen backend is logged either way, so which one is live is never a
    guess.
    """
    if not settings.use_firestore:
        return MemoryStore()

    try:
        from nadi.db.firestore_store import FirestoreStore

        store = FirestoreStore(project_id=settings.firestore_project or None)
        logger.info("Store backend: Firestore (project=%s)", settings.firestore_project or "default")
        return store
    except Exception as err:
        logger.warning("Firestore unavailable, falling back to in-memory store: %s", err)
        return MemoryStore()


store = build_store()
