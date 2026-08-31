"""Jalur Kita / Aurora demo seed for Evaluation + war room."""

from __future__ import annotations

from datetime import datetime, timezone

from nadi.domain.enums import (
    Lang,
    ObjectiveStatus,
    OrgStatus,
    OrgTier,
    Platform,
    ResidueChannel,
    ResidueStatus,
    SentimentLabel,
    ThreeRFlag,
    WarRoomSeverity,
)
from nadi.domain.models import (
    LadderStage,
    Mention,
    Objective,
    Organisation,
    ResidueItem,
    Sentiment,
    ThreeR,
    User,
    Workspace,
)
from nadi.services.evaluation_service import build_snapshot
from nadi.services.holding_service import draft_holding_from_mentions
from nadi.services.war_room_service import open_war_room

ORG = Organisation(
    id="org_aurora",
    slug="aurora",
    name="Aurora Group",
    tier=OrgTier.DESK,
    status=OrgStatus.ACTIVE,
)
WS = Workspace(id="ws_aurora", org_id=ORG.id, slug="aurora", name="Aurora Brand")
USER = User(id="usr_ws_admin", email="comms@aurora.example", name="Desk Lead")


def seed_mentions() -> list[Mention]:
    now = datetime(2026, 8, 24, 6, 30, tzinfo=timezone.utc)
    return [
        Mention(
            id="mnt_bh_sme",
            org_id=ORG.id,
            workspace_id=WS.id,
            published_at=now,
            platform=Platform.NEWS,
            lang=Lang.BM,
            outlet_name="Berita Harian",
            outlet_tier="national",
            text="SME names on pack — East Coast suppliers not a footnote.",
            excerpt="SME names on pack — East Coast suppliers not a footnote.",
            sentiment=Sentiment(label=SentimentLabel.POS, score=0.7, nuance=["sme_on_pack"]),
            codes=["sme_on_pack"],
            state="Kelantan",
            east_my=False,
        ),
        Mention(
            id="mnt_de_east",
            org_id=ORG.id,
            workspace_id=WS.id,
            published_at=now,
            platform=Platform.NEWS,
            lang=Lang.EN,
            outlet_name="Daily Express",
            outlet_tier="regional",
            text="Merdeka film, zero KK faces. Logistics win in Sabah, casting still peninsula.",
            excerpt="Merdeka film, zero KK faces.",
            sentiment=Sentiment(label=SentimentLabel.NEG, score=-0.4, nuance=["east_my"]),
            codes=["east_my"],
            state="Sabah",
            east_my=True,
        ),
        Mention(
            id="mnt_tg_imbi_01",
            org_id=ORG.id,
            workspace_id=WS.id,
            published_at=now,
            platform=Platform.TELEGRAM,
            lang=Lang.MIXED,
            text="Slogan lama still on the Jalan Imbi endcap. WhatsApp screenshot circulating.",
            excerpt="Raja di hati endcap still up Jalan Imbi.",
            sentiment=Sentiment(label=SentimentLabel.NEG, score=-0.5, nuance=["three_r_residue"]),
            three_r=ThreeR(flags=[ThreeRFlag.ROYALTY], severity="high", review="in_review"),
            codes=["three_r_residue"],
            state="WP Kuala Lumpur",
        ),
    ]


def seed_objectives() -> list[Objective]:
    return [
        Objective(
            id="O1",
            label_en="Net sentiment ≥ +15",
            label_bm="Sentimen bersih ≥ +15",
            baseline=0,
            target=15,
            actual=11,
            unit="index",
            direction="up",
            status=ObjectiveStatus.AMBER,
        ),
        Objective(
            id="O2",
            label_en="SME-on-pack pull-through ≥ 40%",
            label_bm="Pull-through SME on-pack ≥ 40%",
            baseline=0,
            target=0.40,
            actual=0.36,
            unit="ratio",
            direction="up",
            status=ObjectiveStatus.AMBER,
        ),
        Objective(
            id="O3",
            label_en="East MY share ≥ 20%",
            label_bm="Bahagian Malaysia Timur ≥ 20%",
            baseline=0,
            target=0.20,
            actual=0.18,
            unit="ratio",
            direction="up",
            status=ObjectiveStatus.AMBER,
        ),
        Objective(
            id="O4",
            label_en="3R residue cleared in 48h",
            label_bm="Sisa 3R selesai dalam 48j",
            baseline=0,
            target=1.0,
            actual=0.64,
            unit="ratio",
            direction="up",
            status=ObjectiveStatus.AMBER,
        ),
        Objective(
            id="O5",
            label_en="Dual-calendar ready by 10 Sep",
            label_bm="Kalendar dual sedia by 10 Sep",
            baseline=0,
            target=1.0,
            actual=0.55,
            unit="ratio",
            direction="up",
            status=ObjectiveStatus.RED,
        ),
    ]


def seed_ladder() -> dict[str, LadderStage]:
    return {
        "outputs": LadderStage(weight=0.15, score=80, kpis=[{"id": "volume", "actual": 412}]),
        "outtakes": LadderStage(
            weight=0.25,
            score=68,
            kpis=[{"id": "pull_sme", "actual": 0.36}],
            quotes=[
                {
                    "mention_id": "mnt_bh_sme",
                    "outlet": "Berita Harian",
                    "text": "SME names on pack — East Coast suppliers not a footnote.",
                }
            ],
        ),
        "outcomes": LadderStage(weight=0.35, score=61, kpis=[{"id": "residue_decay", "actual": 0.64}]),
        "impact": LadderStage(
            weight=0.25,
            score=54,
            kpis=[{"id": "malaysia_day_readiness", "actual": 0.55}],
            notes="Trust panel not in this window.",
        ),
    }


def seed_moves() -> list[dict]:
    return [
        {
            "id": 1,
            "horizon_days": 14,
            "en": "Date Malaysia Day shoot and Borneo Post / Daily Express briefing before 10 Sep.",
            "bm": "Tetapkan shoot Hari Malaysia dan taklimat Borneo Post / Daily Express sebelum 10 Sep.",
            "objective_ids": ["O3", "O5"],
            "stage": "outcomes",
        },
        {
            "id": 2,
            "horizon_days": 14,
            "en": "Close The Star SME methodology query on background; protect supplier story.",
            "bm": "Selesaikan pertanyaan metodologi SME The Star secara background.",
            "objective_ids": ["O2"],
            "stage": "outcomes",
        },
        {
            "id": 3,
            "horizon_days": 14,
            "en": "Retail sweep for residual POS; one-line superseded note, not a second apology.",
            "bm": "Sapuan runcit untuk POS sisa; notis satu baris, bukan maaf kedua.",
            "objective_ids": ["O4"],
            "stage": "outcomes",
        },
    ]


def seed_snapshot():
    return build_snapshot(
        org_id=ORG.id,
        workspace_id=WS.id,
        title="Jalur Kita · week 34",
        campaign={"id": "cmp_jalur_kita", "name": "Jalur Kita Merdeka 2026", "client": "Aurora Group"},
        window={
            "from": "2026-08-18T00:00:00Z",
            "to": "2026-08-24T15:59:59Z",
            "timezone": "Asia/Kuala_Lumpur",
            "label": "18–24 Aug 2026",
        },
        objectives=seed_objectives(),
        ladder=seed_ladder(),
        moves=seed_moves(),
        created_by={"user_id": USER.id, "name": USER.name, "role": "ws_admin"},
        campaign_cost_myr=180000,
        narrative_en="Contribution is held back by East MY share and dual-calendar readiness, not by volume.",
        narrative_bm="Sumbangan tertahan oleh bahagian Malaysia Timur dan kesediaan kalendar dual, bukan oleh volume.",
    )


def seed_war_room_and_holding():
    mentions = seed_mentions()
    residue_m = next(m for m in mentions if m.id == "mnt_tg_imbi_01")
    wr = open_war_room(
        org_id=ORG.id,
        workspace_id=WS.id,
        title='Jalur Kita · POS residue “Raja di hati” · Jalan Imbi',
        severity=WarRoomSeverity.HIGH,
        trigger={
            "kind": "residue",
            "mention_id": residue_m.id,
            "at": residue_m.published_at.isoformat(),
        },
        opened_by=USER.id,
        three_r={
            "flags": ["royalty"],
            "posture": "self_regulated_not_directed",
            "review": "in_review",
        },
        residue=[
            ResidueItem(
                id="res_imbi_endcap",
                mention_id=residue_m.id,
                channel=ResidueChannel.POS_RETAIL,
                asset="Raja di hati endcap card",
                location="Jalan Imbi",
                status=ResidueStatus.SWEEPING,
            )
        ],
    )
    holding = draft_holding_from_mentions(
        mentions=[residue_m],
        war_room_id=wr.id,
        locale="bilingual",
        audience="press",
    )
    wr.holdings.append(
        {
            "id": holding.id,
            "brief_id": holding.brief_id,
            "status": holding.status.value,
            "locale": holding.locale,
            "version": holding.version,
        }
    )
    return wr, holding
