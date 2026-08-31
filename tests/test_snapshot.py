from nadi.data.seed_aurora import seed_snapshot


def test_seed_snapshot_no_ave():
    snap = seed_snapshot()
    assert snap.methodology.ave is False
    assert snap.status == "locked"
    assert len(snap.moves) == 3
    assert "content_sha256" in snap.integrity
    assert snap.contribution["score"] > 0
