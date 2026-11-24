"""Two-stage (centroids → members) search over the int8 index. Mirrors worker/src/search.ts exactly.

1. Normalise the query (zero query → []).
2. Score all centroids; order clusters by score desc, cluster id asc.
3. Probe clusters in that order until probed >= probe_min and candidates >= min_candidates,
   or probed == max_probe, or clusters run out.
4. Score every member of the probed clusters; return the top k as (row, score),
   sorted by score desc then row asc.
"""

from __future__ import annotations

import numpy as np

from pipeline.index_format import IndexData


def _normalise(query: np.ndarray) -> np.ndarray | None:
    query = np.asarray(query, dtype=np.float32)
    norm = float(np.linalg.norm(query))
    if norm == 0.0 or not np.isfinite(norm):
        return None
    return query / norm


def _score_rows(query: np.ndarray, index: IndexData, rows: np.ndarray) -> np.ndarray:
    dots = index.q[rows].astype(np.float32) @ query
    return dots * (index.scales[rows] / np.float32(127))


def _top_k(rows: np.ndarray, scores: np.ndarray, k: int) -> list[tuple[int, float]]:
    if len(rows) == 0 or k <= 0:
        return []
    if len(rows) > k:
        part = np.argpartition(-scores, k - 1)[:k]
        # include ties at the boundary so row-asc tiebreak is exact
        threshold = scores[part].min()
        part = np.nonzero(scores >= threshold)[0]
        rows, scores = rows[part], scores[part]
    order = np.lexsort((rows, -scores))[:k]
    return [(int(rows[i]), float(scores[i])) for i in order]


def two_stage_search(
    query: np.ndarray,
    centroids: np.ndarray,
    index: IndexData,
    k: int = 10,
    probe_min: int = 3,
    min_candidates: int = 1500,
    max_probe: int = 12,
) -> list[tuple[int, float]]:
    q = _normalise(query)
    if q is None:
        return []
    cscores = centroids.astype(np.float32) @ q
    order = np.lexsort((np.arange(len(cscores)), -cscores))
    offsets = index.offsets
    chunks: list[np.ndarray] = []
    candidates = 0
    for c in order:
        probed = len(chunks)
        if probed >= max_probe or (probed >= probe_min and candidates >= min_candidates):
            break
        start, end = int(offsets[c]), int(offsets[c + 1])
        chunks.append(np.arange(start, end))
        candidates += end - start
    rows = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int64)
    return _top_k(rows, _score_rows(q, index, rows), k)


def brute_force_search(query: np.ndarray, index: IndexData, k: int = 10) -> list[tuple[int, float]]:
    q = _normalise(query)
    if q is None:
        return []
    rows = np.arange(index.q.shape[0])
    return _top_k(rows, _score_rows(q, index, rows), k)
