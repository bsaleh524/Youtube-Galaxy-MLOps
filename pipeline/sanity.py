"""Score an embeddings folder for issue #5 (names dominating the vectors).

    uv run python -m pipeline.sanity [--embeddings DIR] [--out FILE.md] [--k 120]

Reports, for any embeddings folder (live data/embeddings or an experiment):
- the Checkpoint 2 sanity creators and their 10 nearest neighbours (judged by eye: ✓ ◐ ✗);
- the name-lookalike rate: the share of all (creator, neighbour) pairs whose titles share a
  3-letter word start (MKBHD -> Brownie, Kurzgesagt -> KuruHS), next to the same rate for random
  pairs, which is what pure chance gives;
- silhouette of a fresh k-means fit (k=120 by default), comparable with Checkpoint 2's 0.012.
The last stdout line is a JSON summary.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np

from pipeline import clusterlib

# The Checkpoint 2 checks, in its order (Target and TARGET are the same-title pair).
SANITY_IDS = [
    "fandom_225303",  # Dream
    "fandom_143804",  # Ninja
    "fandom_135613",  # James Charles
    "fandom_125499",  # Dude Perfect
    "fandom_102432",  # CoryxKenshin
    "fandom_372805",  # Target
    "fandom_449281",  # TARGET
    "fandom_20660",  # Markiplier
    "fandom_179221",  # Linus Tech Tips
    "fandom_137746",  # Technoblade
    "fandom_1754",  # Smosh
    "fandom_111268",  # MrBeast
    "fandom_131817",  # PewDiePie
    "fandom_34528",  # Marques Brownlee
    "fandom_15700",  # Vsauce
    "fandom_120119",  # Kurzgesagt – In a Nutshell
]
N_NEIGHBOURS = 10


def fold_words(title: str) -> list[str]:
    """Lowercase, accent-free alphanumeric words of 3+ characters."""
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    words = "".join(c if c.isalnum() else " " for c in s).split()
    return [w for w in words if len(w) >= 3]


def _starts(title: str) -> set[str]:
    return {w[:3] for w in fold_words(title)}


def lookalike(a: str, b: str) -> bool:
    """True when some word of each title starts with the same 3 letters."""
    return bool(_starts(a) & _starts(b))


def lookalike_rate(titles: list[str], nbrs: np.ndarray) -> float:
    starts = [_starts(t) for t in titles]
    hits = sum(bool(starts[i] & starts[j]) for i, row in enumerate(nbrs) for j in row)
    return hits / nbrs.size


def chance_rate(titles: list[str], n_pairs: int = 200_000, seed: int = 42) -> float:
    """The lookalike rate for random distinct pairs: what you'd get with no name effect at all."""
    rng = np.random.default_rng(seed)
    starts = [_starts(t) for t in titles]
    a = rng.integers(0, len(titles), n_pairs)
    b = (a + rng.integers(1, len(titles), n_pairs)) % len(titles)
    return sum(bool(starts[i] & starts[j]) for i, j in zip(a, b, strict=True)) / n_pairs


def score(X: np.ndarray, ids: list[str], titles: list[str], k: int = 120) -> dict:
    nbrs = clusterlib.top_neighbors(X, N_NEIGHBOURS)
    labels, _ = clusterlib.fit_kmeans(X, k)
    row = {rid: i for i, rid in enumerate(ids)}
    checks = {
        rid: {"title": titles[row[rid]], "neighbours": [titles[j] for j in nbrs[row[rid]]]}
        for rid in SANITY_IDS
        if rid in row
    }
    return {
        "lookalike_rate": round(lookalike_rate(titles, nbrs), 4),
        "chance_rate": round(chance_rate(titles), 4),
        "silhouette": round(s, 4) if (s := clusterlib.silhouette_cosine(X, labels)) is not None else None,
        "k": k,
        "checks": checks,
    }


def format_report(result: dict, label: str) -> str:
    lines = [
        f"# Embedding sanity: {label}",
        "",
        (
            f"- Name-lookalike rate: **{result['lookalike_rate']:.2%}** of neighbour pairs "
            f"(random pairs: {result['chance_rate']:.2%})"
        ),
        f"- Silhouette (k={result['k']}): **{result['silhouette']}**",
        "",
        "| Creator | 10 nearest neighbours | Verdict |",
        "|---|---|---|",
    ]
    for c in result["checks"].values():
        lines.append(f"| {c['title']} | {' · '.join(c['neighbours'])} |  |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from pipeline.config import load_settings
    from pipeline.embed import load_embeddings
    from pipeline.snapshot import load_current

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--embeddings", type=Path, default=None, help="default: data/embeddings")
    ap.add_argument("--out", type=Path, default=None, help="markdown report path")
    ap.add_argument("--k", type=int, default=120)
    a = ap.parse_args(argv)
    settings = load_settings()
    emb = a.embeddings or settings.data_dir / "embeddings"
    X, ids, rows = load_embeddings(emb)
    by_id = {r["id"]: r["title"] for r in load_current(settings.data_dir / "raw")[0]}
    missing = [rid for rid in ids if rid not in by_id]
    if missing:
        ap.error(f"{len(missing)} embedded ids are not in the current snapshot (e.g. {missing[0]})")
    result = score(X, ids, [by_id[rid] for rid in ids], a.k)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(format_report(result, str(emb)), encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "checks"}
    print(json.dumps({**summary, "embeddings": str(emb), "text_prep": rows.get("text_prep", "v1")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
