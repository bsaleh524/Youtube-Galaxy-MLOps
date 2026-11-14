"""Index format round-trip, two-stage vs brute force, and the cross-language fixture for the Worker."""

import json
from pathlib import Path

import numpy as np

from pipeline.index_format import (
    SearchParams,
    brute_force_search,
    l2_normalize,
    probe_clusters,
    quantize_rows,
    read_index,
    read_meta_record,
    two_stage_search,
)
from pipeline.spike_synth import build

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "worker" / "test" / "fixtures"
FIXTURE_PARAMS = SearchParams(k=5, min_probe=2, max_probe=4, min_candidates=60, max_candidates=150)


def test_quantize_roundtrip_preserves_cosine():
    rng = np.random.default_rng(1)
    v = l2_normalize(rng.standard_normal((50, 384)))
    q, s = quantize_rows(v)
    deq = q.astype(np.float32) * s[:, None]
    cos = (deq * v).sum(1) / np.linalg.norm(deq, axis=1)
    assert cos.min() > 0.999


def test_build_and_read(tmp_path):
    m = build(tmp_path, n=500, dim=32, n_clusters=10, seed=3)
    idx = read_index(tmp_path / "index.bin", tmp_path / "centroids.bin")
    assert idx.n == 500 and idx.data.shape == (500, 32) and len(idx.offsets) == 11
    assert idx.offsets[-1] == 500 and m["n"] == 500
    rec = read_meta_record(tmp_path / "meta.bin", 7)
    assert rec["id"].startswith("synth_") and "cluster" in rec


def test_meta_cluster_matches_index_order(tmp_path):
    build(tmp_path, n=300, dim=16, n_clusters=6, seed=4)
    idx = read_index(tmp_path / "index.bin", tmp_path / "centroids.bin")
    for c in range(6):
        for row in (idx.offsets[c], idx.offsets[c + 1] - 1):
            if idx.offsets[c] < idx.offsets[c + 1]:
                assert read_meta_record(tmp_path / "meta.bin", int(row))["cluster"] == c


def test_probe_respects_bounds(tmp_path):
    build(tmp_path, n=2000, dim=32, n_clusters=20, seed=5)
    idx = read_index(tmp_path / "index.bin", tmp_path / "centroids.bin")
    p = SearchParams(min_probe=3, max_probe=6, min_candidates=400, max_candidates=900)
    q = l2_normalize(np.random.default_rng(0).standard_normal(32))
    chosen = probe_clusters(idx, q, p)
    assert 3 <= len(chosen) <= 6
    assert len(set(chosen)) == len(chosen)


def test_two_stage_agrees_with_brute_force_on_member_queries(tmp_path):
    build(tmp_path, n=3000, dim=64, n_clusters=30, seed=6)
    idx = read_index(tmp_path / "index.bin", tmp_path / "centroids.bin")
    deq = l2_normalize(idx.dequantized())
    rng = np.random.default_rng(7)
    hits = 0
    for row in rng.choice(idx.n, 50, replace=False):
        q = l2_normalize(deq[row] + 0.02 * rng.standard_normal(64))
        ts = {r for r, _ in two_stage_search(idx, q, SearchParams(k=10, min_candidates=300))}
        bf = {r for r, _ in brute_force_search(idx, q, 10)}
        hits += len(ts & bf)
    assert hits / 500 > 0.8  # synthetic clusters overlap; real-data agreement is measured by the gate


def test_two_stage_equals_brute_force_when_probing_everything(tmp_path):
    build(tmp_path, n=1000, dim=32, n_clusters=10, seed=8)
    idx = read_index(tmp_path / "index.bin", tmp_path / "centroids.bin")
    p = SearchParams(k=10, min_probe=10, max_probe=10)
    for q in l2_normalize(np.random.default_rng(9).standard_normal((20, 32))):
        assert [r for r, _ in two_stage_search(idx, q, p)] == [r for r, _ in brute_force_search(idx, q, 10)]


def test_write_cross_language_fixture(tmp_path):
    """Regenerates worker/test/fixtures/ deterministically; the vitest suite asserts the same results."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    build(FIXTURE_DIR, n=400, dim=32, n_clusters=8, seed=11, bio_len=40)
    (FIXTURE_DIR / "index_manifest.json").unlink()  # timestamped; not needed by tests
    idx = read_index(FIXTURE_DIR / "index.bin", FIXTURE_DIR / "centroids.bin")
    rng = np.random.default_rng(12)
    cases = []
    for _ in range(12):
        q = l2_normalize(rng.standard_normal(32)).astype(np.float32)
        cases.append(
            {
                "query": [float(x) for x in q],
                "probe": probe_clusters(idx, q, FIXTURE_PARAMS),
                "two_stage": [[r, round(s, 5)] for r, s in two_stage_search(idx, q, FIXTURE_PARAMS)],
                "brute": [[r, round(s, 5)] for r, s in brute_force_search(idx, q, FIXTURE_PARAMS.k)],
            }
        )
    params = {
        "k": FIXTURE_PARAMS.k,
        "minProbe": FIXTURE_PARAMS.min_probe,
        "maxProbe": FIXTURE_PARAMS.max_probe,
        "minCandidates": FIXTURE_PARAMS.min_candidates,
        "maxCandidates": FIXTURE_PARAMS.max_candidates,
    }
    (FIXTURE_DIR / "expected.json").write_text(json.dumps({"params": params, "cases": cases}, indent=1))
    assert len(cases) == 12
