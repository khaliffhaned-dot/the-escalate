import pytest

from nadi.domain.enums import HoldingStatus
from nadi.services.holding_service import draft_holding_from_mentions, reject_if_ave_requested, transition
from nadi.data.seed_aurora import seed_mentions


def test_reject_ave():
    with pytest.raises(ValueError):
        reject_if_ave_requested({"include_ave": True})
    with pytest.raises(ValueError):
        reject_if_ave_requested({"publish": True})


def test_draft_has_no_ave_and_human_send():
    m = [x for x in seed_mentions() if x.id == "mnt_tg_imbi_01"]
    h = draft_holding_from_mentions(mentions=m, war_room_id="wr_test")
    assert h.ave is False
    assert h.auto_publish is False
    assert h.human_must_send is True
    assert "en" in h.lines and "bm" in h.lines


def test_transition():
    m = seed_mentions()[:1]
    h = draft_holding_from_mentions(mentions=m, war_room_id=None)
    transition(h, HoldingStatus.APPROVED)
    assert h.status == HoldingStatus.APPROVED
    transition(h, HoldingStatus.SENT_EXTERNAL)
    assert h.status == HoldingStatus.SENT_EXTERNAL
