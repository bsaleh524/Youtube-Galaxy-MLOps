"""Binary formats shared by the pipeline (writer) and the Cloudflare Worker (reader).

Mirror of worker/src/indexFormat.ts and worker/src/search.ts. Keep them in sync; the cross-language
fixture (tests/test_index_format.py writes worker/test/fixtures/) catches drift.

All integers/floats are little-endian.

index.bin      header (32 B): b"GXI1", u32 n, u32 dim, u32 n_clusters, u32 format_version, 12 B pad
               u32 cluster_offsets[n_clusters + 1]   row range of each cluster (rows are cluster-ordered)
               f32 scales[n]                          per-row dequantisation scale
               i8  data[n * dim]                      row i ~= data[i] * scales[i]
centroids.bin  header (16 B): b"GXC1", u32 n_clusters, u32 dim, 4 B pad;  f32 data[n_clusters * dim]
meta.bin       header (16 B): b"GXM1", u32 n, 8 B pad;  u32 offsets[n + 1];  utf-8 bytes
               record i = bytes[offsets[i]:offsets[i+1]] is a small JSON object (decoded only for top-k)
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FORMAT_VERSION = 1
INDEX_MAGIC, CENTROID_MAGIC, META_MAGIC = b"GXI1", b"GXC1", b"GXM1"


# ── quantisation ─────────────────────────────────────────────────────────────

def quantize_rows(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric per-row int8 quantisation. Returns (int8 data, float32 scales)."""
    v = np.asarray(vectors, dtype=np.float32)
    maxabs = np.abs(v).max(axis=1)
    maxabs[maxabs == 0] = 1.0
    scales = (maxabs / 127.0).astype(np.float32)
    q = np.clip(np.rint(v / scales[:, None]), -127, 127).astype(np.int8)
    return q, scales


def l2_normalize(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    n = np.linalg.norm(x, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


# ── writers ──────────────────────────────────────────────────────────────────

def cluster_order(labels: np.ndarray, n_clusters: int) -> tuple[np.ndarray, np.ndarray]:
    """Stable row permutation that groups rows by cluster, plus the cluster offsets table."""
    labels = np.asarray(labels)
    order = np.argsort(labels, kind="stable")
    counts = np.bincount(labels, minlength=n_clusters)
    offsets = np.zeros(n_clusters + 1, dtype=np.uint32)
    offsets[1:] = np.cumsum(counts)
    return order, offsets


def write_index(path: Path, vectors_ordered: np.ndarray, offsets: np.ndarray) -> None:
    """vectors_ordered must already be cluster-ordered (see cluster_order) and L2-normalised."""
    n, dim = vectors_ordered.shape
    q, scales = quantize_rows(vectors_ordered)
    with open(path, "wb") as f:
        f.write(INDEX_MAGIC + struct.pack("<IIII", n, dim, len(offsets) - 1, FORMAT_VERSION) + b"\0" * 12)
        f.write(np.asarray(offsets, dtype="<u4").tobytes())
        f.write(scales.astype("<f4").tobytes())
        f.write(q.tobytes())


def write_centroids(path: Path, centroids: np.ndarray) -> None:
    c = l2_normalize(centroids)
    with open(path, "wb") as f:
        f.write(CENTROID_MAGIC + struct.pack("<II", *c.shape) + b"\0" * 4)
        f.write(c.astype("<f4").tobytes())


def write_meta(path: Path, records: list[dict]) -> None:
    blobs = [json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode() for r in records]
    offsets = np.zeros(len(blobs) + 1, dtype="<u4")
    offsets[1:] = np.cumsum([len(b) for b in blobs])
    with open(path, "wb") as f:
        f.write(META_MAGIC + struct.pack("<I", len(blobs)) + b"\0" * 8)
        f.write(offsets.tobytes())
        f.write(b"".join(blobs))


# ── readers + search (Python mirror of the Worker) ───────────────────────────

@dataclass
class Index:
    offsets: np.ndarray  # (C+1,) uint32
    scales: np.ndarray  # (n,) float32
    data: np.ndarray  # (n, dim) int8
    centroids: np.ndarray  # (C, dim) float32

    @property
    def n(self) -> int:
        return self.data.shape[0]

    def dequantized(self) -> np.ndarray:
        return self.data.astype(np.float32) * self.scales[:, None]


def read_index(index_path: Path, centroids_path: Path) -> Index:
    raw = Path(index_path).read_bytes()
    assert raw[:4] == INDEX_MAGIC, "bad index magic"
    n, dim, c, ver = struct.unpack_from("<IIII", raw, 4)
    assert ver == FORMAT_VERSION
    pos = 32
    offsets = np.frombuffer(raw, "<u4", c + 1, pos)
    pos += 4 * (c + 1)
    scales = np.frombuffer(raw, "<f4", n, pos)
    pos += 4 * n
    data = np.frombuffer(raw, np.int8, n * dim, pos).reshape(n, dim)
    craw = Path(centroids_path).read_bytes()
    assert craw[:4] == CENTROID_MAGIC, "bad centroid magic"
    cc, cdim = struct.unpack_from("<II", craw, 4)
    assert (cc, cdim) == (c, dim)
    cents = np.frombuffer(craw, "<f4", cc * cdim, 16).reshape(cc, cdim)
    return Index(offsets, scales, data, cents)


def read_meta_record(meta_path: Path, row: int) -> dict:
    raw = Path(meta_path).read_bytes()
    assert raw[:4] == META_MAGIC
    (n,) = struct.unpack_from("<I", raw, 4)
    offs = np.frombuffer(raw, "<u4", n + 1, 16)
    base = 16 + 4 * (n + 1)
    return json.loads(raw[base + offs[row] : base + offs[row + 1]].decode())


@dataclass
class SearchParams:
    k: int = 10
    min_probe: int = 3
    max_probe: int = 12
    min_candidates: int = 1500
    max_candidates: int = 5000


def probe_clusters(idx: Index, query: np.ndarray, p: SearchParams) -> list[int]:
    """Clusters to scan, nearest centroid first. Same rule as worker/src/search.ts."""
    cs = idx.centroids @ query.astype(np.float32)
    # Stable descending order; ties broken by lower cluster id (matches the TS sort).
    order = sorted(range(len(cs)), key=lambda c: (-float(cs[c]), c))
    chosen, cand = [], 0
    for c in order:
        if len(chosen) >= p.max_probe:
            break
        if len(chosen) >= p.min_probe and cand >= p.min_candidates:
            break
        size = int(idx.offsets[c + 1] - idx.offsets[c])
        if len(chosen) >= p.min_probe and cand + size > p.max_candidates:
            break
        chosen.append(c)
        cand += size
    return chosen


def two_stage_search(idx: Index, query: np.ndarray, p: SearchParams | None = None) -> list[tuple[int, float]]:
    """Returns [(row, score)] best first. Rows are positions in the cluster-ordered index."""
    p = p or SearchParams()
    q = query.astype(np.float32)
    rows = np.concatenate(
        [np.arange(idx.offsets[c], idx.offsets[c + 1]) for c in probe_clusters(idx, q, p)]
    ).astype(np.int64)
    scores = (idx.data[rows].astype(np.float32) @ q) * idx.scales[rows]
    return _topk(rows, scores, p.k)


def brute_force_search(idx: Index, query: np.ndarray, k: int = 10) -> list[tuple[int, float]]:
    scores = (idx.data.astype(np.float32) @ query.astype(np.float32)) * idx.scales
    return _topk(np.arange(idx.n), scores, k)


def _topk(rows: np.ndarray, scores: np.ndarray, k: int) -> list[tuple[int, float]]:
    # Descending score, ties by lower row (matches the TS insertion top-k).
    order = np.lexsort((rows, -scores))[:k]
    return [(int(rows[i]), float(scores[i])) for i in order]
