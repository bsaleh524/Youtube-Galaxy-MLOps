import importlib.util

import numpy as np
import pytest
from sklearn.decomposition import PCA

from pipeline.cluster import fit
from pipeline.galaxy_model import load_model, save_model

HAS_UMAP = importlib.util.find_spec("umap") is not None


def pca_factory(n_components: int, seed: int):
    """Fast stand-in for UMAP with the same fit_transform/transform interface."""
    return PCA(n_components=n_components, random_state=seed)


def data(n_per=60, k=5, dim=24, spread=0.2, seed=0):
    rng = np.random.default_rng(seed)
    centres = np.eye(dim)[:k]
    X = np.concatenate([c + spread * rng.normal(size=(n_per, dim)) for c in centres])
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    ids = [f"fandom_{i}" for i in range(len(X))]
    hashes = [f"h{i}" for i in range(len(X))]
    return X.astype(np.float32), ids, hashes


def do_fit(X, ids, hashes, prev=None, k=5):
    return fit(X, ids, hashes, k=k, prev=prev, embedding_model="m", embeddings_sha256="sha",
               run_id="r1", reducer_factory=pca_factory)


def test_fit_shapes_and_contents():
    X, ids, hashes = data()
    model, report = do_fit(X, ids, hashes)
    n = len(ids)
    assert model.xy2.shape == (n, 2) and model.xyz3.shape == (n, 3)
    assert np.isfinite(model.xy2).all() and np.isfinite(model.xyz3).all()
    assert model.labels.shape == (n,) and model.centroids.shape == (5, 24)
    assert model.neighbors.shape == (n, 10)
    assert model.ids == ids and model.hashes == hashes
    assert model.meta["k"] == 5 and model.meta["cluster_keys"] == [None] * 5
    assert report["silhouette"] > 0.3 and report["aligned_to_previous"] is False
    assert set(report["seconds"]) >= {"kmeans", "layout2d", "layout3d", "neighbors"}


def test_fit_is_deterministic():
    X, ids, hashes = data()
    a, _ = do_fit(X, ids, hashes)
    b, _ = do_fit(X, ids, hashes)
    assert np.array_equal(a.labels, b.labels)
    assert np.allclose(a.xy2, b.xy2) and np.allclose(a.xyz3, b.xyz3)


def test_save_load_round_trip(tmp_path):
    X, ids, hashes = data()
    model, _ = do_fit(X, ids, hashes)
    save_model(model, tmp_path / "galaxy")
    back = load_model(tmp_path / "galaxy")
    assert back.ids == model.ids and back.hashes == model.hashes and back.meta == model.meta
    for f in ("labels", "centroids", "xy2", "xyz3", "neighbors"):
        assert np.array_equal(getattr(back, f), getattr(model, f))
    assert np.allclose(back.reducer2d.transform(X[:3]), model.reducer2d.transform(X[:3]))


def test_previous_model_kept_on_save(tmp_path):
    X, ids, hashes = data()
    m1, _ = do_fit(X, ids, hashes)
    save_model(m1, tmp_path / "galaxy")
    m2, _ = do_fit(X, ids, hashes, k=4)
    save_model(m2, tmp_path / "galaxy")
    assert load_model(tmp_path / "galaxy").meta["k"] == 4
    assert load_model(tmp_path / "galaxy.prev").meta["k"] == 5


def test_crash_mid_save_leaves_old_model_intact(tmp_path):
    X, ids, hashes = data()
    m1, _ = do_fit(X, ids, hashes)
    save_model(m1, tmp_path / "galaxy")

    class Unpicklable:
        def __reduce__(self):
            raise RuntimeError("boom")

    m2, _ = do_fit(X, ids, hashes, k=4)
    m2.reducer3d = Unpicklable()
    with pytest.raises(RuntimeError, match="boom"):
        save_model(m2, tmp_path / "galaxy")
    assert load_model(tmp_path / "galaxy").meta["k"] == 5
    assert not (tmp_path / "galaxy.tmp").exists()


def test_alignment_to_previous_reduces_movement():
    X, ids, hashes = data()
    rng = np.random.default_rng(5)
    X2 = X + 0.02 * rng.normal(size=X.shape).astype(np.float32)
    X2 /= np.linalg.norm(X2, axis=1, keepdims=True)
    X2 = X2[:, ::-1].copy()  # permuted dims: an unaligned refit lands rotated/flipped
    X1p = X[:, ::-1].copy()
    base, _ = do_fit(X1p, ids, hashes)
    unaligned, _ = do_fit(X2, ids, hashes)
    aligned, report = do_fit(X2, ids, hashes, prev=base)
    assert report["aligned_to_previous"] is True and report["aligned_shared"] == len(ids)
    move = lambda m: np.mean(np.linalg.norm(m.xy2 - base.xy2, axis=1))
    assert move(aligned) <= move(unaligned) + 1e-9
    assert move(aligned) < 0.5 * np.std(base.xy2)


def test_alignment_uses_shared_ids_only():
    X, ids, hashes = data()
    base, _ = do_fit(X, ids, hashes)
    # drop 20 creators and add 10 new ones: alignment fits on the shared ids only
    X2 = np.concatenate([X[20:], data(n_per=2, seed=9)[0]])
    ids2 = ids[20:] + [f"fandom_new{i}" for i in range(10)]
    _, report = do_fit(X2, ids2, hashes[20:] + [f"n{i}" for i in range(10)], prev=base)
    assert report["aligned_shared"] == len(ids) - 20


@pytest.mark.skipif(not HAS_UMAP, reason="umap-learn not installed (ci group)")
def test_real_umap_fit_is_deterministic(tmp_path):
    X, ids, hashes = data(n_per=60)
    kw = {"k": 5, "prev": None, "embedding_model": "m", "embeddings_sha256": "s", "run_id": "r"}
    a, _ = fit(X, ids, hashes, **kw)
    b, _ = fit(X, ids, hashes, **kw)
    assert np.allclose(a.xy2, b.xy2) and np.allclose(a.xyz3, b.xyz3)
    save_model(a, tmp_path / "m")
    back = load_model(tmp_path / "m")
    assert back.reducer2d.transform(X[:5]).shape == (5, 2)


def test_save_without_reducers(tmp_path):
    X, ids, hashes = data()
    model, _ = do_fit(X, ids, hashes)
    save_model(model, tmp_path / "m", reducers=False)
    assert not (tmp_path / "m" / "umap2d.pkl").exists()
    back = load_model(tmp_path / "m")
    assert back.reducer2d is None and back.reducer3d is None
    assert np.array_equal(back.xy2, model.xy2)
