"""Embed creators incrementally: only new or changed texts are encoded, removed creators dropped.

    uv run python -m pipeline.embed [--max-chars 2000] [--batch-size 64]

Reads the current snapshot (data/raw/current). Writes data/embeddings/:
    embeddings.npy   float32 (n, dim), L2-normalised, row i belongs to rows.json ids[i]
    rows.json        {model, dim, max_chars, snapshot_sha256, embeddings_sha256, ids, hashes}
Rows follow snapshot order (numeric pageid). Rows are internal; everything downstream keys on id.
The last stdout line is a JSON summary (for Airflow XCom in Plan 6).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Protocol

import numpy as np

from pipeline.config import load_settings
from pipeline.snapshot import load_current
from pipeline.textprep import DEFAULT_MAX_CHARS, embed_chunks, protected_words, text_hash

NORM_TOLERANCE = 1e-3


class Encoder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_embeddings(out_dir: Path) -> tuple[np.ndarray, list[str], dict]:
    """Return (matrix, ids, rows metadata). Raises ValueError if the two files don't belong together."""
    out_dir = Path(out_dir)
    meta = json.loads((out_dir / "rows.json").read_text(encoding="utf-8"))
    path = out_dir / "embeddings.npy"
    if _sha256_file(path) != meta["embeddings_sha256"]:
        raise ValueError("embeddings.npy and rows.json do not match (interrupted write?)")
    X = np.load(path)
    if X.shape != (len(meta["ids"]), meta["dim"]):
        raise ValueError("embeddings.npy and rows.json do not match (shape)")
    return X, meta["ids"], meta


def _previous(out_dir: Path) -> tuple[np.ndarray | None, dict[str, dict]]:
    if not (Path(out_dir) / "rows.json").exists():
        return None, {}
    X, ids, meta = load_embeddings(out_dir)
    return X, {rid: {"hash": h, "row": i} for i, (rid, h) in enumerate(zip(ids, meta["hashes"], strict=True))}


def plan(hashes: dict[str, str], prev: dict[str, dict]) -> tuple[dict[str, int], list[str], list[str]]:
    """Split ids into (reuse: id -> previous row, todo: ids to encode, dropped: ids no longer present)."""
    reuse = {rid: prev[rid]["row"] for rid, h in hashes.items() if rid in prev and prev[rid]["hash"] == h}
    todo = [rid for rid in hashes if rid not in reuse]
    dropped = sorted(set(prev) - set(hashes))
    return reuse, todo, dropped


def run(
    encoder: Encoder,
    records: list[dict],
    out_dir: Path,
    model_name: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    snapshot_sha256: str | None = None,
    batch_size: int = 256,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    texts, hashes, truncated = {}, {}, 0
    protected = protected_words(records)
    for r in records:
        chunks, cut = embed_chunks(r, protected, max_chars, 1)
        texts[r["id"]] = chunks[0]
        hashes[r["id"]] = text_hash(chunks, model_name)
        truncated += cut

    X_prev, prev = _previous(out_dir)
    reuse, todo, dropped = plan(hashes, prev)

    t0 = time.perf_counter()
    new_vecs: dict[str, np.ndarray] = {}
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        V = np.asarray(encoder.encode([texts[i] for i in batch]), dtype=np.float32)
        norms = np.linalg.norm(V, axis=1)
        if not np.all(np.abs(norms - 1) < NORM_TOLERANCE):
            raise ValueError("encoder output is not normalised")
        new_vecs.update(zip(batch, V, strict=True))
    seconds = time.perf_counter() - t0

    ids = [r["id"] for r in records]
    if not ids:
        raise ValueError("no records to embed")
    dim = next(iter(new_vecs.values())).shape[0] if new_vecs else X_prev.shape[1]
    X = np.empty((len(ids), dim), dtype=np.float32)
    for i, rid in enumerate(ids):
        X[i] = new_vecs[rid] if rid in new_vecs else X_prev[reuse[rid]]

    # Write the matrix first, then rows.json (which records the matrix's sha256) as the commit point.
    tmp_npy = out_dir / "embeddings.npy.tmp"
    with open(tmp_npy, "wb") as f:
        np.save(f, X)
    meta = {
        "model": model_name,
        "dim": dim,
        "max_chars": max_chars,
        "snapshot_sha256": snapshot_sha256,
        "embeddings_sha256": _sha256_file(tmp_npy),
        "ids": ids,
        "hashes": [hashes[i] for i in ids],
    }
    tmp_rows = out_dir / "rows.json.tmp"
    tmp_rows.write_text(json.dumps(meta), encoding="utf-8")
    os.replace(tmp_npy, out_dir / "embeddings.npy")
    os.replace(tmp_rows, out_dir / "rows.json")

    return {
        "creators": len(ids),
        "encoded": len(todo),
        "reused": len(reuse),
        "dropped": len(dropped),
        "truncated": truncated,
        "seconds": round(seconds, 2),
        "per_second": round(len(todo) / seconds, 1) if todo and seconds > 0 else None,
    }


class SentenceTransformerEncoder:
    def __init__(self, model_name: str, batch_size: int):
        from sentence_transformers import SentenceTransformer

        from pipeline.device import best_device

        self.device = best_device()
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device=self.device)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, convert_to_numpy=True
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    ap.add_argument("--batch-size", type=int, default=64)
    a = ap.parse_args(argv)
    settings = load_settings()
    records, manifest = load_current(settings.data_dir / "raw")
    encoder = SentenceTransformerEncoder(settings.embedding_model, a.batch_size)
    stats = run(
        encoder,
        records,
        settings.data_dir / "embeddings",
        model_name=settings.embedding_model,
        max_chars=a.max_chars,
        snapshot_sha256=manifest["sha256"],
        batch_size=1024,
    )
    print(json.dumps({**stats, "device": encoder.device, "snapshot_sha256": manifest["sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
