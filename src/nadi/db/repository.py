"""Tenant-scoped database repository for NADI models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nadi.db.models import (
    EvaluationSnapshotDB,
    HoldingBriefDB,
    MentionDB,
    OrgDB,
    UserDB,
    WarRoomDB,
    WorkspaceDB,
    WorkspaceMembershipDB,
)
from nadi.domain.models import (
    EvaluationSnapshot,
    HoldingBrief,
    Mention,
    Organisation,
    User,
    WarRoom,
    Workspace,
    WorkspaceMembership,
)

from nadi.services.holding_service import reject_if_ave_requested


class TenantRepository:
    """Provides tenant-isolated access to all NADI persistent entities."""

    def __init__(self, db: Session, org_id: str, workspace_id: str):
        self.db = db
        self.org_id = org_id
        self.workspace_id = workspace_id

    # --- Mentions ---
    def list_mentions(
        self,
        platform: str | None = None,
        only_3r: bool = False,
        limit: int = 100,
    ) -> list[Mention]:
        stmt = select(MentionDB).where(
            MentionDB.org_id == self.org_id,
            MentionDB.workspace_id == self.workspace_id,
        )
        if platform:
            stmt = stmt.where(MentionDB.platform == platform)
        stmt = stmt.order_by(MentionDB.published_at.desc()).limit(limit)
        results = self.db.scalars(stmt).all()

        mentions = []
        for r in results:
            data = {
                "id": r.id,
                "org_id": r.org_id,
                "workspace_id": r.workspace_id,
                "published_at": r.published_at,
                "ingested_at": r.ingested_at,
                "platform": r.platform,
                "lang": r.lang,
                "script": r.script,
                "url": r.url,
                "author_handle": r.author_handle,
                "author_name": r.author_name,
                "author_kind": r.author_kind,
                "outlet_name": r.outlet_name,
                "outlet_tier": r.outlet_tier,
                "text": r.text,
                "excerpt": r.excerpt,
                "sentiment": r.sentiment or {},
                "three_r": r.three_r or {},
                "state": r.state,
                "east_my": r.east_my,
                "engagement": r.engagement or {},
                "codes": r.codes or [],
                "peso": r.peso,
                "starred": r.starred,
            }
            m = Mention.model_validate(data)
            if only_3r and not m.three_r.flags:
                continue
            mentions.append(m)
        return mentions

    def save_mention(self, mention: Mention) -> Mention:
        db_obj = self.db.get(MentionDB, mention.id)
        if not db_obj:
            db_obj = MentionDB(
                id=mention.id,
                org_id=self.org_id,
                workspace_id=self.workspace_id,
                published_at=mention.published_at,
                ingested_at=mention.ingested_at or datetime.now(timezone.utc),

                platform=mention.platform.value,
                lang=mention.lang.value,
                script=mention.script,
                url=mention.url,
                author_handle=mention.author_handle,
                author_name=mention.author_name,
                author_kind=mention.author_kind,
                outlet_name=mention.outlet_name,
                outlet_tier=mention.outlet_tier,
                text=mention.text,
                excerpt=mention.excerpt,
                sentiment=mention.sentiment.model_dump(mode="json"),
                three_r=mention.three_r.model_dump(mode="json"),
                state=mention.state,
                east_my=mention.east_my,
                engagement=mention.engagement,
                codes=mention.codes,
                peso=mention.peso.value,
                starred=mention.starred,
            )
            self.db.add(db_obj)
        else:
            db_obj.text = mention.text
            db_obj.starred = mention.starred
            db_obj.sentiment = mention.sentiment.model_dump(mode="json")
            db_obj.three_r = mention.three_r.model_dump(mode="json")
        self.db.flush()
        return mention

    # --- Evaluation Snapshots ---
    def get_snapshot(self, snapshot_id: str) -> EvaluationSnapshot | None:
        stmt = select(EvaluationSnapshotDB).where(
            EvaluationSnapshotDB.id == snapshot_id,
            EvaluationSnapshotDB.org_id == self.org_id,
            EvaluationSnapshotDB.workspace_id == self.workspace_id,
        )
        r = self.db.scalars(stmt).first()
        if not r:
            return None
        return EvaluationSnapshot.model_validate(r.__dict__)

    def save_snapshot(self, snap: EvaluationSnapshot) -> EvaluationSnapshot:
        reject_if_ave_requested(snap.methodology.model_dump())
        db_obj = EvaluationSnapshotDB(
            id=snap.id,
            org_id=self.org_id,
            workspace_id=self.workspace_id,
            schema_version=snap.schema_version,
            status=snap.status,
            title=snap.title,
            campaign=snap.campaign,
            window=snap.window,
            locale=snap.locale,
            created_at=snap.created_at,
            created_by=snap.created_by,
            supersedes_id=snap.supersedes_id,
            methodology=snap.methodology.model_dump(mode="json"),
            inputs=snap.inputs,
            objectives=[o.model_dump(mode="json") for o in snap.objectives],
            ladder={k: v.model_dump(mode="json") for k, v in snap.ladder.items()},
            contribution=snap.contribution,
            moves=snap.moves,
            governance=snap.governance,
            integrity=snap.integrity,
        )
        self.db.add(db_obj)
        self.db.flush()
        return snap

    # --- War Rooms ---
    def list_war_rooms(self) -> list[WarRoom]:
        stmt = select(WarRoomDB).where(
            WarRoomDB.org_id == self.org_id,
            WarRoomDB.workspace_id == self.workspace_id,
        ).order_by(WarRoomDB.opened_at.desc())
        results = self.db.scalars(stmt).all()
        return [WarRoom.model_validate(r.__dict__) for r in results]

    def get_war_room(self, wr_id: str) -> WarRoom | None:
        stmt = select(WarRoomDB).where(
            WarRoomDB.id == wr_id,
            WarRoomDB.org_id == self.org_id,
            WarRoomDB.workspace_id == self.workspace_id,
        )
        r = self.db.scalars(stmt).first()
        if not r:
            return None
        return WarRoom.model_validate(r.__dict__)

    def save_war_room(self, wr: WarRoom) -> WarRoom:
        holdings_data = [

            h.model_dump(mode="json") if hasattr(h, "model_dump") else h
            for h in wr.holdings
        ]
        decisions_data = [
            d.model_dump(mode="json") if hasattr(d, "model_dump") else d
            for d in wr.decisions
        ]
        db_obj = self.db.get(WarRoomDB, wr.id)
        if not db_obj:
            db_obj = WarRoomDB(
                id=wr.id,
                org_id=self.org_id,
                workspace_id=self.workspace_id,
                schema_version=wr.schema_version,
                status=wr.status.value if hasattr(wr.status, "value") else str(wr.status),
                severity=wr.severity.value if hasattr(wr.severity, "value") else str(wr.severity),
                title=wr.title,
                locale=wr.locale,
                campaign_id=wr.campaign_id,
                trigger=wr.trigger,
                three_r=wr.three_r,
                policy=wr.policy,
                queues=wr.queues,
                holdings=holdings_data,
                media=wr.media,
                decisions=decisions_data,
                links=wr.links,
                opened_at=wr.opened_at,
                opened_by=wr.opened_by,
                contained_at=wr.contained_at,
                closed_at=wr.closed_at,
                methodology=wr.methodology,
            )
            self.db.add(db_obj)
        else:
            db_obj.status = wr.status.value if hasattr(wr.status, "value") else str(wr.status)
            db_obj.severity = wr.severity.value if hasattr(wr.severity, "value") else str(wr.severity)
            db_obj.title = wr.title
            db_obj.holdings = holdings_data
            db_obj.decisions = decisions_data
            db_obj.contained_at = wr.contained_at
            db_obj.closed_at = wr.closed_at
        self.db.flush()
        return wr


    # --- Holdings ---
    def get_holding(self, hld_id: str) -> HoldingBrief | None:
        stmt = select(HoldingBriefDB).where(
            HoldingBriefDB.id == hld_id,
            HoldingBriefDB.org_id == self.org_id,
            HoldingBriefDB.workspace_id == self.workspace_id,
        )
        r = self.db.scalars(stmt).first()
        if not r:
            return None
        return HoldingBrief.model_validate(r.__dict__)

    def save_holding(self, hld: HoldingBrief) -> HoldingBrief:
        reject_if_ave_requested({})
        db_obj = self.db.get(HoldingBriefDB, hld.id)
        if not db_obj:
            db_obj = HoldingBriefDB(
                id=hld.id,
                brief_id=hld.brief_id,
                org_id=self.org_id,
                workspace_id=self.workspace_id,
                war_room_id=hld.war_room_id,
                status=hld.status.value,
                locale=hld.locale,
                audience=hld.audience,
                version=hld.version,
                facts_used=hld.facts_used,
                gaps=hld.gaps,
                lines=hld.lines,
                do_not_say=hld.do_not_say,
                ops=hld.ops,
                posture=hld.posture,
                auto_publish=False,
                ave=False,
                human_must_send=True,
                model_version=hld.model_version,
                prompt_hash=hld.prompt_hash,
                methodology=hld.methodology,
            )
            self.db.add(db_obj)
        else:
            db_obj.status = hld.status.value
            db_obj.version = hld.version
            db_obj.lines = hld.lines
        self.db.flush()
        return hld
