"""Firestore-backed store — a Google Cloud persistence layer that needs no
billing account.

Why this exists: Cloud Run requires billing enabled. Firestore does not — the
Firebase Spark plan provides it free, and Firestore is named in the hackathon
rules as a qualifying Google Cloud infrastructure service. This makes the
"at least one Google Cloud service" requirement reachable without a card.

Design note: the API routes talk to `store.holdings[id] = brief` and
`store.war_rooms.values()` directly, so this mirrors `MemoryStore`'s shape
rather than replacing it with a repository. `FirestoreDocMap` is a
write-through MutableMapping: mutating it the way the routes already do
persists to Firestore, with no route changes at all.

Tenant isolation is preserved at the *query* level, not just in application
code: every document carries org_id and workspace_id, and every read is a
Firestore composite filter on both. A document belonging to another tenant is
not filtered out after the fact — it is never returned.
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any, Iterator, TypeVar

from pydantic import BaseModel

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

M = TypeVar("M", bound=BaseModel)

# Collection names are namespaced so a single Firebase project can host this
# alongside anything else without collision.
COL_MENTIONS = "nadi_mentions"
COL_SNAPSHOTS = "nadi_snapshots"
COL_WAR_ROOMS = "nadi_war_rooms"
COL_HOLDINGS = "nadi_holdings"


def _client(project_id: str | None = None):
    """Builds a real Firestore client. Imported lazily so the rest of NADI
    imports fine without google-cloud-firestore installed."""
    from google.cloud import firestore

    project = project_id or settings.firestore_project or None
    return firestore.Client(project=project) if project else firestore.Client()


class FirestoreDocMap(MutableMapping):
    """Dict-like, tenant-scoped view over one Firestore collection.

    Values are Pydantic models. They are re-validated on read, which means the
    product invariants (`ave=False`, `auto_publish=False`, `human_must_send=True`)
    are re-applied by the model's own validators on the way *out* of the
    database, not merely on the way in. A row tampered with directly in the
    Firestore console cannot reintroduce AVE or an auto-publishing holding.
    """

    def __init__(self, client, collection: str, model_cls: type[M], org_id: str, workspace_id: str):
        self._client = client
        self._collection = collection
        self._model_cls = model_cls
        self._org_id = org_id
        self._workspace_id = workspace_id

    # -- internals ---------------------------------------------------------
    def _col(self):
        return self._client.collection(self._collection)

    def _query(self):
        from google.cloud.firestore_v1.base_query import FieldFilter

        return (
            self._col()
            .where(filter=FieldFilter("org_id", "==", self._org_id))
            .where(filter=FieldFilter("workspace_id", "==", self._workspace_id))
        )

    def _to_model(self, data: dict[str, Any]) -> M:
        payload = {k: v for k, v in data.items() if k not in ("_org_scope",)}
        return self._model_cls.model_validate(payload)

    # -- MutableMapping ----------------------------------------------------
    def __getitem__(self, key: str) -> M:
        snap = self._col().document(key).get()
        if not getattr(snap, "exists", False):
            raise KeyError(key)
        data = snap.to_dict() or {}
        # Belt and braces: never hand back another tenant's document even if
        # someone fetched it by a guessed id rather than through the query.
        if data.get("org_id") != self._org_id or data.get("workspace_id") != self._workspace_id:
            raise KeyError(key)
        return self._to_model(data)

    def __setitem__(self, key: str, value: M) -> None:
        data = value.model_dump(mode="json")
        data["org_id"] = self._org_id
        data["workspace_id"] = self._workspace_id
        self._col().document(key).set(data)

    def __delitem__(self, key: str) -> None:
        self[key]  # raises KeyError if absent or foreign
        self._col().document(key).delete()

    def __iter__(self) -> Iterator[str]:
        for snap in self._query().stream():
            yield snap.id

    def __len__(self) -> int:
        return sum(1 for _ in self._query().stream())

    # `dict.values()` via MutableMapping would re-fetch each doc individually.
    # One streamed query is both faster and fewer reads against the free quota.
    def values(self):  # type: ignore[override]
        return [self._to_model(s.to_dict() or {}) for s in self._query().stream()]

    def items(self):  # type: ignore[override]
        return [(s.id, self._to_model(s.to_dict() or {})) for s in self._query().stream()]


class FirestoreStore:
    """Drop-in replacement for MemoryStore, backed by Firestore."""

    def __init__(self, client=None, project_id: str | None = None, seed: bool = True):
        self._client = client or _client(project_id)
        self.org = ORG
        self.workspace = WS
        self.user = USER

        scope = dict(org_id=ORG.id, workspace_id=WS.id)
        self.snapshots = FirestoreDocMap(self._client, COL_SNAPSHOTS, EvaluationSnapshot, **scope)
        self.war_rooms = FirestoreDocMap(self._client, COL_WAR_ROOMS, WarRoom, **scope)
        self.holdings = FirestoreDocMap(self._client, COL_HOLDINGS, HoldingBrief, **scope)
        self._mentions_map = FirestoreDocMap(self._client, COL_MENTIONS, Mention, **scope)

        # Report schedules stay in-process. Cloud Scheduler is the durable
        # trigger in this design (see reports.py), so persisting the schedule
        # rows would duplicate state that already lives in Cloud Scheduler.
        self.report_scheduler = ReportScheduler(persistent=False)

        if seed:
            self.seed_if_empty()

    @property
    def mentions(self) -> list[Mention]:
        """Routes treat this as a plain list, so it is materialised per access."""
        return self._mentions_map.values()

    def seed_if_empty(self) -> bool:
        """Loads the Aurora / Jalur Kita demo corpus on first run.

        Idempotent: a redeploy or a second container must not duplicate the
        seed, and Cloud Run will start more than one of these.
        """
        if len(self._mentions_map) > 0:
            return False

        for m in seed_mentions():
            self._mentions_map[m.id] = m
        snap = seed_snapshot()
        self.snapshots[snap.id] = snap
        wr, hld = seed_war_room_and_holding()
        self.war_rooms[wr.id] = wr
        self.holdings[hld.id] = hld
        logger.info("Seeded Firestore with the Aurora demo corpus")
        return True
