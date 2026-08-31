from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from nadi.data.seed_aurora import ORG, WS, seed_mentions
from nadi.db.models import MentionDB
from nadi.db.repository import TenantRepository
from nadi.db.seed import seed_database
from nadi.db.session import Base
from nadi.domain.models import Mention


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    seed_database(db, engine_to_use=engine)
    try:
        yield db
    finally:
        db.close()


def test_seed_database_populates_tables(in_memory_db):
    repo = TenantRepository(in_memory_db, org_id=ORG.id, workspace_id=WS.id)
    mentions = repo.list_mentions()
    assert len(mentions) == 3
    
    war_rooms = repo.list_war_rooms()
    assert len(war_rooms) >= 1
    assert war_rooms[0].id.startswith("wr_")
    assert war_rooms[0].title != ""


def test_tenant_isolation_boundary(in_memory_db):
    # Repo for original tenant
    repo_aurora = TenantRepository(in_memory_db, org_id="org_aurora", workspace_id="ws_aurora")
    assert len(repo_aurora.list_mentions()) > 0
    assert len(repo_aurora.list_war_rooms()) > 0

    # Repo for an isolated/different tenant
    repo_other = TenantRepository(in_memory_db, org_id="org_competitor", workspace_id="ws_competitor")
    assert len(repo_other.list_mentions()) == 0
    assert len(repo_other.list_war_rooms()) == 0
    assert repo_other.get_snapshot("snap_aurora_2026_08") is None


def test_tenant_insert_isolation(in_memory_db):
    repo_a = TenantRepository(in_memory_db, org_id="org_a", workspace_id="ws_a")
    repo_b = TenantRepository(in_memory_db, org_id="org_b", workspace_id="ws_b")

    sample_mention = seed_mentions()[0].model_copy(update={"id": "mnt_custom_isolated_01"})
    repo_a.save_mention(sample_mention)

    assert len(repo_a.list_mentions()) == 1
    assert len(repo_b.list_mentions()) == 0


def test_sql_migration_script_contains_rls_policies():
    migration_file = Path(__file__).resolve().parent.parent / "schemas" / "migrations" / "001_initial_schema_and_rls.sql"
    assert migration_file.exists(), "Migration SQL file must exist"
    
    content = migration_file.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in content
    assert "current_setting('app.current_org_id'" in content
    assert "current_setting('app.current_workspace_id'" in content
    assert "chk_no_ave_eval" in content
    assert "chk_holding_no_ave" in content
