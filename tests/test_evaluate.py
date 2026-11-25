import json

import numpy as np
import pytest

from pipeline import evaluate as ev
from pipeline.config import QUERY_PREFIX
from pipeline.index_format import IndexData, quantize_rows, write_centroids, write_index, write_meta

DIM = 8
NAMES = [
    "Alpha",
    "Beta",
    "Music",
]  # cluster c, rows 4c..4c+3; "Music0".. never collide with topic word


def _vectors() -> np.ndarray:
    rows = []
    for c in range(3):
        for j in range(4):
            v = np.zeros(DIM, dtype=np.float32)
            v[c] = 1.0
            if j:
                v[3 + j] = 0.1 * j  # row j=1 is the closest to row 0 of its cluster
            rows.append(v)
    return np.stack(rows)


def make_build(root, version="v1"):
    b = root / "artifacts" / "galaxy" / version
    (b / "worker").mkdir(parents=True)
    v = _vectors()
    q, s = quantize_rows(v)
    write_index(
        b / "worker" / "index.bin", IndexData(q, s, np.array([0, 4, 8, 12], dtype=np.uint32))
    )
    cents = np.stack([v[4 * c : 4 * c + 4].mean(0) for c in range(3)])
    write_centroids(
        b / "worker" / "centroids.bin", cents / np.linalg.norm(cents, axis=1, keepdims=True)
    )
    recs = [
        {
            "id": f"fandom_{r}",
            "title": f"{NAMES[r // 4]}{r % 4}",
            "cluster": NAMES[r // 4],
            "url": "u",
            "snippet": "s",
        }
        for r in range(12)
    ]
    write_meta(b / "worker" / "meta.bin", recs)
    (b / "worker" / "index_manifest.json").write_text(
        json.dumps(
            {
                "version": version,
                "n": 12,
                "dim": DIM,
                "k": 3,
                "model": "m",
                "topic_words": ["music"],
            }
        )
    )
    (b / "manifest.json").write_text(json.dumps({"version": version, "creators": 12}))
    return b


class FakeEncoder:
    def __init__(self):
        self.seen = []

    def __call__(self, texts):
        self.seen.extend(texts)
        out = []
        for t in texts:
            v = np.zeros(DIM, dtype=np.float32)
            v[1 if "beta things" in t else 0] = 1.0
            out.append(v)
        return np.stack(out)


def test_load_build(tmp_path):
    b = ev.load_build(make_build(tmp_path))
    assert b.version == "v1"
    assert b.ids[:2] == ["fandom_0", "fandom_1"]
    assert b.titles[5] == "Beta1"
    assert b.topic_words == {"music"}
    assert b.index.q.shape == (12, DIM)


def test_answer_named_creator_uses_its_vector_and_drops_itself(tmp_path):
    b = ev.load_build(make_build(tmp_path))
    enc = FakeEncoder()
    kind, two, brute = ev.answer(b, "channels like alpha0", enc)
    assert kind == "similar"
    assert enc.seen == []  # no embedding for a named creator
    assert 0 not in two and 0 not in brute
    assert two[:3] == [1, 2, 3]
    assert len(two) == 8 and len(brute) == 8


def test_answer_topic_uses_prefixed_query(tmp_path):
    b = ev.load_build(make_build(tmp_path))
    enc = FakeEncoder()
    kind, two, _ = ev.answer(b, "beta things", enc)
    assert kind == "topic"
    assert enc.seen == [QUERY_PREFIX + "beta things"]
    assert set(two[:4]) == {4, 5, 6, 7}


def test_evaluate_report_shape_and_values(tmp_path):
    bd = make_build(tmp_path)
    qp = tmp_path / "q.yaml"
    qp.write_text(
        "- {question: like alpha0, expected: [Alpha1], status: approved}\n"
        "- {question: beta things, expected: [Beta0, Gamma9], status: draft}\n"
    )
    r = ev.evaluate(bd, qp, FakeEncoder())
    assert r["version"] == "v1"
    assert r["creators"] == 12
    assert isinstance(r["silhouette"], float)
    assert r["search_params"] == {"k": 8, "probe_min": 3, "min_candidates": 1500, "max_probe": 12}
    first, second = r["per_question"]
    assert first["kind"] == "similar" and first["recall_at_8"] == 1.0 and first["rr"] == 1.0
    assert first["got"][0] == "fandom_1"
    assert second["unknown"] == ["Gamma9"] and second["recall_at_8"] == 1.0
    assert r["summary"]["approved"] == {"n": 1, "recall_at_8": 1.0, "mrr": 1.0}
    assert 0.0 <= r["summary"]["agreement"] <= 1.0
    assert len(r["questions_sha256"]) == 64


def test_write_report_outside_build_dir(tmp_path):
    bd = make_build(tmp_path)
    qp = tmp_path / "q.yaml"
    qp.write_text("- {question: like alpha0, expected: [Alpha1], status: draft}\n")
    r = ev.evaluate(bd, qp, FakeEncoder())
    out = ev.write_report(r, tmp_path / "runs")
    assert out == tmp_path / "runs" / "eval-v1" / "report.json"
    assert json.loads(out.read_text())["version"] == "v1"
    md = (out.parent / "report.md").read_text()
    assert "like alpha0" in md and "recall@8" in md
    assert not list(bd.rglob("report*"))


def test_main_scores_newest_build(tmp_path, monkeypatch):
    make_build(tmp_path)
    qp = tmp_path / "q.yaml"
    qp.write_text("- {question: like alpha0, expected: [Alpha1], status: draft}\n")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ev, "make_encoder", lambda settings: FakeEncoder())
    assert ev.main(["--questions", str(qp), "--no-mlflow"]) == 0
    assert (tmp_path / "runs" / "eval-v1" / "report.json").exists()


def test_missing_build_dir_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        ev.load_build(tmp_path / "nope")
