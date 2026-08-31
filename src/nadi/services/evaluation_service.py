"""Lock Evaluation snapshots (AMEC IEF / Barcelona 4.0)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from nadi.domain.models import (
    EvaluationSnapshot,
    LadderStage,
    Methodology,
    Objective,
)
from nadi.services.contribution import band_for, cost_per_outcome, refresh_objectives, stage_score


def _canonical_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def build_snapshot(
    *,
    org_id: str,
    workspace_id: str,
    title: str,
    campaign: dict,
    window: dict[str, str],
    objectives: list[Objective],
    ladder: dict[str, LadderStage],
    moves: list[dict],
    created_by: dict,
    campaign_cost_myr: float | None = None,
    locale: str = "en",
    narrative_en: str = "",
    narrative_bm: str = "",
    limitations: list[str] | None = None,
) -> EvaluationSnapshot:
    objectives = refresh_objectives(list(objectives))
    score = stage_score(ladder)
    band = band_for(score)
    cpo = cost_per_outcome(campaign_cost_myr, objectives)

    methodology = Methodology(
        sources=["NADI mention graph", "coded messages"],
        sampling={"method": "full window universe"},
        ai={"used": True, "tasks": ["brief_moves"], "human_in_the_loop": True},
        limitations=limitations
        or [
            "Impact reputation index may be proxy pending panel",
            "Private messaging not in universe",
        ],
    )

    if len(moves) != 3:
        raise ValueError("moves must contain exactly 3 items")

    snap = EvaluationSnapshot(
        org_id=org_id,
        workspace_id=workspace_id,
        title=title,
        campaign=campaign,
        window=window,
        locale=locale,
        created_at=datetime.now(timezone.utc),
        created_by=created_by,
        methodology=methodology,
        inputs={
            "campaign_cost_myr": campaign_cost_myr,
            "currency": "MYR",
            "cost_source": "client_entered" if campaign_cost_myr is not None else None,
        },
        objectives=objectives,
        ladder=ladder,
        contribution={
            "score": score,
            "formula": "0.15*outputs + 0.25*outtakes + 0.35*outcomes + 0.25*impact",
            "band": band.value,
            "cost_per_outcome_myr": cpo,
            "narrative_en": narrative_en,
            "narrative_bm": narrative_bm,
        },
        moves=moves,
        governance={
            "classification": "client_confidential",
            "footer_en": (
                "NADI · berry-bison-yonder-cabin · Barcelona 4.0 · IEF · no AVE · AI assist disclosed"
            ),
            "footer_bm": (
                "NADI · berry-bison-yonder-cabin · Barcelona 4.0 · IEF · tiada AVE · bantuan AI dizahirkan"
            ),
        },
        integrity={"locked": True},
    )
    body = snap.model_dump(mode="json")
    body.pop("integrity", None)
    snap.integrity = {"content_sha256": _canonical_hash(body), "locked": True}
    return snap
