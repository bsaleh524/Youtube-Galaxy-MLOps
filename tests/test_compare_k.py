import numpy as np

from pipeline.compare_k import format_report, run_k


def fake(k, sil, jacc):
    return {
        "k": k, "silhouette": sil,
        "sizes": {"min": 3, "median": 10.0, "max": 40, "empty": 0, "under_20": 2},
        "seed_named": 2, "jaccard": jacc, "unnamed": k - 2, "seconds": 1.25,
        "examples": [{"name": "Gaming", "source": "seed", "size": 40, "titles": ["A", "B"]},
                     {"name": "x · y · z", "source": "placeholder", "size": 3, "titles": ["C"]}],
    }


def test_report_has_one_row_per_k_and_all_sections():
    md = format_report([fake(4, 0.0123, [0.05, 0.25, 0.6, 0.15]), fake(8, None, [])], "run1", 100)
    assert "# Cluster-count comparison (run1)" in md and "100 creators" in md
    assert "| 4 | 0.0123 | 3 / 10 / 40 | 0 | 2 | 2 | 2 | 1.2 |" in md
    assert "| 8 | — |" in md
    assert "| 4 | 1 | 1 | 1 | 0 | 1 | 0.200 |" in md
    assert "| 8 | 0 | 0 | 0 | 0 | 0 | — |" in md
    assert "## k = 4: example clusters" in md and "## k = 8: example clusters" in md
    assert "- **Gaming**, 40 creators: A, B" in md
    assert "- **x · y · z** *(placeholder)*, 3 creators: C" in md
    assert "Naming workload: 6 unnamed clusters, packs in `k8/naming_packs/`." in md


def test_run_k_is_deterministic_and_writes_packs(tmp_path):
    rng = np.random.default_rng(0)
    centres = np.eye(16)[:4]
    X = np.concatenate([c + 0.1 * rng.normal(size=(30, 16)) for c in centres]).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    ids = [f"fandom_{i}" for i in range(120)]
    topics = ["minecraft server", "makeup beauty", "cooking recipes", "music songs"]
    texts = [f"{topics[i // 30]} words" for i in range(120)]
    records = {rid: {"title": f"T{i}", "description": texts[i]} for i, rid in enumerate(ids)}
    seed = {rid: "Minecraft" for rid in ids[:30]}
    a = run_k(X, ids, ["h"] * 120, 4, records, texts, seed, tmp_path / "a")
    b = run_k(X, ids, ["h"] * 120, 4, records, texts, seed, tmp_path / "b")
    a.pop("seconds"), b.pop("seconds")
    assert a == b
    assert a["seed_named"] == 1 and a["unnamed"] == 3 and len(a["examples"]) == 5
    assert (tmp_path / "a" / "k4" / "unnamed_clusters.md").exists()
    assert len(list((tmp_path / "a" / "k4" / "naming_packs").glob("*.md"))) == 3
