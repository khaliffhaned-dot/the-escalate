"""Database seed script for NADI tables."""

from __future__ import annotations

from sqlalchemy.orm import Session

from nadi.data.seed_aurora import (
    ORG,
    USER,
    WS,
    seed_mentions,
    seed_snapshot,
    seed_war_room_and_holding,
)
from nadi.db.models import OrgDB, UserDB, WorkspaceDB, WorkspaceMembershipDB
from nadi.db.repository import TenantRepository
from nadi.db.session import Base, get_engine


def seed_database(db: Session, engine_to_use=None) -> None:
    """Creates all tables and seeds Aurora demo data."""
    eng = engine_to_use or db.get_bind()
    Base.metadata.create_all(bind=eng)

    # 1. Org, Workspace, User, Membership
    if not db.get(OrgDB, ORG.id):
        db.add(OrgDB(id=ORG.id, name=ORG.name, tier=ORG.tier.value))
    if not db.get(WorkspaceDB, WS.id):
        db.add(WorkspaceDB(id=WS.id, org_id=WS.org_id, name=WS.name, slug=WS.slug))
    if not db.get(UserDB, USER.id):
        db.add(UserDB(id=USER.id, email=USER.email, name=USER.name, status=USER.status, auth_source=USER.auth_source))
    
    db.flush()


    repo = TenantRepository(db, org_id=ORG.id, workspace_id=WS.id)

    # 2. Mentions
    for m in seed_mentions():
        repo.save_mention(m)

    # 3. Snapshot
    snap = seed_snapshot()
    repo.save_snapshot(snap)

    # 4. War room & holding
    wr, hld = seed_war_room_and_holding()
    repo.save_war_room(wr)
    repo.save_holding(hld)

    db.commit()


if __name__ == "__main__":
    from nadi.db.session import SessionLocal
    with SessionLocal() as session:
        seed_database(session)
        print("Database seeded successfully.")
