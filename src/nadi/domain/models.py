"""Core domain models (Pydantic). AVE fields are intentionally absent."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from nadi.domain.enums import (
    ContributionBand,
    HoldingStatus,
    Lang,
    ObjectiveStatus,
    OrgRole,
    OrgStatus,
    OrgTier,
    PESO,
    Platform,
    ResidueChannel,
    ResidueStatus,
    SentimentLabel,
    ThreeRFlag,
    WarRoomSeverity,
    WarRoomStatus,
    WorkspaceRole,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Organisation(BaseModel):
    id: str = Field(default_factory=lambda: _id("org"))
    slug: str
    name: str
    tier: OrgTier = OrgTier.DESK
    status: OrgStatus = OrgStatus.TRIAL
    data_region: str = "ap-southeast-1"
    retention_days: int = 396
    ave_enabled: bool = False
    dpo_email: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ave_enabled")
    @classmethod
    def force_no_ave(cls, v: bool) -> bool:
        return False


class Workspace(BaseModel):
    id: str = Field(default_factory=lambda: _id("ws"))
    org_id: str
    slug: str
    name: str
    kind: str = "brand"
    status: str = "active"
    timezone: str = "Asia/Kuala_Lumpur"
    locale: str = "en"
    settings: dict[str, Any] = Field(default_factory=dict)


class User(BaseModel):
    id: str = Field(default_factory=lambda: _id("usr"))
    email: str
    name: str
    status: str = "active"
    auth_source: str = "password"
    idp_subject: str | None = None


class OrgMembership(BaseModel):
    org_id: str
    user_id: str
    org_role: OrgRole


class WorkspaceMembership(BaseModel):
    org_id: str
    workspace_id: str
    user_id: str
    ws_role: WorkspaceRole


class Sentiment(BaseModel):
    label: SentimentLabel
    score: float = 0.0
    nuance: list[str] = Field(default_factory=list)


class ThreeR(BaseModel):
    flags: list[ThreeRFlag] = Field(default_factory=list)
    severity: str = "none"
    review: str = "clear"


class Mention(BaseModel):
    id: str = Field(default_factory=lambda: _id("mnt"))
    org_id: str
    workspace_id: str
    published_at: datetime
    ingested_at: datetime | None = None
    platform: Platform
    lang: Lang
    script: str = "latin"
    url: str | None = None
    author_handle: str | None = None
    author_name: str | None = None
    author_kind: str = "public"
    outlet_name: str | None = None
    outlet_tier: str | None = None
    text: str
    excerpt: str | None = None
    sentiment: Sentiment
    three_r: ThreeR = Field(default_factory=ThreeR)
    state: str | None = None
    east_my: bool = False
    engagement: dict[str, Any] = Field(default_factory=dict)
    codes: list[str] = Field(default_factory=list)
    peso: PESO = PESO.EARNED
    starred: bool = False


class Objective(BaseModel):
    id: str
    label_en: str
    label_bm: str = ""
    baseline: float
    target: float
    actual: float
    unit: str = "index"
    direction: str = "up"  # up | down
    status: ObjectiveStatus = ObjectiveStatus.NOT_STARTED
    stakeholders: list[str] = Field(default_factory=list)

    def progress(self) -> float:
        if self.direction == "down":
            # lower actual is better; target is ideal floor (often 0)
            span = abs(self.baseline - self.target) or 1.0
            done = abs(self.baseline - self.actual)
            return max(0.0, min(1.0, done / span))
        span = abs(self.target - self.baseline) or 1.0
        done = self.actual - self.baseline
        return max(0.0, min(1.0, done / span))

    def refresh_status(self) -> ObjectiveStatus:
        p = self.progress()
        if p >= 1.0:
            self.status = ObjectiveStatus.GREEN
        elif p >= 0.6:
            self.status = ObjectiveStatus.AMBER
        elif self.actual == self.baseline and self.direction == "up":
            self.status = ObjectiveStatus.NOT_STARTED
        else:
            self.status = ObjectiveStatus.RED
        return self.status


class LadderStage(BaseModel):
    weight: float
    score: float
    kpis: list[dict[str, Any]] = Field(default_factory=list)
    quotes: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class Methodology(BaseModel):
    framework: str = "AMEC Integrated Evaluation Framework"
    principles: str = "Barcelona Principles 4.0"
    codename: str = "berry-bison-yonder-cabin"
    ave: bool = False
    ave_statement: str = (
        "Invalid under Barcelona Principles 4.0 — NADI measures contribution, "
        "not advertising equivalents."
    )
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "outputs": 0.15,
            "outtakes": 0.25,
            "outcomes": 0.35,
            "impact": 0.25,
        }
    )
    sources: list[str] = Field(default_factory=list)
    sampling: dict[str, Any] = Field(default_factory=dict)
    ai: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("ave")
    @classmethod
    def no_ave(cls, v: bool) -> bool:
        return False


class EvaluationSnapshot(BaseModel):
    schema_version: str = "1.0.0"
    id: str = Field(default_factory=lambda: _id("snap"))
    org_id: str
    workspace_id: str
    status: str = "locked"
    title: str
    campaign: dict[str, Any] = Field(default_factory=dict)
    window: dict[str, str]
    locale: str = "en"
    created_at: datetime
    created_by: dict[str, Any] = Field(default_factory=dict)
    supersedes_id: str | None = None
    methodology: Methodology = Field(default_factory=Methodology)
    inputs: dict[str, Any] = Field(default_factory=dict)
    objectives: list[Objective] = Field(default_factory=list)
    ladder: dict[str, LadderStage] = Field(default_factory=dict)
    contribution: dict[str, Any] = Field(default_factory=dict)
    moves: list[dict[str, Any]] = Field(default_factory=list)
    governance: dict[str, Any] = Field(default_factory=dict)
    integrity: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def must_be_locked(cls, v: str) -> str:
        return "locked"


class ResidueItem(BaseModel):
    id: str = Field(default_factory=lambda: _id("res"))
    mention_id: str | None = None
    channel: ResidueChannel
    asset: str
    location: str | None = None
    status: ResidueStatus = ResidueStatus.DETECTED
    sla_hours: float = 48


class HoldingRef(BaseModel):
    id: str
    brief_id: str | None = None
    status: HoldingStatus = HoldingStatus.DRAFT
    locale: str = "bilingual"
    version: int = 1


class Decision(BaseModel):
    id: str = Field(default_factory=lambda: _id("dec"))
    at: datetime
    actor_user_id: str
    action: str
    note: str = ""


class WarRoom(BaseModel):
    schema_version: str = "1.0.0"
    id: str = Field(default_factory=lambda: _id("wr"))
    org_id: str
    workspace_id: str
    status: WarRoomStatus = WarRoomStatus.OPEN
    severity: WarRoomSeverity = WarRoomSeverity.MEDIUM
    title: str
    locale: str = "bilingual"
    campaign_id: str | None = None
    trigger: dict[str, Any]
    three_r: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(
        default_factory=lambda: {
            "auto_publish": False,
            "ave": False,
            "human_send": True,
            "require_ws_admin_to_close": True,
            "legal_hold": False,
        }
    )
    queues: dict[str, Any] = Field(
        default_factory=lambda: {
            "three_r": [],
            "residue": [],
            "queries": [],
            "assignments": [],
        }
    )
    holdings: list[HoldingRef] = Field(default_factory=list)
    media: dict[str, Any] = Field(default_factory=dict)
    decisions: list[Decision] = Field(default_factory=list)
    links: dict[str, Any] = Field(default_factory=dict)
    opened_at: datetime
    opened_by: str
    contained_at: datetime | None = None
    closed_at: datetime | None = None
    methodology: dict[str, Any] = Field(
        default_factory=lambda: {
            "framework": "AMEC IEF",
            "principles": "Barcelona Principles 4.0",
            "codename": "berry-bison-yonder-cabin",
            "ave": False,
            "auto_publish": False,
        }
    )


class HoldingBrief(BaseModel):
    id: str = Field(default_factory=lambda: _id("hld"))
    brief_id: str = Field(default_factory=lambda: _id("brf"))
    war_room_id: str | None = None
    status: HoldingStatus = HoldingStatus.DRAFT
    locale: str = "bilingual"
    audience: str = "press"
    version: int = 1
    facts_used: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    lines: dict[str, str] = Field(default_factory=dict)
    do_not_say: list[str] = Field(default_factory=list)
    ops: list[dict[str, Any]] = Field(default_factory=list)
    posture: str = "self_regulated_not_directed"
    auto_publish: bool = False
    ave: bool = False
    human_must_send: bool = True
    model_version: str = "nadi-brief-2026-08"
    prompt_hash: str = ""
    methodology: dict[str, Any] = Field(
        default_factory=lambda: {
            "principles": "Barcelona Principles 4.0",
            "codename": "berry-bison-yonder-cabin",
            "ave": False,
        }
    )

    @field_validator("ave", "auto_publish")
    @classmethod
    def force_false(cls, v: bool) -> bool:
        return False

    @field_validator("human_must_send")
    @classmethod
    def force_true(cls, v: bool) -> bool:
        return True
