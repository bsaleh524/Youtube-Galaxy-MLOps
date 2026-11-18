"""Clustering building blocks shared by fit mode, assign mode and the cluster-count comparison.

Pure numpy / scipy / scikit-learn (no UMAP, no torch), so the CI test group covers all of it.
Vectors are L2-normalised, so dot product = cosine similarity.
"""

from __future__ import annotations

import numpy as np

SMALL_CLUSTER = 20


def _unit(M: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    return (M / np.where(norms == 0, 1, norms)).astype(np.float32)


def fit_kmeans(X: np.ndarray, k: int, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """KMeans on unit vectors (Euclidean on the sphere ranks like cosine). Returns (labels, unit centroids)."""
    from sklearn.cluster import KMeans

    if not 1 <= k <= len(X):
        raise ValueError(f"k={k} must be between 1 and the number of vectors ({len(X)})")
    km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)
    return km.labels_.astype(np.int32), _unit(km.cluster_centers_)


def assign_nearest(X: np.ndarray, centroids: np.ndarray, block: int = 4096) -> np.ndarray:
    """Label each vector with its highest-cosine centroid (ties: lowest cluster index)."""
    out = np.empty(len(X), dtype=np.int32)
    for s in range(0, len(X), block):
        out[s : s + block] = np.argmax(X[s : s + block] @ centroids.T, axis=1)
    return out


def top_neighbors(X: np.ndarray, k: int = 10, block: int = 2048) -> np.ndarray:
    """Exact top-k cosine neighbours per row, best first, excluding the row itself.

    Works in row blocks so memory stays at block x n floats (~170 MB at 2048 x 20.8K float32).
    Returns int32 (n, min(k, n-1)).
    """
    n = len(X)
    k = min(k, n - 1)
    out = np.empty((n, k), dtype=np.int32)
    for s in range(0, n, block):
        S = X[s : s + block] @ X.T
        rows = np.arange(S.shape[0])
        S[rows, s + rows] = -np.inf  # never your own neighbour
        part = np.argpartition(-S, k - 1, axis=1)[:, :k] if k < n - 1 else np.argsort(-S, axis=1)[:, :k]
        scores = np.take_along_axis(S, part, axis=1)
        order = np.lexsort((part, -scores), axis=1)  # best score first; ties -> lower row
        out[s : s + block] = np.take_along_axis(part, order, axis=1)
    return out


def leaders(X: np.ndarray, labels: np.ndarray, centroids: np.ndarray) -> dict[int, int]:
    """Cluster -> row of the member nearest its centroid. Empty clusters are absent."""
    out: dict[int, int] = {}
    for c in np.unique(labels):
        members = np.flatnonzero(labels == c)
        out[int(c)] = int(members[np.argmax(X[members] @ centroids[c])])
    return out


def silhouette_cosine(X: np.ndarray, labels: np.ndarray, sample: int = 10000, seed: int = 42) -> float | None:
    """Mean silhouette with cosine distance on a fixed random sample; None if fewer than 2 clusters."""
    from sklearn.metrics import silhouette_score

    if len(np.unique(labels)) < 2:
        return None
    size = min(sample, len(X))
    return float(silhouette_score(X, labels, metric="cosine", sample_size=size, random_state=seed))


def procrustes_align(
    new: np.ndarray,
    old: np.ndarray,
    shared_new: np.ndarray | None = None,
    shared_old: np.ndarray | None = None,
) -> np.ndarray:
    """Rotate (reflection allowed), scale uniformly and translate `new` to best match `old`.

    The transform is fitted on the shared rows (new[shared_new] <-> old[shared_old]; by default
    all rows, which must then correspond 1:1) and applied to every row of `new`.
    """
    from scipy.linalg import orthogonal_procrustes

    a = new if shared_new is None else new[shared_new]
    b = old if shared_old is None else old[shared_old]
    if a.shape != b.shape or len(a) < a.shape[1] + 1:
        raise ValueError("need matching shared rows (at least dim + 1) to align layouts")
    mu_a, mu_b = a.mean(axis=0), b.mean(axis=0)
    a0, b0 = a - mu_a, b - mu_b
    R, sigma = orthogonal_procrustes(a0, b0)
    scale = sigma / np.sum(a0 * a0)
    return (new - mu_a) @ R * scale + mu_b


def size_stats(labels: np.ndarray, k: int) -> dict:
    """Cluster size summary. `under_20` counts non-empty clusters smaller than SMALL_CLUSTER."""
    sizes = np.bincount(labels, minlength=k)
    return {
        "min": int(sizes.min()),
        "median": float(np.median(sizes)),
        "max": int(sizes.max()),
        "empty": int(np.sum(sizes == 0)),
        "under_20": int(np.sum((sizes > 0) & (sizes < SMALL_CLUSTER))),
    }
