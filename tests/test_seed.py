import pytest

from pipeline.seed import check_overlap


def test_overlap_counts():
    ids = {"fandom_1", "fandom_2", "fandom_3"}
    r = check_overlap(ids, {"fandom_1": "A", "fandom_2": "A"})
    assert r == {
        "records": 3,
        "named": 2,
        "names": 1,
        "named_not_in_snapshot": 0,
        "snapshot_without_name": 1,
    }


def test_same_title_pages_named_independently_by_id():
    # TARGET and Target are separate pages; names attach by id, so each keeps its own.
    named = {"fandom_449281": "Brands", "fandom_372805": "Gaming"}
    r = check_overlap({"fandom_449281", "fandom_372805"}, named)
    assert r["named"] == 2 and r["names"] == 2


def test_mismatched_sources_rejected():
    named = {f"fandom_{i}": "X" for i in range(1000)}
    ids = {f"fandom_{i}" for i in range(990)}  # 1% of named ids unknown > 0.5%
    with pytest.raises(ValueError, match="not in the snapshot"):
        check_overlap(ids, named)
