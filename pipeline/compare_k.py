"""Compare cluster counts on the same embeddings, for the owner to pick k at Checkpoint 2.

    uv run python -m pipeline.compare_k [--ks 60,120,200] [--run-id ID]

For each k: KMeans with the fixed seed, silhouette, sizes, a seed-name bootstrap, and 5 example
clusters. The 2D/3D layout is skipped (it doesn't affect clustering and takes ~30 s per k).
Writes data/runs/<run_id>/compare_k.md plus, per k, k<k>/unnamed_clusters.md and naming packs.
Never touches the live model. Same seed and data give identical numbers on a re-run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from pipeline import names
from pipeline.cluster import SEED, fit

EXAMPLES = 5
EXAMPLE_TITLES = 8
JACCARD_BINS = [0, 0.1, 0.2, 0.3, 0.5, 1.0001]


class _NoLayout:
    """Stands in for UMAP: the comparison doesn't need coordinates."""

    def __init__(self, n_components: int, seed: int):
        self.n = n_components

    def fit_transform(self, X):
        return np.zeros((len(X), self.n), dtype=np.float32)


def run_k(X, ids, hashes, k, records, texts, seed_names, run_dir: Path, seed: int = SEED) -> dict:
    model, rep = fit(X, ids, hashes, k, None, "", "", run_dir.name, seed=seed, reducer_factory=_NoLayout)
    keys, registry, nrep = names.name_clusters(model.labels, ids, model.centroids, texts, None, None, None,
                                               seed_names, {})
    _, scores = names.bootstrap_scores(model.labels, ids, seed_names, k=k)
    unnamed = names.write_review(run_dir / f"k{k}", keys, registry, model.labels, X, model.centroids, ids, records)
    sizes = np.bincount(model.labels, minlength=k)
    by_size = np.argsort(-sizes, kind="stable")
    picks = [int(by_size[round(i * (k - 1) / (EXAMPLES - 1))]) for i in range(EXAMPLES)]
    examples = []
    for c in picks:
        members = np.flatnonzero(model.labels == c)
        near = members[np.argsort(-(X[members] @ model.centroids[c]), kind="stable")][:EXAMPLE_TITLES]
        e = registry["clusters"][keys[c]]
        examples.append({"name": e["name"], "source": e["source"], "size": int(sizes[c]),
                         "titles": [records[ids[i]]["title"] for i in near]})
    return {
        "k": k,
        "silhouette": rep["silhouette"],
        "sizes": rep["sizes"],
        "seed_named": nrep["sources"]["seed"],
        "jaccard": sorted(round(v, 4) for v in scores.values()),
        "unnamed": len(unnamed),
        "seconds": round(sum(rep["seconds"].values()), 1),
        "examples": examples,
    }


def format_report(results: list[dict], run_id: str, n: int) -> str:
    def f(v, nd=4):
        return "—" if v is None else f"{v:.{nd}f}"

    lines = [
        f"# Cluster-count comparison ({run_id})",
        "",
        (f"{n} creators, same embeddings and seed for every k. Silhouette: cosine, 10K sample "
        "(higher = tighter, better-separated clusters; text embeddings usually score low)."),
        f"Seed names: one-to-one Jaccard match with the old labelled data, kept if ≥ {names.SEED_THRESHOLD}.",
        "",
        "| k | silhouette | size min / median / max | empty | under 20 | seed-named | unnamed | fit s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        s = r["sizes"]
        lines.append(
            f"| {r['k']} | {f(r['silhouette'])} | {s['min']} / {s['median']:g} / {s['max']} | {s['empty']} | "
            f"{s['under_20']} | {r['seed_named']} | {r['unnamed']} | {r['seconds']:.1f} |"
        )
    lines += ["", "## Seed-name match quality (Jaccard of each cluster's best one-to-one match)", ""]
    labels = ["0–0.1", "0.1–0.2", "0.2–0.3", "0.3–0.5", "0.5–1"]
    lines += ["| k | " + " | ".join(labels) + " | median |", "|---" * (len(labels) + 2) + "|"]
    for r in results:
        counts = np.histogram(r["jaccard"], bins=JACCARD_BINS)[0].tolist() if r["jaccard"] else [0] * len(labels)
        med = float(np.median(r["jaccard"])) if r["jaccard"] else None
        lines.append(f"| {r['k']} | " + " | ".join(map(str, counts)) + f" | {f(med, 3)} |")
    for r in results:
        lines += ["", f"## k = {r['k']}: example clusters (largest to smallest)", ""]
        for e in r["examples"]:
            tag = "" if e["source"] == "seed" else " *(placeholder)*"
            lines.append(f"- **{e['name']}**{tag}, {e['size']} creators: {', '.join(e['titles'])}")
        lines.append(f"\nNaming workload: {r['unnamed']} unnamed clusters, packs in `k{r['k']}/naming_packs/`.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from pipeline.config import load_settings
    from pipeline.embed import load_embeddings
    from pipeline.snapshot import load_current
    from pipeline.textprep import embed_text

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ks", default="60,120,200")
    ap.add_argument("--run-id", default="compare-k-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    a = ap.parse_args(argv)
    settings = load_settings()
    ks = [int(x) for x in a.ks.split(",")]

    X, ids, rows = load_embeddings(settings.data_dir / "embeddings")
    records = {r["id"]: r for r in load_current(settings.data_dir / "raw")[0]}
    texts = [embed_text(records[rid], rows["max_chars"])[0] for rid in ids]
    seed_file = settings.data_dir / "seed" / "seed_cluster_names.json"
    seed_names = json.loads(seed_file.read_text(encoding="utf-8")) if seed_file.exists() else {}
    run_dir = settings.data_dir / "runs" / a.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for k in ks:
        r = run_k(X, ids, rows["hashes"], k, records, texts, seed_names, run_dir)
        print(f"k={k}: silhouette {r['silhouette']:.4f}, {r['seed_named']} seed-named, {r['seconds']} s",
              file=sys.stderr)
        results.append(r)
    (run_dir / "compare_k.md").write_text(format_report(results, a.run_id, len(ids)), encoding="utf-8")
    (run_dir / "compare_k.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "ks": ks,
                      "silhouette": {r["k"]: r["silhouette"] for r in results}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
