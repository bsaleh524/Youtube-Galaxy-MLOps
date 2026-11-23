"""Cluster creators and lay out the 2D/3D map.

    uv run python -m pipeline.cluster [--mode assign]                    weekly (default)
    uv run python -m pipeline.cluster --mode fit [--k N] [--run-id ID] [--no-save]

Fit mode (manual `make recluster` and the first run): KMeans + UMAP 2D/3D, aligned to the
previous model's layout (Procrustes on shared ids), exact top-10 neighbours, silhouette.
Saves the model to data/model/galaxy/ (or data/runs/<run_id>/model/ with --no-save) and a
report to data/runs/<run_id>/fit_report.json. The naming step (pipeline/names.py) then gives
each cluster a stable key, a name and a colour, and writes unnamed_clusters.md and naming packs
to the run dir for the owner to review.

Assign mode (weekly) keeps cluster identity fixed: creators whose id and text hash are
unchanged keep their cluster and coordinates byte-for-byte; new or edited creators go to the
nearest centroid and are placed with the saved UMAP reducers; removed creators are dropped.
Neighbours and centroids are recomputed. Keys, names and colours are never touched. When the
share of creators placed by assign since the last fit exceeds DRIFT_RECOMMEND it logs
"re-cluster recommended" but still succeeds. The report goes to data/runs/<run_id>/assign_report.json.
The last stdout line is a JSON summary.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np

from pipeline import clusterlib, names
from pipeline.config import load_settings
from pipeline.galaxy_model import GalaxyModel, load_model, save_model

SEED = 42
UMAP_PARAMS = {"metric": "cosine", "n_neighbors": 15, "min_dist": 0.1}
N_NEIGHBORS = 10
DRIFT_RECOMMEND = 0.15

log = logging.getLogger(__name__)

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


def name_model(
    model: GalaxyModel,
    X: np.ndarray,
    texts: list[str],
    prev: GalaxyModel | None,
    seed_names: dict[str, str],
    owner_names: dict[str, str],
    fresh: bool = False,
) -> dict:
    """Fill model.meta["cluster_keys"] and model.registry; return the naming report.

    fresh=True ignores the previous model's names and colours and bootstraps from the seed labels
    again (after a re-embed, old centroids no longer describe the same groups; issue #5).
    """
    if fresh:
        prev = None
    prev_keys = prev.meta.get("cluster_keys") if prev is not None else None
    usable = prev is not None and prev.registry is not None and bool(prev_keys) and all(prev_keys)
    keys, registry, report = names.name_clusters(
        model.labels,
        model.ids,
        model.centroids,
        texts,
        prev.registry if usable else None,
        prev.centroids if usable else None,
        prev_keys if usable else None,
        seed_names,
        owner_names,
    )
    model.meta["cluster_keys"] = keys
    model.registry = registry
    return report


def _read_json(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def assign(
    X: np.ndarray,
    ids: list[str],
    hashes: list[str],
    model: GalaxyModel,
    embeddings_sha256: str,
    run_id: str,
    n_neighbors: int = N_NEIGHBORS,
) -> tuple[GalaxyModel, dict]:
    """Place the current creators into the existing clusters without changing cluster identity."""
    t0 = time.perf_counter()
    old = {rid: i for i, rid in enumerate(model.ids)}
    keep = [i for i, rid in enumerate(ids) if rid in old and model.hashes[old[rid]] == hashes[i]]
    place = [i for i, rid in enumerate(ids) if not (rid in old and model.hashes[old[rid]] == hashes[i])]
    added = sum(1 for i in place if ids[i] not in old)
    current = set(ids)
    removed = sum(1 for rid in model.ids if rid not in current)

    n, k = len(ids), model.centroids.shape[0]
    labels = np.empty(n, dtype=np.int32)
    xy2 = np.empty((n, model.xy2.shape[1]), dtype=np.float32)
    xyz3 = np.empty((n, model.xyz3.shape[1]), dtype=np.float32)
    from_fit = np.zeros(n, dtype=bool)
    if keep:
        src = np.array([old[ids[i]] for i in keep])
        dst = np.array(keep)
        labels[dst] = model.labels[src]
        xy2[dst] = model.xy2[src]
        xyz3[dst] = model.xyz3[src]
        from_fit[dst] = model.from_fit[src]
    if place:
        if model.reducer2d is None or model.reducer3d is None:
            raise ValueError("model has no saved UMAP reducer; re-run `--mode fit` to save one")
        dst = np.array(place)
        Xp = X[dst]
        labels[dst] = clusterlib.assign_nearest(Xp, model.centroids)
        xy2[dst] = np.asarray(model.reducer2d.transform(Xp), dtype=np.float32)
        xyz3[dst] = np.asarray(model.reducer3d.transform(Xp), dtype=np.float32)

    centroids = model.centroids.copy()  # an emptied cluster keeps its old centroid
    for c in np.unique(labels):
        m = X[labels == c].astype(np.float64).mean(axis=0)
        norm = np.linalg.norm(m)
        if norm > 0:
            centroids[c] = (m / norm).astype(np.float32)
    neighbors = clusterlib.top_neighbors(X, n_neighbors)

    meta = dict(model.meta)
    meta["embeddings_sha256"] = embeddings_sha256
    meta["last_assign_run_id"] = run_id
    out = GalaxyModel(meta, centroids, list(ids), list(hashes), labels, xy2, xyz3, neighbors,
                      model.reducer2d, model.reducer3d, from_fit, model.registry)

    drift = float((~from_fit).sum() / n) if n else 0.0
    recommend = drift > DRIFT_RECOMMEND
    if recommend:
        log.warning("re-cluster recommended: %.1f%% of creators placed by assign since the last fit (> %.0f%%)",
                    100 * drift, 100 * DRIFT_RECOMMEND)
    report = {
        "run_id": run_id,
        "mode": "assign",
        "k": k,
        "creators": n,
        "unchanged": len(keep),
        "added": added,
        "reassigned": len(place) - added,
        "removed": removed,
        "drift_share": drift,
        "recluster_recommended": recommend,
        "empty_clusters": sorted(set(range(k)) - set(np.unique(labels).tolist())),
        "sizes": clusterlib.size_stats(labels, k),
        "seconds": round(time.perf_counter() - t0, 2),
    }
    return out, report


def main(argv: list[str] | None = None) -> int:
    from pipeline.embed import load_embeddings

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["assign", "fit"], default="assign")
    ap.add_argument("--k", type=int, default=None, help="cluster count (default: N_CLUSTERS)")
    ap.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--fresh-names", action="store_true",
                    help="fit mode: name clusters from the seed labels again instead of carrying old names")
    ap.add_argument("--no-save", action="store_true", help="write the model under the run dir only, without the UMAP pickles")
    a = ap.parse_args(argv)
    settings = load_settings()
    k = a.k or settings.n_clusters

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    X, ids, rows = load_embeddings(settings.data_dir / "embeddings")
    live = settings.data_dir / "model" / "galaxy"
    prev = load_model(live) if (live / "model.json").exists() else None
    run_dir = settings.data_dir / "runs" / a.run_id
    if a.mode == "assign":
        if prev is None:
            ap.error(f"no model at {live}; run `--mode fit` first")
        model, report = assign(X, ids, rows["hashes"], prev, rows["embeddings_sha256"], a.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        save_model(model, live)
        report["model_dir"] = str(live)
        (run_dir / "assign_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(json.dumps(report))
        return 0
    model, report = fit(
        X, ids, rows["hashes"], k, prev, rows["model"], rows["embeddings_sha256"], a.run_id
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    from pipeline.snapshot import load_current
    from pipeline.textprep import keyword_text, protected_words

    all_records = load_current(settings.data_dir / "raw")[0]
    records = {r["id"]: r for r in all_records}
    missing = [rid for rid in ids if rid not in records]
    if missing:
        ap.error(f"{len(missing)} embedded ids are not in the current snapshot (e.g. {missing[0]}); run embed first")
    protected = protected_words(all_records)
    texts = [keyword_text(records[rid], protected, rows["max_chars"]) for rid in ids]
    seed_names = _read_json(settings.data_dir / "seed" / "seed_cluster_names.json")
    owner_names = _read_json(settings.data_dir / "cluster_names.json")
    report["naming"] = name_model(model, X, texts, prev, seed_names, owner_names, fresh=a.fresh_names)
    report["unnamed"] = names.write_review(
        run_dir, model.meta["cluster_keys"], model.registry, model.labels, X, model.centroids, ids, records
    )
    target = run_dir / "model" if a.no_save else live
    save_model(model, target, reducers=not a.no_save)
    report["model_dir"] = str(target)
    (run_dir / "fit_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
