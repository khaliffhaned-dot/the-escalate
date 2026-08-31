"""SQLAlchemy engine, session factory, and RLS session management."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from nadi.config import settings


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str | None = None):
    url = database_url or settings.database_url or "sqlite:///./nadi.db"
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(url, connect_args=connect_args, echo=False)


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session(
    org_id: str | None = None,
    workspace_id: str | None = None,
    custom_engine=None,
) -> Generator[Session, None, None]:
    """Provides a transactional database session with RLS session variables set."""
    eng = custom_engine or engine
    db: Session = sessionmaker(autocommit=False, autoflush=False, bind=eng)()
    try:
        if eng.dialect.name == "postgresql":
            if org_id:
                db.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
            if workspace_id:
                db.execute(text(f"SET LOCAL app.current_workspace_id = '{workspace_id}'"))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
