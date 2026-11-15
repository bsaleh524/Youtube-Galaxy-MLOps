import numpy as np

from pipeline.index_format import IndexData, quantize_rows
from pipeline.search import brute_force_search, two_stage_search
from pipeline.synthetic import make_synthetic


def _build(n, dim, k, seed):
    v, offsets, cents, _ = make_synthetic(n=n, dim=dim, k=k, seed=seed)
    q, s = quantize_rows(v)
    return v, IndexData(q, s, offsets), cents


def test_two_stage_matches_brute_force_when_probing_everything():
    _v, idx, cents = _build(400, 32, 8, 0)
    rng = np.random.default_rng(1)
    for _ in range(10):
        query = rng.normal(size=32).astype(np.float32)
        got = two_stage_search(query, cents, idx, k=10, max_probe=8, min_candidates=400)
        want = brute_force_search(query, idx, k=10)
        assert [r for r, _ in got] == [r for r, _ in want]


def test_high_agreement_on_synthetic():
    v, idx, cents = _build(5000, 384, 40, 0)
    rng = np.random.default_rng(2)
    overlaps = []
    for row in rng.choice(5000, 50, replace=False):
        query = v[row] + rng.normal(scale=0.02, size=384).astype(np.float32)
        a = {r for r, _ in two_stage_search(query, cents, idx, k=10, min_candidates=500)}
        b = {r for r, _ in brute_force_search(query, idx, k=10)}
        overlaps.append(len(a & b) / 10)
    assert np.mean(overlaps) >= 0.9


def test_empty_clusters_and_max_probe_stop():
    _v, idx, cents = _build(300, 16, 6, 0)
    # make clusters 1 and 2 empty by collapsing their ranges into cluster 3
    off = idx.offsets.copy()
    off[2] = off[1]
    off[3] = off[1]
    idx2 = IndexData(idx.q, idx.scales, off)
    query = cents[0]
    got = two_stage_search(query, cents, idx2, k=1000, probe_min=1, min_candidates=10**9, max_probe=2)
    sizes = np.diff(off)
    order = np.lexsort((np.arange(6), -(cents @ (query / np.linalg.norm(query)))))
    assert len(got) == sizes[order[:2]].sum()


def test_k_larger_than_candidates_returns_all_sorted():
    _v, idx, cents = _build(200, 16, 5, 0)
    got = two_stage_search(cents[0], cents, idx, k=10_000, probe_min=1, min_candidates=1, max_probe=1)
    top_cluster = int(np.argmax(cents @ cents[0]))
    assert len(got) == idx.offsets[top_cluster + 1] - idx.offsets[top_cluster]
    scores = [s for _, s in got]
    assert scores == sorted(scores, reverse=True)


def test_zero_query_returns_empty():
    _v, idx, cents = _build(100, 16, 4, 0)
    assert two_stage_search(np.zeros(16, np.float32), cents, idx) == []
    assert brute_force_search(np.zeros(16, np.float32), idx) == []


def test_unnormalized_query_same_as_normalized():
    _v, idx, cents = _build(300, 16, 6, 0)
    query = np.random.default_rng(0).normal(size=16).astype(np.float32)
    a = two_stage_search(query * 37.5, cents, idx)
    b = two_stage_search(query / np.linalg.norm(query), cents, idx)
    assert [r for r, _ in a] == [r for r, _ in b]
    assert np.allclose([s for _, s in a], [s for _, s in b], atol=1e-6)


def test_results_sorted_score_desc_row_asc():
    v, idx, _cents = _build(300, 16, 6, 0)
    q = idx.q.copy()
    q[5] = q[4]
    idx2 = IndexData(q, idx.scales.copy(), idx.offsets)
    idx2.scales[5] = idx2.scales[4]
    got = brute_force_search(v[4], idx2, k=300)
    keys = [(-s, r) for r, s in got]
    assert keys == sorted(keys)


def test_duplicate_vectors_and_titles_both_returned():
    _v, idx, cents = _build(300, 16, 6, 0)
    q = idx.q.copy()
    scales = idx.scales.copy()
    q[1] = q[0]
    scales[1] = scales[0]
    idx2 = IndexData(q, scales, idx.offsets)
    query = q[0].astype(np.float32) * scales[0] / 127
    got = two_stage_search(query, cents, idx2, k=5)
    assert [r for r, _ in got[:2]] == [0, 1]
    assert got[0][1] == got[1][1]
