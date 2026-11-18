import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pipeline.embed import load_embeddings, plan, run
from pipeline.textprep import embed_text, text_hash

FIXTURE = Path(__file__).parent / "fixtures" / "creators_small.json"
MODEL = "test-model"


def records() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class FakeEncoder:
    """Deterministic unit vectors from the text's hash; counts what it was asked to encode."""

    dim = 8

    def __init__(self):
        self.seen: list[str] = []

    def encode(self, texts: list[str]) -> np.ndarray:
        self.seen.extend(texts)
        out = []
        for t in texts:
            rng = np.random.default_rng(int(hashlib.sha256(t.encode()).hexdigest()[:8], 16))
            v = rng.normal(size=self.dim)
            out.append(v / np.linalg.norm(v))
        return np.asarray(out, dtype=np.float32)


# --- textprep ---------------------------------------------------------------------------------


def test_embed_text_joins_title_and_description():
    text, cut = embed_text({"title": "A", "description": "b c"}, max_chars=100)
    assert (text, cut) == ("A - b c", False)


def test_truncation_keeps_words_whole():
    rec = {"title": "T", "description": "alpha beta gamma delta"}
    text, cut = embed_text(rec, max_chars=14)  # "T - alpha beta" is 14 chars exactly
    assert (text, cut) == ("T - alpha beta", True)
    text, cut = embed_text(rec, max_chars=16)  # would split "gamma"; back off to a word boundary
    assert (text, cut) == ("T - alpha beta", True)


def test_truncation_hard_cut_when_no_space():
    text, cut = embed_text({"title": "X", "description": "a" * 50}, max_chars=10)
    assert len(text) == 10 and cut


def test_none_description_is_empty():
    assert embed_text({"title": "T", "description": None}, max_chars=50) == ("T - ", False)


def test_text_hash_depends_on_model():
    assert text_hash("x", "m1") != text_hash("x", "m2")
    assert text_hash("x", "m1") == text_hash("x", "m1")


# --- plan -------------------------------------------------------------------------------------


def test_plan_reuse_todo_dropped():
    prev = {"fandom_1": {"hash": "h1", "row": 0}, "fandom_2": {"hash": "old", "row": 1}, "fandom_9": {"hash": "h9", "row": 2}}
    hashes = {"fandom_1": "h1", "fandom_2": "new", "fandom_3": "h3"}
    reuse, todo, dropped = plan(hashes, prev)
    assert reuse == {"fandom_1": 0}
    assert todo == ["fandom_2", "fandom_3"]
    assert dropped == ["fandom_9"]


# --- run --------------------------------------------------------------------------------------


def test_first_run_encodes_everything(tmp_path):
    enc = FakeEncoder()
    stats = run(enc, records(), tmp_path, model_name=MODEL, max_chars=2000)
    assert stats["encoded"] == 12 and stats["reused"] == 0 and stats["dropped"] == 0
    X, ids, meta = load_embeddings(tmp_path)
    assert X.shape == (12, FakeEncoder.dim) and X.dtype == np.float32
    assert np.allclose(np.linalg.norm(X, axis=1), 1, atol=1e-5)
    assert ids == [r["id"] for r in records()]
    assert meta["model"] == MODEL


def test_second_run_encodes_only_changes(tmp_path):
    run(FakeEncoder(), records(), tmp_path, model_name=MODEL, max_chars=2000)
    X1, ids1, _ = load_embeddings(tmp_path)
    recs = records()
    recs[4]["description"] += " (edited)"
    enc = FakeEncoder()
    stats = run(enc, recs, tmp_path, model_name=MODEL, max_chars=2000)
    assert stats["encoded"] == 1 and stats["reused"] == 11
    assert len(enc.seen) == 1 and "(edited)" in enc.seen[0]
    X2, ids2, _ = load_embeddings(tmp_path)
    for i, rid in enumerate(ids2):
        if rid != recs[4]["id"]:
            assert np.array_equal(X2[i], X1[ids1.index(rid)])  # reused vectors are copied exactly


def test_removed_creator_dropped_and_rows_stay_aligned(tmp_path):
    run(FakeEncoder(), records(), tmp_path, model_name=MODEL, max_chars=2000)
    X1, ids1, _ = load_embeddings(tmp_path)
    recs = records()
    removed = recs.pop(2)
    stats = run(FakeEncoder(), recs, tmp_path, model_name=MODEL, max_chars=2000)
    assert stats["dropped"] == 1 and stats["encoded"] == 0
    X2, ids2, _ = load_embeddings(tmp_path)
    assert removed["id"] not in ids2 and X2.shape[0] == 11
    for i, rid in enumerate(ids2):
        assert np.array_equal(X2[i], X1[ids1.index(rid)])


def test_model_change_reencodes_everything(tmp_path):
    run(FakeEncoder(), records(), tmp_path, model_name=MODEL, max_chars=2000)
    stats = run(FakeEncoder(), records(), tmp_path, model_name="other-model", max_chars=2000)
    assert stats["encoded"] == 12


def test_same_title_pages_get_separate_rows(tmp_path):
    run(FakeEncoder(), records(), tmp_path, model_name=MODEL, max_chars=2000)
    X, ids, _ = load_embeddings(tmp_path)
    a, b = ids.index("fandom_449281"), ids.index("fandom_372805")  # TARGET / Target
    assert a != b and not np.array_equal(X[a], X[b])


def test_truncation_counted(tmp_path):
    stats = run(FakeEncoder(), records(), tmp_path, model_name=MODEL, max_chars=30)
    assert stats["truncated"] > 0


def test_rejects_unnormalised_encoder(tmp_path):
    class Bad(FakeEncoder):
        def encode(self, texts):
            return super().encode(texts) * 2

    with pytest.raises(ValueError, match="not normalised"):
        run(Bad(), records(), tmp_path, model_name=MODEL, max_chars=2000)
    assert not (tmp_path / "embeddings.npy").exists()


def test_load_detects_mismatched_files(tmp_path):
    run(FakeEncoder(), records(), tmp_path, model_name=MODEL, max_chars=2000)
    np.save(tmp_path / "embeddings.npy", np.zeros((3, 8), dtype=np.float32))
    with pytest.raises(ValueError, match="do not match"):
        load_embeddings(tmp_path)
