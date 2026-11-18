import logging

import numpy as np
import pytest

from pipeline import clusterlib
from pipeline.cluster import DRIFT_RECOMMEND, assign
from pipeline.galaxy_model import GalaxyModel, load_model, save_model

DIM = 8
K = 3


class FirstDims:
    """Identity-style 'transform': the first n coordinates of each vector."""

    def __init__(self, n):
        self.n = n

    def transform(self, X):
        return np.asarray(X, dtype=np.float32)[:, : self.n] * 10


def unit(M):
    M = np.asarray(M, dtype=np.float32)
    return M / np.linalg.norm(M, axis=1, keepdims=True)


def vec(axis, jitter=0.0):
    v = np.zeros(DIM, dtype=np.float32)
    v[axis] = 1.0
    v[(axis + 4) % DIM] = jitter
    return v


def base_model():
    """9 creators, 3 per cluster along axes 0, 1, 2. Coordinates are distinct made-up values."""
    X = unit([vec(c, j) for c in range(K) for j in (0.0, 0.1, 0.2)])
    ids = [f"fandom_{i}" for i in range(9)]
    hashes = [f"h{i}" for i in range(9)]
    labels = np.repeat(np.arange(K, dtype=np.int32), 3)
    rng = np.random.default_rng(1)
    meta = {"k": K, "seed": 42, "fit_run_id": "fit1", "cluster_keys": ["c001", "c002", "c003"],
            "embedding_model": "m", "embeddings_sha256": "old", "silhouette": 0.5}
    model = GalaxyModel(
        meta=meta, centroids=unit(np.eye(DIM)[:K]), ids=ids, hashes=hashes, labels=labels,
        xy2=rng.normal(size=(9, 2)).astype(np.float32), xyz3=rng.normal(size=(9, 3)).astype(np.float32),
        neighbors=clusterlib.top_neighbors(X, 5), reducer2d=FirstDims(2), reducer3d=FirstDims(3),
    )
    return model, X, ids, hashes


def run(model, X, ids, hashes):
    return assign(X, ids, hashes, model, embeddings_sha256="new", run_id="a1", n_neighbors=5)


def rows(model):
    pos = {rid: i for i, rid in enumerate(model.ids)}
    return {rid: (int(model.labels[i]), model.xy2[i].tobytes(), model.xyz3[i].tobytes()) for rid, i in pos.items()}


def test_unchanged_creators_are_byte_identical():
    model, X, ids, hashes = base_model()
    before = rows(model)
    new_X = np.vstack([X, unit([vec(1, 0.05)])])
    out, _ = run(model, new_X, ids + ["fandom_100"], hashes + ["h100"])
    after = rows(out)
    for rid in ids:
        assert after[rid] == before[rid]


def test_new_creator_lands_in_nearest_cluster_with_transformed_coords():
    model, X, ids, hashes = base_model()
    v = unit([vec(2, 0.3)])
    out, report = run(model, np.vstack([X, v]), ids + ["fandom_100"], hashes + ["h100"])
    i = out.ids.index("fandom_100")
    assert out.labels[i] == 2
    assert np.allclose(out.xy2[i], v[0, :2] * 10) and np.allclose(out.xyz3[i], v[0, :3] * 10)
    assert report["added"] == 1 and report["reassigned"] == 0 and report["removed"] == 0


def test_changed_text_is_reassigned():
    model, X, ids, hashes = base_model()
    X2 = X.copy()
    X2[0] = unit([vec(1)])[0]  # creator 0 moved from cluster 0 to cluster 1's direction
    hashes2 = ["changed"] + hashes[1:]
    out, report = run(model, X2, ids, hashes2)
    assert out.labels[out.ids.index("fandom_0")] == 1
    assert out.hashes[out.ids.index("fandom_0")] == "changed"
    assert report["reassigned"] == 1 and report["added"] == 0


def test_removed_creator_is_gone_everywhere():
    model, X, ids, hashes = base_model()
    keep = [i for i in range(9) if i != 4]
    out, report = run(model, X[keep], [ids[i] for i in keep], [hashes[i] for i in keep])
    assert "fandom_4" not in out.ids and len(out.ids) == 8
    assert out.xy2.shape == (8, 2) and out.neighbors.shape == (8, 5)
    assert out.neighbors.max() < 8
    assert report["removed"] == 1


def test_neighbours_recomputed_over_all_vectors():
    model, X, ids, hashes = base_model()
    v = unit([vec(0, 0.05)])
    new_X = np.vstack([X, v])
    out, _ = run(model, new_X, ids + ["fandom_100"], hashes + ["h100"])
    assert np.array_equal(out.neighbors, clusterlib.top_neighbors(new_X, 5))


def test_keys_and_meta_identity_unchanged():
    model, X, ids, hashes = base_model()
    keys = list(model.meta["cluster_keys"])
    out, _ = run(model, np.vstack([X, unit([vec(1)])]), ids + ["fandom_100"], hashes + ["h100"])
    assert out.meta["cluster_keys"] == keys
    assert out.meta["k"] == K and out.meta["fit_run_id"] == "fit1"
    assert out.meta["embeddings_sha256"] == "new" and out.meta["last_assign_run_id"] == "a1"


def test_centroids_are_unit_mean_of_current_members():
    model, X, ids, hashes = base_model()
    v = unit([vec(1, 0.5)])
    new_X = np.vstack([X, v])
    out, _ = run(model, new_X, ids + ["fandom_100"], hashes + ["h100"])
    members = new_X[out.labels == 1]
    expected = members.mean(axis=0) / np.linalg.norm(members.mean(axis=0))
    assert np.allclose(out.centroids[1], expected, atol=1e-6)
    assert np.allclose(np.linalg.norm(out.centroids, axis=1), 1, atol=1e-6)


def test_emptied_cluster_keeps_key_and_centroid_and_has_no_leader():
    model, X, ids, hashes = base_model()
    keep = [i for i in range(9) if model.labels[i] != 2]
    out, report = run(model, X[keep], [ids[i] for i in keep], [hashes[i] for i in keep])
    assert out.meta["cluster_keys"][2] == "c003"
    assert np.array_equal(out.centroids[2], model.centroids[2])
    assert 2 not in clusterlib.leaders(X[keep], out.labels, out.centroids)
    assert report["empty_clusters"] == [2]


def test_drift_share_is_cumulative_since_fit(caplog):
    model, X, ids, hashes = base_model()
    new_X = np.vstack([X, unit([vec(0, 0.3)])])
    out, report = run(model, new_X, ids + ["fandom_100"], hashes + ["h100"])
    assert report["drift_share"] == pytest.approx(1 / 10)
    # second run: change one more text; the first newcomer still counts
    hashes2 = ["changed"] + hashes[1:] + ["h100"]
    with caplog.at_level(logging.WARNING, logger="pipeline.cluster"):
        _, report2 = run(out, new_X, ids + ["fandom_100"], hashes2)
    assert report2["drift_share"] == pytest.approx(2 / 10)
    assert report2["recluster_recommended"] is (2 / 10 > DRIFT_RECOMMEND)
    assert ("re-cluster recommended" in caplog.text) is report2["recluster_recommended"]


def test_drift_above_threshold_warns_but_succeeds(caplog):
    model, X, ids, hashes = base_model()
    extra = unit([vec(c % K, 0.05 * c) for c in range(5)])
    with caplog.at_level(logging.WARNING, logger="pipeline.cluster"):
        _, report = run(model, np.vstack([X, extra]), ids + [f"fandom_{100 + i}" for i in range(5)],
                        hashes + [f"n{i}" for i in range(5)])
    assert report["drift_share"] == pytest.approx(5 / 14)
    assert report["recluster_recommended"] is True
    assert "re-cluster recommended" in caplog.text


def test_assign_without_reducers_fails_clearly():
    model, X, ids, hashes = base_model()
    model.reducer2d = None
    with pytest.raises(ValueError, match="reducer"):
        run(model, np.vstack([X, unit([vec(0)])]), ids + ["fandom_100"], hashes + ["h100"])


def test_assign_with_nothing_new_needs_no_reducers():
    model, X, ids, hashes = base_model()
    model.reducer2d = model.reducer3d = None
    out, report = run(model, X, ids, hashes)
    assert rows(out) == rows(model) and report["drift_share"] == 0


def test_fit_origin_round_trips(tmp_path):
    model, X, ids, hashes = base_model()
    out, _ = run(model, np.vstack([X, unit([vec(0)])]), ids + ["fandom_100"], hashes + ["h100"])
    assert out.from_fit.tolist() == [True] * 9 + [False]
    save_model(out, tmp_path / "g", reducers=False)
    back = load_model(tmp_path / "g")
    assert back.from_fit.tolist() == out.from_fit.tolist()
