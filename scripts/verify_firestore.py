"""Is Firestore actually connected, and is tenant isolation real?

Requirement 3 of the hackathon rules is "at least one Google Cloud
infrastructure service". This proves Firestore is genuinely that, against a
real project rather than the fake client the test suite uses.

    python scripts/verify_firestore.py

Expects GOOGLE_APPLICATION_CREDENTIALS, NADI_USE_FIRESTORE and
NADI_FIRESTORE_PROJECT. Prints no credential material.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main() -> int:
    cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    proj = os.getenv("NADI_FIRESTORE_PROJECT")
    on = os.getenv("NADI_USE_FIRESTORE")

    print("Configuration")
    print(f"  NADI_USE_FIRESTORE            : {on or 'not set'}")
    print(f"  NADI_FIRESTORE_PROJECT        : {proj or 'not set'}")
    print(f"  GOOGLE_APPLICATION_CREDENTIALS: "
          f"{'set, file exists' if cred and os.path.isfile(cred) else (cred and 'set, FILE NOT FOUND') or 'not set'}")

    if not (on and proj and cred):
        print("\nMissing configuration. In PowerShell:")
        print('  $env:GOOGLE_APPLICATION_CREDENTIALS="C:\\path\\to\\serviceAccount.json"')
        print('  $env:NADI_USE_FIRESTORE="true"')
        print(f'  $env:NADI_FIRESTORE_PROJECT="{proj or "your-project-id"}"')
        return 1

    print("\nConnecting…")
    from nadi.db.firestore_store import COL_HOLDINGS, FirestoreStore
    from nadi.domain.models import HoldingBrief

    try:
        store = FirestoreStore(project_id=proj)
    except Exception as err:
        print(f"  FAILED: {type(err).__name__}: {str(err)[:200]}")
        print("\n  Common causes: Firestore database not created yet in the")
        print("  Firebase console (Build -> Firestore Database -> Create),")
        print("  or the service account lacks the Datastore User role.")
        return 1

    print("  connected")
    print(f"\nSeeded corpus in Firestore (project {proj})")
    print(f"  mentions  : {len(store.mentions)}")
    print(f"  war rooms : {len(store.war_rooms)}")
    print(f"  snapshots : {len(store.snapshots)}")
    print(f"  holdings  : {len(store.holdings)}")

    # Round trip: write, re-read through a fresh store, then clean up.
    probe = HoldingBrief(
        lines={"en": "Connectivity probe.", "bm": "Ujian sambungan."},
        facts_used=["mnt_tg_imbi_01"],
    )
    store.holdings[probe.id] = probe
    reloaded = FirestoreStore(project_id=proj, seed=False).holdings[probe.id]
    print("\nRound trip")
    print(f"  wrote and re-read : {reloaded.id == probe.id}")
    print(f"  invariants intact : human_must_send={reloaded.human_must_send}, "
          f"ave={reloaded.ave}, auto_publish={reloaded.auto_publish}")

    # Tenant scoping, against the real database rather than a fake.
    raw = store._client.collection(COL_HOLDINGS)
    raw.document("probe_foreign_tenant").set({
        **probe.model_dump(mode="json"),
        "id": "probe_foreign_tenant",
        "org_id": "org_someone_else",
        "workspace_id": "ws_someone_else",
    })
    leaked = "probe_foreign_tenant" in list(store.holdings)
    print("\nTenant isolation")
    print(f"  foreign document returned by scoped query: {leaked}")

    raw.document("probe_foreign_tenant").delete()
    del store.holdings[probe.id]
    print("  probes cleaned up")

    if leaked:
        print("\nFAIL — tenant isolation did not hold. Do not ship this.")
        return 1

    print("\nPASS — Firestore is live and tenant-scoped.")
    print("Requirement 3 (a Google Cloud infrastructure service) is met.")
    print("Screenshot the Firebase console showing nadi_holdings for the video.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
