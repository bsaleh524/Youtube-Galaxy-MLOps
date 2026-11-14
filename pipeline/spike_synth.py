"""Phase 1 spike: write a synthetic Worker index (default 20,800 x 384, 120 clusters).

    uv run python -m pipeline.spike_synth --out worker/assets
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from pipeline.index_format import (
    cluster_order,
    l2_normalize,
    write_centroids,
    write_index,
    write_meta,
)


def synth(n: int, dim: int, n_clusters: int, seed: int = 0, spread: float = 0.6):
    rng = np.random.default_rng(seed)
    centers = l2_normalize(rng.standard_normal((n_clusters, dim)))
    # Uneven cluster sizes, like real KMeans output.
    weights = rng.dirichlet(np.full(n_clusters, 3.0))
    labels = rng.choice(n_clusters, size=n, p=weights)
    vecs = l2_normalize(centers[labels] + spread * rng.standard_normal((n, dim)) / np.sqrt(dim) * 3)
    return vecs.astype(np.float32), labels


def build(out: Path, n: int, dim: int, n_clusters: int, seed: int = 0, bio_len: int = 400) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    vecs, labels = synth(n, dim, n_clusters, seed)
    order, offsets = cluster_order(labels, n_clusters)
    ordered = vecs[order]
    centroids = np.stack([ordered[offsets[c] : offsets[c + 1]].mean(0) for c in range(n_clusters)])
    write_index(out / "index.bin", ordered, offsets)
    write_centroids(out / "centroids.bin", centroids)
    bio = "Synthetic creator bio used for the Worker CPU spike. " * 7
    write_meta(
        out / "meta.bin",
        [
            {
                "id": f"synth_{int(i)}",
                "title": f"Synthetic Creator {int(i)}",
                "cluster": int(labels[i]),
                "url": f"https://youtube.fandom.com/wiki/Synthetic_{int(i)}",
                "bio": bio[:bio_len],
            }
            for i in order
        ],
    )
    manifest = {
        "version": f"synthetic-{time.strftime('%Y%m%d%H%M%S')}",
        "n": n,
        "dim": dim,
        "n_clusters": n_clusters,
        "files": {p.name: p.stat().st_size for p in sorted(out.glob("*.bin"))},
    }
    (out / "index_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("worker/assets"))
    ap.add_argument("--n", type=int, default=20_800)
    ap.add_argument("--dim", type=int, default=384)
    ap.add_argument("--clusters", type=int, default=120)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    print(json.dumps(build(a.out, a.n, a.dim, a.clusters, a.seed), indent=2))


if __name__ == "__main__":
    main()
