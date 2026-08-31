"""Firestore store: tenant scoping, write-through, invariants on read.

Runs entirely offline against a fake client that mimics the subset of the
Firestore API this store uses. No credentials, no network, no emulator — the
same rule as the rest of the suite.

Why Firestore at all: Cloud Run needs a billing account; Firestore on the
Firebase Spark plan does not, and the rules name Firestore as a qualifying
Google Cloud infrastructure service.
"""

from __future__ import annotations

import pytest

from nadi.db.firestore_store import COL_HOLDINGS, FirestoreDocMap, FirestoreStore
from nadi.domain.enums import HoldingStatus
from nadi.domain.models import HoldingBrief


# --------------------------------------------------------------- fake client
class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeDocRef:
    def __init__(self, store: dict, doc_id: str):
        self._store, self._id = store, doc_id

    def set(self, data):
        self._store[self._id] = dict(data)

    def get(self):
        return FakeSnapshot(self._id, self._store.get(self._id))

    def delete(self):
        self._store.pop(self._id, None)


class FakeQuery:
    def __init__(self, store: dict, filters: list):
        self._store, self._filters = store, filters

    def where(self, filter=None):  # noqa: A002 - mirrors the real signature
        return FakeQuery(self._store, self._filters + [filter])

    def stream(self):
        for doc_id, data in self._store.items():
            if all(data.get(f.field_path) == f.value for f in self._filters):
                yield FakeSnapshot(doc_id, data)


class FakeCollection(FakeQuery):
    def document(self, doc_id):
        return FakeDocRef(self._store, doc_id)


class FakeFirestore:
    """Mimics google.cloud.firestore.Client for the calls this store makes."""

    def __init__(self):
        self.data: dict[str, dict] = {}

    def collection(self, name):
        return FakeCollection(self.data.setdefault(name, {}), [])


@pytest.fixture
def client():
    return FakeFirestore()


@pytest.fixture
def store(client):
    return FirestoreStore(client=client)


def _holding(**kw) -> HoldingBrief:
    base = dict(
        lines={"en": "English line.", "bm": "Baris Bahasa Malaysia."},
        facts_used=["mnt_tg_imbi_01"],
        status=HoldingStatus.DRAFT,
    )
    base.update(kw)
    return HoldingBrief(**base)


# ------------------------------------------------------------------- seeding
def test_seeds_the_demo_corpus_on_first_run(store):
    assert len(store.mentions) == 3
    assert len(store.war_rooms) == 1
    assert len(store.snapshots) == 1
    assert len(store.holdings) == 1


def test_seeding_is_idempotent_across_restarts(client):
    """Cloud Run starts more than one container; a redeploy must not duplicate."""
    first = FirestoreStore(client=client)
    n_mentions, n_rooms = len(first.mentions), len(first.war_rooms)

    second = FirestoreStore(client=client)  # simulates a second instance
    assert second.seed_if_empty() is False
    assert len(second.mentions) == n_mentions
    assert len(second.war_rooms) == n_rooms


# -------------------------------------------------------------- write-through
def test_route_style_assignment_persists(store, client):
    """The routes do `store.holdings[id] = brief`. That must reach Firestore."""
    h = _holding()
    store.holdings[h.id] = h

    assert h.id in client.data[COL_HOLDINGS]
    reloaded = FirestoreStore(client=client).holdings[h.id]
    assert reloaded.lines["en"] == "English line."
    assert reloaded.id == h.id


def test_delete_and_len(store):
    h = _holding()
    store.holdings[h.id] = h
    before = len(store.holdings)
    del store.holdings[h.id]
    assert len(store.holdings) == before - 1
    with pytest.raises(KeyError):
        store.holdings[h.id]


# ------------------------------------------------------------ tenant scoping
def test_other_tenants_documents_are_never_returned(store, client):
    """Isolation is a query filter, not post-hoc filtering in Python."""
    mine = _holding()
    store.holdings[mine.id] = mine

    foreign = _holding()
    client.data[COL_HOLDINGS]["hld_foreign"] = {
        **foreign.model_dump(mode="json"),
        "id": "hld_foreign",
        "org_id": "org_someone_else",
        "workspace_id": "ws_someone_else",
    }

    ids = list(store.holdings)
    assert "hld_foreign" not in ids
    assert mine.id in ids
    assert all(h.id != "hld_foreign" for h in store.holdings.values())


def test_direct_id_lookup_cannot_cross_tenants(store, client):
    """Guessing a document id must not bypass the scope either."""
    client.data[COL_HOLDINGS]["hld_guessed"] = {
        **_holding().model_dump(mode="json"),
        "org_id": "org_someone_else",
        "workspace_id": "ws_someone_else",
    }
    with pytest.raises(KeyError):
        store.holdings["hld_guessed"]


def test_scope_fields_are_written_on_every_document(store, client):
    h = _holding()
    store.holdings[h.id] = h
    doc = client.data[COL_HOLDINGS][h.id]
    assert doc["org_id"] == store.org.id
    assert doc["workspace_id"] == store.workspace.id


# --------------------------------------------------- invariants on the way out
def test_tampered_document_cannot_reintroduce_auto_publish(store, client):
    """Someone editing the row directly in the Firestore console must not be
    able to produce a holding that publishes itself. Models re-validate on
    read, so the invariants are re-applied coming *out* of the database."""
    h = _holding()
    store.holdings[h.id] = h

    doc = client.data[COL_HOLDINGS][h.id]
    doc["ave"] = True
    doc["auto_publish"] = True
    doc["human_must_send"] = False

    reloaded = store.holdings[h.id]
    assert reloaded.ave is False
    assert reloaded.auto_publish is False
    assert reloaded.human_must_send is True


def test_values_returns_validated_models(store):
    h = _holding()
    store.holdings[h.id] = h
    for item in store.holdings.values():
        assert isinstance(item, HoldingBrief)
        assert item.human_must_send is True


# ------------------------------------------------------------------ plumbing
def test_docmap_is_scoped_to_its_collection(client):
    a = FirestoreDocMap(client, "col_a", HoldingBrief, "org_aurora", "ws_aurora")
    b = FirestoreDocMap(client, "col_b", HoldingBrief, "org_aurora", "ws_aurora")
    h = _holding()
    a[h.id] = h
    assert h.id in a
    assert h.id not in b
