"""Binary formats shared by the pipeline (writer) and the Worker (reader). Little-endian throughout.

index.bin      magic b"GXIDX1\\0\\0" | u32 n, dim, k | u32 offsets[k+1] | f32 scales[n] | i8 vecs[n*dim]
centroids.bin  magic b"GXCEN1\\0\\0" | u32 k, dim | f32 data[k*dim]
meta.bin       magic b"GXMETA1\\0" | u32 n | u32 byte_offsets[n+1] | UTF-8 blob of compact JSON records

Rows in index.bin and meta.bin are ordered by cluster; offsets[c]..offsets[c+1] are cluster c's rows.
Approximate cosine of a row with a normalised float query: (scale / 127) * sum(q_i * query_i).
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

INDEX_MAGIC = b"GXIDX1\0\0"
CENTROIDS_MAGIC = b"GXCEN1\0\0"
META_MAGIC = b"GXMETA1\0"


@dataclass
class IndexData:
    q: np.ndarray  # int8 (n, dim)
    scales: np.ndarray  # float32 (n,)
    offsets: np.ndarray  # uint32 (k+1,)


def _check_magic(buf: bytes, magic: bytes, name: str) -> None:
    if buf[: len(magic)] != magic:
        raise ValueError(f"bad magic: {name}")


def quantize_rows(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    v = np.asarray(v, dtype=np.float32)
    scales = np.max(np.abs(v), axis=1).astype(np.float32)
    safe = np.where(scales == 0, 1.0, scales)
    q = np.clip(np.rint(v / safe[:, None] * 127), -127, 127).astype(np.int8)
    return q, scales


def write_index(path: Path, data: IndexData) -> None:
    n, dim = data.q.shape
    k = len(data.offsets) - 1
    with open(path, "wb") as f:
        f.write(INDEX_MAGIC)
        f.write(struct.pack("<3I", n, dim, k))
        f.write(np.asarray(data.offsets, dtype="<u4").tobytes())
        f.write(np.asarray(data.scales, dtype="<f4").tobytes())
        f.write(np.ascontiguousarray(data.q, dtype=np.int8).tobytes())


def read_index(path: Path) -> IndexData:
    buf = Path(path).read_bytes()
    _check_magic(buf, INDEX_MAGIC, "index")
    n, dim, k = struct.unpack_from("<3I", buf, 8)
    pos = 20
    offsets = np.frombuffer(buf, dtype="<u4", count=k + 1, offset=pos).astype(np.uint32)
    pos += 4 * (k + 1)
    scales = np.frombuffer(buf, dtype="<f4", count=n, offset=pos).astype(np.float32)
    pos += 4 * n
    q = np.frombuffer(buf, dtype=np.int8, count=n * dim, offset=pos).reshape(n, dim).copy()
    return IndexData(q, scales, offsets)


def write_centroids(path: Path, c: np.ndarray) -> None:
    k, dim = c.shape
    with open(path, "wb") as f:
        f.write(CENTROIDS_MAGIC)
        f.write(struct.pack("<2I", k, dim))
        f.write(np.asarray(c, dtype="<f4").tobytes())


def read_centroids(path: Path) -> np.ndarray:
    buf = Path(path).read_bytes()
    _check_magic(buf, CENTROIDS_MAGIC, "centroids")
    k, dim = struct.unpack_from("<2I", buf, 8)
    return np.frombuffer(buf, dtype="<f4", count=k * dim, offset=16).reshape(k, dim).copy()


def write_meta(path: Path, records: list[dict]) -> None:
    encoded = [
        json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode("utf-8") for r in records
    ]
    offsets = np.zeros(len(encoded) + 1, dtype="<u4")
    offsets[1:] = np.cumsum([len(e) for e in encoded])
    with open(path, "wb") as f:
        f.write(META_MAGIC)
        f.write(struct.pack("<I", len(encoded)))
        f.write(offsets.tobytes())
        f.write(b"".join(encoded))


def read_meta_record(blob: bytes, i: int) -> dict:
    _check_magic(blob, META_MAGIC, "meta")
    (n,) = struct.unpack_from("<I", blob, 8)
    if not 0 <= i < n:
        raise IndexError(i)
    start, end = struct.unpack_from("<2I", blob, 12 + 4 * i)
    base = 12 + 4 * (n + 1)
    return json.loads(blob[base + start : base + end].decode("utf-8"))
