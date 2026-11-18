import numpy as np
import pytest

from pipeline.clusterlib import (
    assign_nearest,
    fit_kmeans,
    leaders,
    procrustes_align,
    silhouette_cosine,
    size_stats,
    top_neighbors,
)


def blobs(n_per=50, k=4, dim=16, spread=0.05, seed=0):
    """k well-separated clusters of unit vectors."""
    rng = np.random.default_rng(seed)
    centres = np.eye(dim)[:k]
    X = np.concatenate([c + spread * rng.normal(size=(n_per, dim)) for c in centres])
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    truth = np.repeat(np.arange(k), n_per)
    return X.astype(np.float32), truth


def same_partition(a, b):
    """True if label vectors describe the same grouping, whatever the label numbers."""
    pairs = set(zip(a.tolist(), b.tolist(), strict=True))
    return len(pairs) == len(set(a.tolist())) == len(set(b.tolist()))


def test_kmeans_recovers_blobs_with_unit_centroids():
    X, truth = blobs()
    labels, C = fit_kmeans(X, 4)
    assert same_partition(labels, truth)
    assert np.allclose(np.linalg.norm(C, axis=1), 1, atol=1e-5)
    assert labels.dtype == np.int32


def test_kmeans_is_deterministic():
    X, _ = blobs()
    a, ca = fit_kmeans(X, 4, seed=42)
    b, cb = fit_kmeans(X, 4, seed=42)
    assert np.array_equal(a, b) and np.array_equal(ca, cb)


def test_assign_nearest_matches_kmeans_on_training_points():
    X, _ = blobs()
    labels, C = fit_kmeans(X, 4)
    assert np.array_equal(assign_nearest(X, C, block=17), labels)


def test_top_neighbors_matches_brute_force_and_excludes_self():
    X, _ = blobs(n_per=30, spread=0.3)
    nb = top_neighbors(X, k=5, block=7)
    S = X @ X.T
    np.fill_diagonal(S, -np.inf)
    for i in range(len(X)):
        assert i not in nb[i]
        expect = np.argsort(-S[i], kind="stable")[:5]
        assert np.allclose(S[i, nb[i]], S[i, expect])  # same scores, best first


def test_top_neighbors_k_larger_than_n():
    X, _ = blobs(n_per=2, k=2)
    nb = top_neighbors(X, k=10)
    assert nb.shape == (4, 3)


def test_procrustes_recovers_rotation_scale_translation():
    rng = np.random.default_rng(1)
    old = rng.normal(size=(100, 2))
    theta = 0.7
    R = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    new = 2.5 * old @ R + np.array([3.0, -1.0])
    aligned = procrustes_align(new, old)
    assert np.allclose(aligned, old, atol=1e-6)


def test_procrustes_fits_on_shared_rows_only():
    rng = np.random.default_rng(2)
    old = rng.normal(size=(50, 3))
    new = np.concatenate([old * 3 + 1, rng.normal(size=(10, 3))])  # 10 extra new-only points
    aligned = procrustes_align(new, old, shared_new=np.arange(50), shared_old=np.arange(50))
    assert aligned.shape == new.shape
    assert np.allclose(aligned[:50], old, atol=1e-6)


def test_silhouette_high_for_separated_blobs():
    X, truth = blobs()
    assert silhouette_cosine(X, truth) > 0.8


def test_silhouette_single_cluster_is_none():
    X, _ = blobs()
    assert silhouette_cosine(X, np.zeros(len(X), dtype=np.int32)) is None


def test_empty_cluster_handled_by_leaders_and_stats():
    X, _ = blobs()
    labels, C = fit_kmeans(X, 4)
    C5 = np.concatenate([C, np.eye(16, dtype=np.float32)[10:11]])  # cluster 4 has no members
    lead = leaders(X, labels, C5)
    assert set(lead) == {0, 1, 2, 3}
    for c, row in lead.items():
        members = np.flatnonzero(labels == c)
        assert row in members
        assert row == members[np.argmax(X[members] @ C5[c])]
    stats = size_stats(labels, 5)
    assert stats == {"min": 0, "median": 50.0, "max": 50, "empty": 1, "under_20": 0}


@pytest.mark.parametrize("bad_k", [0, 1000])
def test_fit_kmeans_rejects_bad_k(bad_k):
    X, _ = blobs()
    with pytest.raises(ValueError):
        fit_kmeans(X, bad_k)
