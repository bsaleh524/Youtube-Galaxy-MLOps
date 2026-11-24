"""Synthetic cluster-ordered index data for the Worker spike and the cross-language fixture.

    python -m pipeline.synthetic --out data/spike            # full-size spike files
    python -m pipeline.synthetic --fixture worker/test/fixtures
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from pipeline.index_format import (
    IndexData,
    quantize_rows,
    write_centroids,
    write_index,
    write_meta,
)
from pipeline.search import two_stage_search

FIXTURE_EMPTY_CLUSTERS = (3, 7)
FIXTURE_PARAMS = {"probeMin": 2, "minCandidates": 150, "maxProbe": 5}


def _unit(x: np.ndarray) -> np.ndarray:
    return (x / np.linalg.norm(x, axis=-1, keepdims=True)).astype(np.float32)


def make_synthetic(
    n: int, dim: int, k: int, seed: int, empty: tuple[int, ...] = ()
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    """Return (vectors ordered by cluster, offsets[k+1], centroids, records)."""
    rng = np.random.default_rng(seed)
    centres = _unit(rng.normal(size=(k, dim)))
    weights = rng.lognormal(mean=0.0, sigma=0.5, size=k)
    weights[list(empty)] = 0
    sizes = np.floor(weights / weights.sum() * n).astype(int)
    live = [c for c in range(k) if c not in empty]
    for i in range(n - sizes.sum()):  # distribute the remainder over non-empty clusters
        sizes[live[i % len(live)]] += 1
    offsets = np.zeros(k + 1, dtype=np.uint32)
    offsets[1:] = np.cumsum(sizes)

    vectors = np.empty((n, dim), dtype=np.float32)
    centroids = np.empty((k, dim), dtype=np.float32)
    for c in range(k):
        s, e = offsets[c], offsets[c + 1]
        if e > s:
            vectors[s:e] = _unit(centres[c] + rng.normal(scale=0.06, size=(e - s, dim)))
            centroids[c] = _unit(vectors[s:e].mean(axis=0))
        else:
            centroids[c] = centres[c]
    records = [
        {
            "id": f"syn_{i}",
            "title": f"Synthetic {i}",
            "cluster": int(np.searchsorted(offsets, i, side="right") - 1),
            "url": f"https://example.invalid/{i}",
            "snippet": f"Synthetic creator number {i} for testing."[:40],
        }
        for i in range(n)
    ]
    return vectors, offsets, centroids, records


def write_set(out: Path, vectors, offsets, centroids, records, version: str, model: str) -> IndexData:
    out.mkdir(parents=True, exist_ok=True)
    q, s = quantize_rows(vectors)
    data = IndexData(q, s, offsets)
    write_index(out / "index.bin", data)
    write_centroids(out / "centroids.bin", centroids)
    write_meta(out / "meta.bin", records)
    manifest = {"version": version, "n": len(vectors), "dim": vectors.shape[1], "k": len(offsets) - 1,
                "model": model}
    (out / "index_manifest.json").write_text(json.dumps(manifest))
    return data


def write_fixture(out: Path) -> None:
    vectors, offsets, centroids, records = make_synthetic(
        n=600, dim=384, k=12, seed=1, empty=FIXTURE_EMPTY_CLUSTERS
    )
    vectors[1] = vectors[0]  # two channels with the same text and the same name
    records[0]["title"] = records[1]["title"] = "Target"
    data = write_set(out, vectors, offsets, centroids, records, "fixture-1", "synthetic")

    rng = np.random.default_rng(7)
    queries = _unit(rng.normal(size=(20, 384)))
    queries[:10] = _unit(vectors[rng.choice(600, 10, replace=False)] + rng.normal(scale=0.03, size=(10, 384)))
    (out / "queries.json").write_text(json.dumps(queries.round(7).tolist()))
    queries = np.array(json.loads((out / "queries.json").read_text()), dtype=np.float32)
    p = FIXTURE_PARAMS
    results = {
        str(k): [
            [[r, round(s, 6)] for r, s in two_stage_search(
                qv, centroids, data, k=k, probe_min=p["probeMin"],
                min_candidates=p["minCandidates"], max_probe=p["maxProbe"])]
            for qv in queries
        ]
        for k in (5, 600)
    }
    (out / "expected.json").write_text(json.dumps({"params": p, "results": results}))

    utf8 = [
        {"id": "fandom_1", "title": "ねくろちゃん -Yamaguro Nekuro-", "cluster": 0, "url": "u", "snippet": "🎮 ok"},
        {"id": "fandom_2", "title": "Plain", "cluster": 1, "url": "u2", "snippet": "x"},
        {"id": "fandom_449281", "title": "Target", "cluster": 0, "url": "a", "snippet": "x"},
        {"id": "fandom_372805", "title": "Target", "cluster": 0, "url": "b", "snippet": "y"},
    ]
    write_meta(out / "meta_utf8.bin", utf8)
    (out / "meta_utf8.json").write_text(json.dumps(utf8, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", type=Path)
    g.add_argument("--fixture", type=Path)
    ap.add_argument("--n", type=int, default=20800)
    ap.add_argument("--dim", type=int, default=384)
    ap.add_argument("--k", type=int, default=120)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    if args.fixture:
        write_fixture(args.fixture)
        target = args.fixture
    else:
        v, off, c, recs = make_synthetic(args.n, args.dim, args.k, args.seed)
        write_set(args.out, v, off, c, recs, version="spike-synthetic-1", model="synthetic")
        target = args.out
    for f in sorted(target.iterdir()):
        print(f"{f.name:22s} {f.stat().st_size / 1e6:8.3f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
