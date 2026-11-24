import numpy as np

from pipeline import names


def ids_for(n):
    return [f"fandom_{i}" for i in range(n)]


# ---- bootstrap from seed -------------------------------------------------------------------


def test_bootstrap_matches_by_overlap():
    labels = np.array([0, 0, 0, 1, 1, 1])
    ids = ids_for(6)
    seed = {"fandom_0": "Gaming", "fandom_1": "Gaming", "fandom_2": "Gaming",
            "fandom_3": "Beauty", "fandom_4": "Beauty", "fandom_5": "Beauty"}
    assert names.bootstrap_from_seed(labels, ids, seed) == {0: "Gaming", 1: "Beauty"}


def test_bootstrap_uses_each_name_once_even_when_two_clusters_prefer_it():
    # clusters 0 and 1 both overlap "Gaming" most; only one may take it
    labels = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    ids = ids_for(8)
    seed = {f"fandom_{i}": "Gaming" for i in range(7)}
    seed["fandom_7"] = "Music"
    out = names.bootstrap_from_seed(labels, ids, seed, threshold=0.0)
    assert sorted(v for v in out.values() if v) == ["Gaming", "Music"]
    assert out[0] == "Gaming"  # 4/7 overlap beats cluster 1's 3/8


def test_bootstrap_below_threshold_is_none():
    labels = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    ids = ids_for(10)
    seed = {"fandom_0": "Rare"}  # Jaccard 1/10
    assert names.bootstrap_from_seed(labels, ids, seed, threshold=0.2) == {0: None}
    _, scores = names.bootstrap_scores(labels, ids, seed, threshold=0.2)
    assert scores == {0: 0.1}


def test_bootstrap_more_clusters_than_names_leaves_rest_unnamed():
    labels = np.array([0, 0, 1, 1, 2, 2])
    seed = {"fandom_0": "A", "fandom_1": "A", "fandom_2": "B", "fandom_3": "B"}
    assert names.bootstrap_from_seed(labels, ids_for(6), seed) == {0: "A", 1: "B", 2: None}


# ---- carry-over and keys -------------------------------------------------------------------


def test_carry_over_maps_permuted_centroids_back_to_keys():
    rng = np.random.default_rng(0)
    prev = rng.normal(size=(6, 16))
    prev /= np.linalg.norm(prev, axis=1, keepdims=True)
    keys = [f"c{i:03d}" for i in range(1, 7)]
    perm = np.array([3, 0, 5, 1, 4, 2])
    out = names.carry_over(prev[perm], prev, keys)
    assert out == {i: keys[perm[i]] for i in range(6)}


def test_carry_over_below_min_cos_is_new():
    prev = np.eye(4)[:2]
    new = np.array([np.eye(4)[0], np.eye(4)[3]])  # second is orthogonal to everything old
    assert names.carry_over(new, prev, ["c001", "c002"]) == {0: "c001", 1: None}


def test_new_keys_never_collide_with_old_or_retired():
    # registry has issued c001..c005; c002 and c004 are retired. next_key is 6.
    keys, nxt = names.assign_keys({0: "c001", 1: None, 2: "c003", 3: None}, 4, next_key=6)
    assert keys == ["c001", "c006", "c003", "c007"] and nxt == 8


# ---- keywords and naming -------------------------------------------------------------------


def corpus():
    labels = np.array([0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3])
    texts = (
        ["Minecraft survival server youtube channel"] * 3
        + ["Makeup beauty tutorials youtube channel"] * 3
        + ["Roblox obby tycoon youtube channel"] * 3
        + ["Cooking recipes kitchen youtube channel"] * 3
    )
    return labels, texts


def test_keywords_skip_words_shared_by_most_clusters():
    labels, texts = corpus()
    kw = names.cluster_keywords(labels, 4, texts)
    assert set(kw[2][:3]) == {"roblox", "obby", "tycoon"}
    assert all("youtube" not in v and "channel" not in v for v in kw.values())


def unit_centroids(k, dim=8):
    return np.eye(dim)[:k].astype(np.float32)


def test_first_fit_seed_names_owner_override_and_placeholder():
    labels, texts = corpus()
    ids = ids_for(12)
    seed = {f"fandom_{i}": "Minecraft & SMPs" for i in range(3)}
    seed.update({f"fandom_{i}": "Beauty" for i in range(3, 6)})
    owner = {"c002": "Makeup Gurus"}  # owner names the cluster the seed called "Beauty"
    keys, reg, report = names.name_clusters(labels, ids, unit_centroids(4), texts, None, None, None, seed, owner)
    assert keys == ["c001", "c002", "c003", "c004"] and reg["next_key"] == 5
    c = reg["clusters"]
    assert c["c001"]["name"] == "Minecraft & SMPs" and c["c001"]["source"] == "seed"
    assert c["c002"]["name"] == "Makeup Gurus" and c["c002"]["source"] == "owner"
    assert c["c003"]["source"] == "placeholder" and set(c["c003"]["name"].split(names.SEP)) == {"roblox", "obby", "tycoon"}
    assert len({e["colour"] for e in c.values()}) == 4
    assert report["method"] == "seed" and report["sources"] == {"owner": 1, "seed": 1, "carried": 0, "placeholder": 2}


def test_refit_carries_names_and_colours_and_retires_unmatched():
    labels, texts = corpus()
    ids = ids_for(12)
    seed = {f"fandom_{i}": "Minecraft & SMPs" for i in range(3)}
    keys1, reg1, _ = names.name_clusters(labels, ids, unit_centroids(4), texts, None, None, None, seed, {})
    # refit: clusters come out in a different order, and old cluster 3 is replaced by a new one
    new_cent = unit_centroids(8)[[2, 0, 1, 5]]
    new_labels = np.array([1, 1, 1, 2, 2, 2, 0, 0, 0, 3, 3, 3])
    keys2, reg2, report = names.name_clusters(new_labels, ids, new_cent, texts, reg1, unit_centroids(4), keys1, seed, {})
    assert keys2[:3] == ["c003", "c001", "c002"] and keys2[3] == "c005"
    c = reg2["clusters"]
    for key in ("c001", "c002", "c003"):
        assert c[key]["colour"] == reg1["clusters"][key]["colour"]
    assert c["c001"]["name"] == "Minecraft & SMPs" and c["c001"]["source"] == "carried"
    assert c["c004"]["active"] is False and c["c004"]["colour"] == reg1["clusters"]["c004"]["colour"]
    assert c["c005"]["colour"] not in {e["colour"] for e in reg1["clusters"].values()}
    assert report["method"] == "carried" and report["retired"] == ["c004"] and reg2["next_key"] == 6


def test_write_review_lists_placeholders_with_packs(tmp_path):
    labels, texts = corpus()
    ids = ids_for(12)
    records = {rid: {"title": f"Creator {i}", "description": texts[i] + ". More text."} for i, rid in enumerate(ids)}
    X = np.repeat(unit_centroids(4), 3, axis=0)
    keys, reg, _ = names.name_clusters(labels, ids, unit_centroids(4), texts, None, None, None, {}, {})
    out = names.write_review(tmp_path, keys, reg, labels, X, unit_centroids(4), ids, records)
    assert out == keys
    md = (tmp_path / "unnamed_clusters.md").read_text()
    assert "| c003 | 3 |" in md
    pack = (tmp_path / "naming_packs" / "c003.md").read_text()
    assert "Creator 6" in pack and "Reply with the name only." in pack and "roblox" in pack
