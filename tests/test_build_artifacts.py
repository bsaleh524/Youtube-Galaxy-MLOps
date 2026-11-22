import json
from pathlib import Path

import numpy as np
import pytest

from pipeline import clusterlib
from pipeline.build_artifacts import BIO_CHARS, SNIPPET_CHARS, build, cut, make_version, size_report
from pipeline.galaxy_model import GalaxyModel
from pipeline.index_format import read_centroids, read_index, read_meta_record
from pipeline.search import two_stage_search

FIXTURE = Path(__file__).parent / "fixtures" / "creators_small.json"
K, DIM = 3, 16


@pytest.fixture
def built(tmp_path):
    recs = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # make one bio very long, with multi-byte characters near both caps
    recs[2]["description"] = ("ねくろ " * 300) + "🎮" * 50
    records = {r["id"]: r for r in recs}
    ids = [r["id"] for r in recs]
    rng = np.random.default_rng(0)
    X = rng.normal(size=(len(ids), DIM)).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    labels = np.array([i % K for i in range(len(ids))], dtype=np.int32)  # interleaved, not sorted
    centroids = np.stack([X[labels == c].mean(axis=0) for c in range(K)])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    keys = ["c001", "c002", "c004"]
    registry = {"next_key": 5, "clusters": {
        "c001": {"name": "Gaming", "colour": "#ff0000", "source": "seed", "active": True},
        "c002": {"name": "a · b · c", "colour": "#00ff00", "source": "placeholder", "active": True},
        "c003": {"name": "Old", "colour": "#0000ff", "source": "seed", "active": False},
        "c004": {"name": "Music", "colour": "#ffff00", "source": "seed", "active": True},
    }}
    model = GalaxyModel(
        meta={"cluster_keys": keys, "embedding_model": "fake", "silhouette": 0.1},
        centroids=centroids.astype(np.float32), ids=ids, hashes=["h"] * len(ids), labels=labels,
        xy2=rng.normal(size=(len(ids), 2)).astype(np.float32),
        xyz3=rng.normal(size=(len(ids), 3)).astype(np.float32),
        neighbors=clusterlib.top_neighbors(X, 5), reducer2d=None, reducer3d=None, registry=registry,
    )
    out = build(records, X, model, {"c002": "Owner Named"}, tmp_path, "20261118-000000-abcdef12")
    return out, records, X, model


def load(out, name):
    return json.loads((out / name).read_text(encoding="utf-8"))


def test_every_id_once_in_nodes_with_valid_cluster(built):
    out, records, _, _ = built
    nodes = load(out, "nodes.json")
    assert sorted(nodes["id"]) == sorted(records) and len(set(nodes["id"])) == len(records)
    assert {len(v) for v in nodes.values()} == {len(records)}
    clusters = load(out, "clusters.json")
    assert all(0 <= c < len(clusters) for c in nodes["cluster"])
    assert all(v == round(v, 3) for v in nodes["x2"])


def test_same_title_pair_both_present_as_distinct_ids(built):
    out, records, _, _model = built
    nodes = load(out, "nodes.json")
    titles = dict(zip(nodes["id"], nodes["title"], strict=True))
    assert titles["fandom_449281"] == "TARGET" and titles["fandom_372805"] == "Target"
    meta = (out / "worker" / "meta.bin").read_bytes()
    meta_ids = [read_meta_record(meta, r)["id"] for r in range(len(records))]
    assert "fandom_449281" in meta_ids and "fandom_372805" in meta_ids


def test_neighbors_are_known_ids(built):
    out, records, _, _ = built
    nb = load(out, "neighbors.json")
    assert set(nb) == set(records)
    assert all(v in records and v != rid for rid, vs in nb.items() for v in vs)


def test_clusters_use_owner_names_leaders_and_ids(built):
    out, _, _, _model = built
    clusters = load(out, "clusters.json")
    assert [c["key"] for c in clusters] == ["c001", "c002", "c004"]
    assert [c["name"] for c in clusters] == ["Gaming", "Owner Named", "Music"]
    assert sum(c["size"] for c in clusters) == 12
    nodes = load(out, "nodes.json")
    cl_of = dict(zip(nodes["id"], nodes["cluster"], strict=True))
    for pos, c in enumerate(clusters):
        assert cl_of[c["leader_id"]] == pos


def test_index_rows_match_cluster_offsets_and_meta(built):
    out, records, X, model = built
    idx = read_index(out / "worker" / "index.bin")
    meta = (out / "worker" / "meta.bin").read_bytes()
    clusters = load(out, "clusters.json")
    assert idx.offsets.tolist() == [0, 4, 8, 12]
    pos = {rid: i for i, rid in enumerate(model.ids)}
    for c in range(K):
        for r in range(idx.offsets[c], idx.offsets[c + 1]):
            rec = read_meta_record(meta, r)
            assert model.labels[pos[rec["id"]]] == c
            assert rec["cluster"] == clusters[c]["name"]
            assert rec["url"] == records[rec["id"]]["url"]
            # row r's vector is that id's vector
            approx = idx.q[r].astype(np.float32) * idx.scales[r] / 127
            assert np.allclose(approx, X[pos[rec["id"]]], atol=0.02)
    man = load(out, "worker/index_manifest.json")
    assert man == {"version": "20261118-000000-abcdef12", "n": 12, "dim": DIM, "k": K, "model": "fake"}
    assert read_centroids(out / "worker" / "centroids.bin").shape == (K, DIM)


def test_exact_copy_query_is_top1(built):
    out, _, X, model = built
    idx = read_index(out / "worker" / "index.bin")
    cents = read_centroids(out / "worker" / "centroids.bin")
    meta = (out / "worker" / "meta.bin").read_bytes()
    for i, rid in enumerate(model.ids):
        hits = two_stage_search(X[i], cents, idx, k=1, probe_min=1, min_candidates=1, max_probe=K)
        assert read_meta_record(meta, hits[0][0])["id"] == rid


def test_bio_caps_and_details(built):
    out, records, _, _ = built
    clusters = load(out, "clusters.json")
    seen = {}
    for c in clusters:
        seen.update(load(out, f"details/cluster_{c['key']}.json"))
    assert set(seen) == set(records)
    long_bio = seen["fandom_500338"]["bio"]
    assert len(long_bio) <= BIO_CHARS and long_bio.endswith("…")
    long_bio.encode("utf-8")  # whole characters only
    assert all(d["source_url"] for d in seen.values())
    assert seen["fandom_106"]["youtube_url"] is None
    meta = (out / "worker" / "meta.bin").read_bytes()
    snippets = [read_meta_record(meta, r)["snippet"] for r in range(12)]
    assert max(len(s) for s in snippets) <= SNIPPET_CHARS


def test_cut_word_boundary_and_short_text():
    assert cut("short  text\n here", 50) == "short text here"
    s = cut("alpha beta gamma delta epsilon", 14)
    assert s == "alpha beta…" and len(s) <= 14
    assert cut(None, 10) == ""
    assert len(cut("x" * 100, 10)) == 10


def test_manifest_sizes_match_disk(built):
    out, *_ = built
    man = load(out, "manifest.json")
    assert man["files"] and "manifest.json" not in man["files"]
    for rel, size in man["files"].items():
        assert (out / rel).stat().st_size == size
    assert man["creators"] == 12 and man["clusters"] == 3
    assert man["attribution"]["license"] == "CC BY-SA"
    rep = size_report(out)
    assert rep["worker"][0] == sum(s for r, s in man["files"].items() if r.startswith("worker/"))


def test_version_format_and_no_overwrite(built, tmp_path):
    out, records, X, model = built
    from datetime import UTC, datetime

    assert make_version("abcdef1234", datetime(2026, 11, 18, 1, 2, 3, tzinfo=UTC)) == "20261118-010203-abcdef12"
    with pytest.raises(FileExistsError):
        build(records, X, model, {}, out.parent, out.name)


def test_details_pass_through_missing_flag(tmp_path, built):
    _, records, X, model = built
    records = {k: dict(v) for k, v in records.items()}
    flagged = model.ids[1]
    records[flagged]["missing_from_wiki_since"] = "2026-12-01"
    out2 = build(records, X, model, {}, tmp_path / "again", "20261118-000001-abcdef12")
    details = {}
    for f in (out2 / "details").glob("*.json"):
        details.update(json.loads(f.read_text(encoding="utf-8")))
    assert details[flagged]["missing_from_wiki_since"] == "2026-12-01"
    assert all("missing_from_wiki_since" not in d for rid, d in details.items() if rid != flagged)


def test_attribution_has_license_url(built):
    att = load(built[0], "manifest.json")["attribution"]
    # as reported by the wiki itself (MediaWiki siteinfo rightsinfo, checked 2026-11-22)
    assert att["license"] == "CC BY-SA"
    assert att["license_url"] == "https://www.fandom.com/licensing"
