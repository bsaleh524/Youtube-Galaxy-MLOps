"""Stable cluster keys, names and colours.

Every cluster gets a key (`c001`, `c002`, ...) that is never reused. The registry, saved with
the model as `registry.json`, maps each key ever issued to its name, colour and name source:

    {"next_key": 121, "clusters": {"c001": {"name", "colour", "source", "active", "size", "keywords"}}}

source is one of "owner" (data/cluster_names.json, always wins), "seed" (bootstrapped from
the old labelled data), "carried" (inherited from the previous fit) or "placeholder" (top
TF-IDF keywords of the cluster, waiting for the owner to name it).

- First fit (no previous model): names come from the seed by Jaccard overlap of member ids,
  matched one-to-one (Hungarian); a match below the threshold leaves the cluster unnamed.
- Later fits: keys carry over by centroid cosine, matched one-to-one; below min_cos a cluster
  is new. Carried clusters keep name and colour; new ones get a new key and colour.
- Assign mode never calls this module: identity is fixed between fits.

Nothing here calls an LLM. `write_review` writes naming packs with a ready-to-paste prompt.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from pipeline import palette

SEED_THRESHOLD = 0.2
CARRY_MIN_COS = 0.8
SEP = " · "
PACK_TITLES = 30
# Wiki biography boilerplate that says nothing about a cluster's topic.
WIKI_STOP_WORDS = frozenset(
    [
        "age",
        "born",
        "birthday",
        "known",
        "better",
        "formerly",
        "previously",
        "professionally",
        "online",
        "stated",
        "said",
        "saying",
        "american",
        "content",
        "youtuber",
        "youtubers",
        "creator",
        "creators",
        "note",
        "zones",
        "vary",
        "differences",
        "according",
        "dates",
        "days",
        "following",
        "individuals",
        "numbers",
        "people",
        "subscribers",
        "uploads",
        "uploaded",
        "videos",
        "video",
    ]
)


def _seed_jaccard(labels: np.ndarray, ids: list[str], seed_names: dict[str, str], k: int):
    names = sorted(set(seed_names.values()))
    col = {n: j for j, n in enumerate(names)}
    inter = np.zeros((k, len(names)))
    for lab, rid in zip(labels.tolist(), ids, strict=True):
        if rid in seed_names:
            inter[lab, col[seed_names[rid]]] += 1
    size_c = np.bincount(labels, minlength=k).astype(float)
    size_n = np.zeros(len(names))
    for n in seed_names.values():
        size_n[col[n]] += 1
    union = size_c[:, None] + size_n[None, :] - inter
    return np.divide(inter, union, out=np.zeros_like(inter), where=union > 0), names


def bootstrap_scores(labels, ids, seed_names, threshold=SEED_THRESHOLD, k=None):
    """(names, scores): names[label] is a seed name or None; scores[label] is the Jaccard of the
    one-to-one match (also reported when it fell below the threshold)."""
    k = int(k if k is not None else labels.max() + 1)
    names_out: dict[int, str | None] = dict.fromkeys(range(k))
    scores: dict[int, float] = {}
    if not seed_names:
        return names_out, scores
    J, names = _seed_jaccard(np.asarray(labels), ids, seed_names, k)
    rows, cols = linear_sum_assignment(-J)
    for r, c in zip(rows.tolist(), cols.tolist(), strict=True):
        scores[r] = float(J[r, c])
        if J[r, c] >= threshold:
            names_out[r] = names[c]
    return names_out, scores


def bootstrap_from_seed(
    labels, ids, seed_names, threshold=SEED_THRESHOLD, k=None
) -> dict[int, str | None]:
    return bootstrap_scores(labels, ids, seed_names, threshold, k)[0]


def carry_scores(new_centroids, prev_centroids, prev_keys, min_cos=CARRY_MIN_COS):
    """(keys, scores): keys[label] is an inherited previous key or None."""
    k = len(new_centroids)
    keys: dict[int, str | None] = dict.fromkeys(range(k))
    scores: dict[int, float] = {}
    usable = [j for j, key in enumerate(prev_keys) if key is not None]
    if not usable:
        return keys, scores
    cos = (
        np.asarray(new_centroids, dtype=np.float64)
        @ np.asarray(prev_centroids, dtype=np.float64)[usable].T
    )
    rows, cols = linear_sum_assignment(-cos)
    for r, c in zip(rows.tolist(), cols.tolist(), strict=True):
        scores[r] = float(cos[r, c])
        if cos[r, c] >= min_cos:
            keys[r] = prev_keys[usable[c]]
    return keys, scores


def carry_over(
    new_centroids, prev_centroids, prev_keys, min_cos=CARRY_MIN_COS
) -> dict[int, str | None]:
    return carry_scores(new_centroids, prev_centroids, prev_keys, min_cos)[0]


def key_number(key: str) -> int:
    return int(key[1:])


def assign_keys(matched: dict[int, str | None], k: int, next_key: int) -> tuple[list[str], int]:
    """Matched labels keep their key; the rest get fresh `c{n:03d}` keys from next_key upwards."""
    keys = []
    for label in range(k):
        key = matched.get(label)
        if key is None:
            key = f"c{next_key:03d}"
            next_key += 1
        keys.append(key)
    return keys, next_key


def cluster_keywords(
    labels: np.ndarray, k: int, texts: list[str], top: int = 10
) -> dict[int, list[str]]:
    """Distinctive words per cluster, counted per member rather than per occurrence so one
    page's rare proper nouns can't dominate. A word scores p_c * log(p_c / p), where p_c is
    the share of the cluster's members whose text contains it and p the share of all
    creators. Words in over half of all texts (youtube, channel, born...) are ignored, and
    a word must appear in at least 3 members (or every member of a tinier cluster)."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

    labels = np.asarray(labels)
    out: dict[int, list[str]] = {i: [] for i in range(k)}
    vec = CountVectorizer(
        stop_words=sorted(ENGLISH_STOP_WORDS | WIKI_STOP_WORDS),
        token_pattern=r"(?u)\b[^\W\d_][^\W_]{2,}\b",
        binary=True,
        min_df=2,
        max_df=0.5 if len(texts) >= 10 else 1.0,
    )
    try:
        M = vec.fit_transform(texts).tocsc().astype(np.float64)
    except ValueError:  # empty vocabulary
        return out
    vocab = vec.get_feature_names_out()
    p = np.asarray(M.sum(axis=0)).ravel() / len(texts)
    onehot = np.zeros((len(texts), k))
    onehot[np.arange(len(texts)), labels] = 1
    counts = (M.T @ onehot).T  # (k, vocab): members containing each word
    sizes = onehot.sum(axis=0)
    for c in range(k):
        if sizes[c] == 0:
            continue
        pc = counts[c] / sizes[c]
        score = np.where(
            (counts[c] >= min(3, sizes[c])) & (pc > p), pc * np.log(np.maximum(pc, 1e-12) / p), 0.0
        )
        order = np.lexsort((np.arange(len(vocab)), -score))
        out[c] = [str(vocab[j]) for j in order[:top] if score[j] > 0]
    return out


def placeholder(keywords: list[str], key: str) -> str:
    return SEP.join(keywords[:3]) if keywords else f"cluster {key}"


def name_clusters(
    labels: np.ndarray,
    ids: list[str],
    centroids: np.ndarray,
    texts: list[str],
    prev_registry: dict | None,
    prev_centroids: np.ndarray | None,
    prev_keys: list[str | None] | None,
    seed_names: dict[str, str],
    owner_names: dict[str, str],
    threshold: float = SEED_THRESHOLD,
    min_cos: float = CARRY_MIN_COS,
) -> tuple[list[str], dict, dict]:
    """Fit mode naming. Returns (keys per label, registry, report)."""
    k = len(centroids)
    sizes = np.bincount(labels, minlength=k)
    keywords = cluster_keywords(labels, k, texts)
    carry = prev_registry is not None and prev_keys is not None and any(prev_keys)
    if carry:
        matched, scores = carry_scores(centroids, prev_centroids, prev_keys, min_cos)
        seed_for = dict.fromkeys(range(k))
        registry = copy.deepcopy(prev_registry)
        for entry in registry["clusters"].values():
            entry["active"] = False
    else:
        matched = dict.fromkeys(range(k))
        seed_for, scores = bootstrap_scores(labels, ids, seed_names, threshold, k)
        registry = {"next_key": 1, "clusters": {}}
    keys, registry["next_key"] = assign_keys(matched, k, registry["next_key"])

    kept_colours = [
        registry["clusters"][key]["colour"] for key in keys if key in registry["clusters"]
    ]
    retired_colours = [e["colour"] for key, e in registry["clusters"].items() if key not in keys]
    n_new = sum(key not in registry["clusters"] for key in keys)
    fresh = iter(palette.new_colours(kept_colours, n_new, avoid=retired_colours))
    for label, key in enumerate(keys):
        old = registry["clusters"].get(key)
        entry = {"colour": old["colour"] if old else next(fresh)}
        if key in owner_names:
            entry.update(name=owner_names[key], source="owner")
        elif old and old["source"] != "placeholder":
            entry.update(name=old["name"], source="carried")
        elif seed_for.get(label):
            entry.update(name=seed_for[label], source="seed")
        else:
            entry.update(name=placeholder(keywords[label], key), source="placeholder")
        entry.update(active=True, size=int(sizes[label]), keywords=keywords[label])
        registry["clusters"][key] = entry

    active = [registry["clusters"][key] for key in keys]
    matched_scores = sorted(scores.values())
    report = {
        "method": "carried" if carry else "seed",
        "threshold": min_cos if carry else threshold,
        "match_scores": {
            "count": len(matched_scores),
            "min": round(matched_scores[0], 4) if matched_scores else None,
            "median": round(float(np.median(matched_scores)), 4) if matched_scores else None,
            "max": round(matched_scores[-1], 4) if matched_scores else None,
            "below_threshold": sum(s < (min_cos if carry else threshold) for s in matched_scores),
        },
        "sources": {
            s: sum(e["source"] == s for e in active)
            for s in ("owner", "seed", "carried", "placeholder")
        },
        "retired": sorted(key for key, e in registry["clusters"].items() if not e["active"]),
        "colour_min_distance": round(palette.min_distance([e["colour"] for e in active]), 4),
        "duplicate_names": sorted(
            {e["name"] for e in active if sum(f["name"] == e["name"] for f in active) > 1}
        ),
    }
    return keys, registry, report


def _snippet(description: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", description or "").strip()
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def write_review(
    run_dir: Path,
    keys: list[str],
    registry: dict,
    labels: np.ndarray,
    X: np.ndarray,
    centroids: np.ndarray,
    ids: list[str],
    records: dict[str, dict],
) -> list[str]:
    """Write unnamed_clusters.md and one naming pack per placeholder cluster. Returns their keys."""
    run_dir = Path(run_dir)
    packs = run_dir / "naming_packs"
    packs.mkdir(parents=True, exist_ok=True)
    named = sorted(
        {
            e["name"]
            for e in registry["clusters"].values()
            if e["active"] and e["source"] != "placeholder"
        }
    )
    examples = (
        "; ".join(named[:12]) or "Minecraft Commentary & SMPs; Beauty & Lifestyle Influencers"
    )
    unnamed = [
        (label, key)
        for label, key in enumerate(keys)
        if registry["clusters"][key]["source"] == "placeholder"
    ]
    lines = [
        "# Unnamed clusters",
        "",
        f"{len(unnamed)} of {len(keys)} clusters have a placeholder name. To name one, add it to",
        '`data/cluster_names.json` as `{"<key>": "<name>"}`; owner names always win.',
        "Each pack in `naming_packs/` has the cluster's creators and a prompt for any free chatbot.",
        "",
        "| key | size | placeholder |",
        "|---|---|---|",
    ]
    for label, key in unnamed:
        e = registry["clusters"][key]
        lines.append(f"| {key} | {e['size']} | {e['name']} |")
        members = np.flatnonzero(labels == label)
        order = members[np.argsort(-(X[members] @ centroids[label]), kind="stable")][:PACK_TITLES]
        creators = "\n".join(
            f"- **{records[ids[i]]['title']}**: {_snippet(records[ids[i]].get('description', ''))}"
            for i in order
        )
        titles = ", ".join(records[ids[i]]["title"] for i in order)
        prompt = (
            "These YouTube creators were grouped together because their wiki pages are similar. "
            "Suggest one short name (2-5 words) for the group, in the same style as these existing "
            f"group names: {examples}. Keywords: {', '.join(e['keywords'])}. Creators: {titles}. "
            "Reply with the name only."
        )
        pack = (
            f"# {key}\n\nSize: {e['size']} creators\n\nPlaceholder: {e['name']}\n\n"
            f"Top keywords: {', '.join(e['keywords'])}\n\n"
            f"## {len(order)} creators nearest the centre\n\n{creators}\n\n"
            f"## Prompt (paste into a free chatbot)\n\n```\n{prompt}\n```\n"
        )
        (packs / f"{key}.md").write_text(pack, encoding="utf-8")
    (run_dir / "unnamed_clusters.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [key for _, key in unnamed]
