"""In-memory store for demo / pilot scaffolding."""

from __future__ import annotations

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


store = MemoryStore()
