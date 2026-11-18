"""The persisted galaxy cluster model: what fit mode produces and assign mode reuses.

    data/model/galaxy/
        model.json      k, seed, fit_run_id, embedding_model, embeddings_sha256, silhouette,
                        cluster_keys (index = KMeans label; filled by the naming step), umap params
        centroids.npy   (k, dim) float32, unit length
        layout.npz      ids, hashes, labels, xy2, xyz3, neighbors (rows index into ids)
        umap2d.pkl      fitted 2D reducer (has .transform); absent if saved with reducers=False
        umap3d.pkl      fitted 3D reducer
    data/model/galaxy.prev/   the model before the last save (for alignment and name carry-over)

Saving writes a sibling .tmp dir and swaps it in, so a crash never leaves half a model.
Pickles are only ever read from this local directory, which this pipeline wrote itself.
"""

from __future__ import annotations

import json
import os
import pickle
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class GalaxyModel:
    meta: dict
    centroids: np.ndarray
    ids: list[str]
    hashes: list[str]
    labels: np.ndarray
    xy2: np.ndarray
    xyz3: np.ndarray
    neighbors: np.ndarray
    reducer2d: Any
    reducer3d: Any


def save_model(model: GalaxyModel, path: Path, reducers: bool = True) -> None:
    """Save atomically. reducers=False skips the ~240 MB UMAP pickles (comparison runs); such a
    model can't place new creators (assign mode) but has everything else."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    prev = path.with_name(path.name + ".prev")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        (tmp / "model.json").write_text(json.dumps(model.meta, indent=1), encoding="utf-8")
        np.save(tmp / "centroids.npy", model.centroids)
        np.savez(
            tmp / "layout.npz",
            ids=np.array(model.ids),
            hashes=np.array(model.hashes),
            labels=model.labels,
            xy2=model.xy2,
            xyz3=model.xyz3,
            neighbors=model.neighbors,
        )
        pickled = (("umap2d.pkl", model.reducer2d), ("umap3d.pkl", model.reducer3d)) if reducers else ()
        for name, reducer in pickled:
            with open(tmp / name, "wb") as f:
                pickle.dump(reducer, f, protocol=pickle.HIGHEST_PROTOCOL)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if path.exists():
        if prev.exists():
            shutil.rmtree(prev)
        os.rename(path, prev)
    os.rename(tmp, path)


def load_model(path: Path) -> GalaxyModel:
    path = Path(path)
    meta = json.loads((path / "model.json").read_text(encoding="utf-8"))
    lay = np.load(path / "layout.npz")
    reducers = []
    for name in ("umap2d.pkl", "umap3d.pkl"):
        if not (path / name).exists():  # saved with reducers=False
            reducers.append(None)
            continue
        with open(path / name, "rb") as f:
            reducers.append(pickle.load(f))
    return GalaxyModel(
        meta=meta,
        centroids=np.load(path / "centroids.npy"),
        ids=lay["ids"].tolist(),
        hashes=lay["hashes"].tolist(),
        labels=lay["labels"],
        xy2=lay["xy2"],
        xyz3=lay["xyz3"],
        neighbors=lay["neighbors"],
        reducer2d=reducers[0],
        reducer3d=reducers[1],
    )
