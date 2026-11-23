import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pipeline.embed import load_embeddings, plan, run

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
    stats = run(FakeEncoder(), records(), tmp_path, model_name=MODEL, max_chars=30, max_chunks=1)
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


# --- chunk averaging (issue #5) ---------------------------------------------------------------

LONG = {"id": "fandom_1", "title": "T", "description": "is " + "word " * 1100}  # ~5500 chars -> 3 chunks


def test_vector_is_normalised_mean_of_chunks(tmp_path):
    enc = FakeEncoder()
    stats = run(enc, [dict(LONG)], tmp_path, MODEL, max_chars=2000, max_chunks=8)
    assert len(enc.seen) == 3 and stats["chunks"] == 3 and stats["encoded"] == 1
    X, _, meta = load_embeddings(tmp_path)
    expect = FakeEncoder().encode(enc.seen).mean(axis=0)
    np.testing.assert_allclose(X[0], expect / np.linalg.norm(expect), atol=1e-6)
    assert meta["max_chunks"] == 8 and meta["text_prep"] == "v2-clean-chunks"


def test_max_chunks_one_is_fix1_only(tmp_path):
    enc = FakeEncoder()
    stats = run(enc, [dict(LONG)], tmp_path, MODEL, max_chars=2000, max_chunks=1)
    assert len(enc.seen) == 1 and stats["truncated"] == 1


def test_changed_bio_reencodes_all_its_chunks(tmp_path):
    other = {"id": "fandom_2", "title": "U", "description": "is a short bio"}
    run(FakeEncoder(), [dict(LONG), other], tmp_path, MODEL, max_chunks=8)
    stats = run(FakeEncoder(), [dict(LONG), other], tmp_path, MODEL, max_chunks=8)
    assert stats["encoded"] == 0 and stats["chunks"] == 0
    changed = {**LONG, "description": LONG["description"] + " more"}
    enc = FakeEncoder()
    stats = run(enc, [changed, other], tmp_path, MODEL, max_chunks=8)
    assert stats["encoded"] == 1 and stats["chunks"] == 3 and len(enc.seen) == 3


def test_chunks_from_different_creators_do_not_mix_across_batches(tmp_path):
    recs = [{**LONG, "id": f"fandom_{i}", "description": f"is n{i} " + "word " * 1100} for i in range(3)]
    run(FakeEncoder(), recs, tmp_path, MODEL, max_chunks=8, batch_size=2)  # batches split creators
    X, _, _ = load_embeddings(tmp_path)
    run(FakeEncoder(), recs, tmp_path / "b", MODEL, max_chunks=8, batch_size=1000)
    Xb, _, _ = load_embeddings(tmp_path / "b")
    np.testing.assert_allclose(X, Xb, atol=1e-6)


def test_first_weight_blends_first_chunk_with_mean_of_rest(tmp_path):
    enc = FakeEncoder()
    run(enc, [dict(LONG)], tmp_path, MODEL, max_chunks=8, first_weight=0.5)
    X, _, meta = load_embeddings(tmp_path)
    V = FakeEncoder().encode(enc.seen)
    expect = 0.5 * V[0] + 0.5 * V[1:].mean(axis=0)
    np.testing.assert_allclose(X[0], expect / np.linalg.norm(expect), atol=1e-6)
    assert meta["first_weight"] == 0.5


def test_first_weight_single_chunk_is_that_chunk(tmp_path):
    enc = FakeEncoder()
    run(enc, [{"id": "fandom_2", "title": "U", "description": "is a short bio"}], tmp_path, MODEL, first_weight=0.5)
    X, _, _ = load_embeddings(tmp_path)
    np.testing.assert_allclose(X[0], FakeEncoder().encode(enc.seen)[0], atol=1e-6)


def test_changing_first_weight_reencodes(tmp_path):
    run(FakeEncoder(), [dict(LONG)], tmp_path, MODEL, max_chunks=8)
    stats = run(FakeEncoder(), [dict(LONG)], tmp_path, MODEL, max_chunks=8, first_weight=0.5)
    assert stats["encoded"] == 1
