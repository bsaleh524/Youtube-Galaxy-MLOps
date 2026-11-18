import hashlib
import json
from pathlib import Path

import pytest

from pipeline.snapshot import load_current, validate_records, write_snapshot

FIXTURE = Path(__file__).parent / "fixtures" / "creators_small.json"


def records() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_is_valid():
    validate_records(records())


def test_duplicate_titles_allowed_duplicate_ids_rejected():
    recs = records()
    titles = [r["title"].lower() for r in recs]
    assert titles.count("target") == 2  # TARGET / Target are distinct pages
    validate_records(recs)
    with pytest.raises(ValueError, match="duplicate id: fandom_449281"):
        validate_records(recs + [dict(recs[0])])


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda r: r.pop("url"), "missing key 'url'"),
        (lambda r: r.update(id="449281"), "bad id"),
        (lambda r: r.update(id="fandom_abc"), "bad id"),
        (lambda r: r.update(title=""), "empty title"),
    ],
)
def test_validate_rejects_bad_records(change, message):
    recs = records()
    change(recs[0])
    with pytest.raises(ValueError, match=message):
        validate_records(recs)


def test_snapshot_round_trip_is_exact(tmp_path):
    recs = records()
    snap = write_snapshot(recs, tmp_path, source="test")
    loaded, manifest = load_current(tmp_path)
    by_id = {r["id"]: r for r in recs}
    assert len(loaded) == len(recs)
    for r in loaded:
        assert r == by_id[r["id"]]  # non-ASCII titles and None youtube_url survive unchanged
    assert manifest["count"] == len(recs)
    assert manifest["source"] == "test"
    assert manifest["sha256"] == hashlib.sha256((snap / "creators.json").read_bytes()).hexdigest()
    assert "ねくろちゃん" in (snap / "creators.json").read_text(encoding="utf-8")  # stored as UTF-8, not \u escapes


def test_records_sorted_by_numeric_pageid(tmp_path):
    write_snapshot(records(), tmp_path, source="test")
    loaded, _ = load_current(tmp_path)
    pids = [int(r["id"].split("_")[1]) for r in loaded]
    assert pids == sorted(pids)


def test_current_points_at_newest_snapshot(tmp_path):
    recs = records()
    first = write_snapshot(recs, tmp_path, source="a")
    second = write_snapshot(recs[:-1], tmp_path, source="b")  # same second: names must not collide
    assert first != second and first.exists() and second.exists()
    loaded, manifest = load_current(tmp_path)
    assert manifest["source"] == "b" and len(loaded) == len(recs) - 1


def test_write_snapshot_validates_first(tmp_path):
    recs = records() + [dict(records()[0])]
    with pytest.raises(ValueError):
        write_snapshot(recs, tmp_path, source="test")
    assert not (tmp_path / "current").exists()


def test_load_current_without_snapshot(tmp_path):
    with pytest.raises(FileNotFoundError, match="no current snapshot"):
        load_current(tmp_path)
