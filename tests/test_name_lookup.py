import json
from pathlib import Path

from pipeline.name_lookup import build_name_index, find_named_creator, fold_name

FIXTURE = Path(__file__).resolve().parents[1] / "worker" / "test" / "fixtures" / "name_cases.json"


def test_fold_name():
    assert fold_name("  Café—Crème! ") == "cafe creme"
    assert fold_name("😀 Emoji Guy") == "emoji guy"


def test_shared_fixture():
    d = json.loads(FIXTURE.read_text(encoding="utf-8"))
    names = build_name_index(d["titles"], set(d["topic_words"]))
    got = [(c["question"], find_named_creator(c["question"], names)) for c in d["cases"]]
    assert got == [(c["question"], c["row"]) for c in d["cases"]]


def test_short_titles_and_topic_words_are_not_names():
    names = build_name_index(["TJ", "Music", "Music Guy"], {"music"})
    assert names == {"music guy": 2}
