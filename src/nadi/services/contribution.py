"""AMEC contribution score — no AVE."""

from __future__ import annotations

from nadi.config import settings
from nadi.domain.enums import ContributionBand
from nadi.domain.models import LadderStage, Objective


def stage_score(stages: dict[str, LadderStage]) -> float:
    w = settings.contribution_weights
    total = 0.0
    for key, weight in w.items():
        stage = stages.get(key)
        if stage is None:
            continue
        total += weight * float(stage.score)
    return round(total, 1)


def band_for(score: float) -> ContributionBand:
    if score < 50:
        return ContributionBand.OFF_TRACK
    if score < 65:
        return ContributionBand.AT_RISK
    if score < 80:
        return ContributionBand.ON_TRACK
    return ContributionBand.EXCEEDING


def cost_per_outcome(campaign_cost_myr: float | None, objectives: list[Objective]) -> float | None:
    if campaign_cost_myr is None:
        return None
    green = sum(1 for o in objectives if o.status.value == "green")
    if green == 0:
        return None
    return round(campaign_cost_myr / green, 2)


def refresh_objectives(objectives: list[Objective]) -> list[Objective]:
    for o in objectives:
        o.refresh_status()
    return objectives
