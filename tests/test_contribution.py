from nadi.domain.enums import ObjectiveStatus
from nadi.domain.models import LadderStage, Objective
from nadi.services.contribution import band_for, cost_per_outcome, stage_score


def test_stage_score_weights():
    ladder = {
        "outputs": LadderStage(weight=0.15, score=80),
        "outtakes": LadderStage(weight=0.25, score=68),
        "outcomes": LadderStage(weight=0.35, score=61),
        "impact": LadderStage(weight=0.25, score=54),
    }
    # 0.15*80 + 0.25*68 + 0.35*61 + 0.25*54 = 12+17+21.35+13.5 = 63.85 → round half-even 63.8
    assert stage_score(ladder) == 63.8


def test_band():
    assert band_for(40).value == "off_track"
    assert band_for(72).value == "on_track"


def test_cost_per_outcome():
    objs = [
        Objective(id="O1", label_en="a", baseline=0, target=1, actual=1, status=ObjectiveStatus.GREEN),
        Objective(id="O2", label_en="b", baseline=0, target=1, actual=0.5, status=ObjectiveStatus.AMBER),
    ]
    assert cost_per_outcome(100000, objs) == 100000.0
    assert cost_per_outcome(None, objs) is None
