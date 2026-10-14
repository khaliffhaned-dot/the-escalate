"""SQLAlchemy ORM models for NADI persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nadi.db.session import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class OrgDB(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[str] = mapped_column(String(64), default="growth")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now_utc)



class WorkspaceDB(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now_utc)

    __table_args__ = (
        Index("ix_workspaces_org_id_slug", "org_id", "slug"),
    )


class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    auth_source: Mapped[str] = mapped_column(String(64), default="password")
    idp_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now_utc)


class OrgMembershipDB(Base):
    __tablename__ = "org_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    org_role: Mapped[str] = mapped_column(String(64), default="analyst")

    __table_args__ = (
        Index("ix_org_membership_tenant", "org_id", "user_id", unique=True),
    )


class WorkspaceMembershipDB(Base):
    __tablename__ = "workspace_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ws_role: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_ws_membership_tenant", "org_id", "workspace_id", "user_id", unique=True),
    )



class MentionDB(Base):
    __tablename__ = "mentions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    lang: Mapped[str] = mapped_column(String(16), default="en")
    script: Mapped[str] = mapped_column(String(32), default="latin")
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    author_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_kind: Mapped[str] = mapped_column(String(64), default="public")
    outlet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outlet_tier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    three_r: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    east_my: Mapped[bool] = mapped_column(Boolean, default=False)
    engagement: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    peso: Mapped[str] = mapped_column(String(32), default="earned")
    starred: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_mentions_tenant_published", "org_id", "workspace_id", "published_at"),
        Index("ix_mentions_tenant_platform", "org_id", "workspace_id", "platform"),
    )



class EvaluationSnapshotDB(Base):
    __tablename__ = "evaluation_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0.0")
    status: Mapped[str] = mapped_column(String(32), default="locked")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    window: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now_utc)
    created_by: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    supersedes_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    methodology: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    objectives: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ladder: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    contribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    moves: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    governance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    integrity: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_eval_snapshots_tenant", "org_id", "workspace_id", "created_at"),
    )


class WarRoomDB(Base):
    __tablename__ = "war_rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0.0")
    status: Mapped[str] = mapped_column(String(32), default="open")
    severity: Mapped[str] = mapped_column(String(32), default="medium")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    locale: Mapped[str] = mapped_column(String(32), default="bilingual")
    campaign_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    three_r: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    queues: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    holdings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    media: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    links: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    listed: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=_now_utc)
    opened_by: Mapped[str] = mapped_column(String(255), default="system")
    contained_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    methodology: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_war_rooms_tenant_status", "org_id", "workspace_id", "status"),
    )


class HoldingBriefDB(Base):
    __tablename__ = "holdings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    brief_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    war_room_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    locale: Mapped[str] = mapped_column(String(32), default="bilingual")
    audience: Mapped[str] = mapped_column(String(32), default="press")
    version: Mapped[int] = mapped_column(Integer, default=1)
    facts_used: Mapped[list[str]] = mapped_column(JSON, default=list)
    gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    lines: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    do_not_say: Mapped[list[str]] = mapped_column(JSON, default=list)
    ops: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    posture: Mapped[str] = mapped_column(String(64), default="self_regulated_not_directed")
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    ave: Mapped[bool] = mapped_column(Boolean, default=False)
    human_must_send: Mapped[bool] = mapped_column(Boolean, default=True)
    model_version: Mapped[str] = mapped_column(String(64), default="nadi-brief-2026-08")
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    methodology: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_holdings_tenant", "org_id", "workspace_id", "status"),
    )


class ReportScheduleDB(Base):
    """Persisted report schedule configs. Persisting these (rather than
    holding them only in an in-process dict) is what lets a weekly
    schedule survive an app restart: on startup the scheduler loop just
    compares `next_run_at` against now for every row here and catches up,
    it doesn't need to have been running continuously. This only helps
    when NADI_USE_DB_STORE=true though, with the default in-memory store
    schedules still don't survive a restart, same limitation as the rest
    of the in-memory store.
    """

    __tablename__ = "report_schedules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cadence: Mapped[str] = mapped_column(String(32), default="weekly")  # weekly | on_demand
    day_of_week: Mapped[int] = mapped_column(Integer, default=0)  # 0=Monday
    hour_myt: Mapped[int] = mapped_column(Integer, default=9)
    recipients: Mapped[list[str]] = mapped_column(JSON, default=list)
    webhook_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now_utc)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_report_schedules_tenant", "org_id", "workspace_id"),
    )
