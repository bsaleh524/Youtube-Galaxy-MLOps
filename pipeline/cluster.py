"""Cluster creators and lay out the 2D/3D map.

    uv run python -m pipeline.cluster --mode fit [--k N] [--run-id ID] [--no-save]

Fit mode (manual `make recluster` and the first run): KMeans + UMAP 2D/3D, aligned to the
previous model's layout (Procrustes on shared ids), exact top-10 neighbours, silhouette.
Saves the model to data/model/galaxy/ (or data/runs/<run_id>/model/ with --no-save) and a
report to data/runs/<run_id>/fit_report.json. Cluster keys and names are assigned by the
naming step (pipeline/names.py), not here. Assign mode (weekly runs) is added in Task 7.
The last stdout line is a JSON summary.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np

from pipeline import clusterlib
from pipeline.config import load_settings
from pipeline.galaxy_model import GalaxyModel, load_model, save_model

SEED = 42
UMAP_PARAMS = {"metric": "cosine", "n_neighbors": 15, "min_dist": 0.1}
N_NEIGHBORS = 10

ReducerFactory = Callable[[int, int], object]


def umap_factory(n_components: int, seed: int):
    import umap

    return umap.UMAP(n_components=n_components, random_state=seed, **UMAP_PARAMS)


def _align(new: np.ndarray, old_model: GalaxyModel, attr: str, ids: list[str]) -> tuple[np.ndarray, int]:
    pos_old = {rid: i for i, rid in enumerate(old_model.ids)}
    pairs = [(i, pos_old[rid]) for i, rid in enumerate(ids) if rid in pos_old]
    dim = new.shape[1]
    if len(pairs) < dim + 1:
        return new, 0
    idx_new, idx_old = map(np.array, zip(*pairs, strict=True))
    old = getattr(old_model, attr)
    return clusterlib.procrustes_align(new, old, idx_new, idx_old), len(pairs)


def fit(
    X: np.ndarray,
    ids: list[str],
    hashes: list[str],
    k: int,
    prev: GalaxyModel | None,
    embedding_model: str,
    embeddings_sha256: str,
    run_id: str,
    seed: int = SEED,
    reducer_factory: ReducerFactory = umap_factory,
) -> tuple[GalaxyModel, dict]:
    seconds: dict[str, float] = {}

    def timed(name, fn):
        t = time.perf_counter()
        out = fn()
        seconds[name] = round(time.perf_counter() - t, 2)
        return out

    labels, centroids = timed("kmeans", lambda: clusterlib.fit_kmeans(X, k, seed))
    r2, r3 = reducer_factory(2, seed), reducer_factory(3, seed)
    xy2 = timed("layout2d", lambda: np.asarray(r2.fit_transform(X), dtype=np.float32))
    xyz3 = timed("layout3d", lambda: np.asarray(r3.fit_transform(X), dtype=np.float32))
    shared = 0
    if prev is not None:
        xy2, shared = _align(xy2, prev, "xy2", ids)
        xyz3, _ = _align(xyz3, prev, "xyz3", ids)
        xy2, xyz3 = xy2.astype(np.float32), xyz3.astype(np.float32)
    neighbors = timed("neighbors", lambda: clusterlib.top_neighbors(X, N_NEIGHBORS))
    silhouette = timed("silhouette", lambda: clusterlib.silhouette_cosine(X, labels, seed=seed))

    meta = {
        "k": k,
        "seed": seed,
        "fit_run_id": run_id,
        "embedding_model": embedding_model,
        "embeddings_sha256": embeddings_sha256,
        "silhouette": silhouette,
        "cluster_keys": [None] * k,
        "umap": UMAP_PARAMS,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    model = GalaxyModel(meta, centroids, list(ids), list(hashes), labels, xy2, xyz3, neighbors, r2, r3)
    report = {
        "run_id": run_id,
        "mode": "fit",
        "k": k,
        "creators": len(ids),
        "silhouette": silhouette,
        "sizes": clusterlib.size_stats(labels, k),
        "aligned_to_previous": shared > 0,
        "aligned_shared": shared,
        "seconds": seconds,
    }
    return model, report


def main(argv: list[str] | None = None) -> int:
    from pipeline.embed import load_embeddings

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["fit"], default="fit")
    ap.add_argument("--k", type=int, default=None, help="cluster count (default: N_CLUSTERS)")
    ap.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--no-save", action="store_true", help="write the model under the run dir only, without the UMAP pickles")
    a = ap.parse_args(argv)
    settings = load_settings()
    k = a.k or settings.n_clusters

    X, ids, rows = load_embeddings(settings.data_dir / "embeddings")
    live = settings.data_dir / "model" / "galaxy"
    prev = load_model(live) if (live / "model.json").exists() else None
    model, report = fit(
        X, ids, rows["hashes"], k, prev, rows["model"], rows["embeddings_sha256"], a.run_id
    )
    run_dir = settings.data_dir / "runs" / a.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "model" if a.no_save else live
    save_model(model, target, reducers=not a.no_save)
    report["model_dir"] = str(target)
    (run_dir / "fit_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
