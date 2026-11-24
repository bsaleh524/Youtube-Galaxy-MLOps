"""The eval question set (eval/questions.yaml) and the retrieval metrics computed on it.

Each entry: {question, expected: [ids or titles], notes, status: draft|approved}. An expected
entry starting with "fandom_" is a creator id; anything else is a title, matched after folding
(pipeline.name_lookup.fold_name). Every creator with that folded title counts, so duplicate
titles expand to several ids. Entries that match nothing are kept in `unknown` and reported.
Only approved questions count toward the gated numbers; drafts are reported, never gated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from pipeline.name_lookup import fold_name

STATUSES = ("draft", "approved")


@dataclass
class Question:
    question: str
    expected_ids: list[str]
    status: str
    notes: str = ""
    unknown: list[str] = field(default_factory=list)


def load_questions(path: Path, ids: list[str], titles: list[str]) -> list[Question]:
    entries = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    known = set(ids)
    by_title: dict[str, list[str]] = {}
    for i, t in zip(ids, titles, strict=True):
        by_title.setdefault(fold_name(t), []).append(i)
    out = []
    for e in entries:
        q = str(e.get("question", "")).strip()
        status = e.get("status")
        if not q:
            raise ValueError(f"eval question without text: {e!r}")
        if status not in STATUSES:
            raise ValueError(f"question {q!r}: status must be draft or approved, not {status!r}")
        expected: list[str] = []
        unknown: list[str] = []
        for raw in e.get("expected") or []:
            raw = str(raw)
            if raw.startswith("fandom_"):
                hits = [raw] if raw in known else []
            else:
                hits = by_title.get(fold_name(raw), [])
            if not hits:
                unknown.append(raw)
            for h in hits:
                if h not in expected:
                    expected.append(h)
        out.append(Question(q, expected, status, str(e.get("notes") or ""), unknown))
    return out


def recall_at_k(got_ids: list[str], expected: list[str], k: int = 8) -> float:
    if not expected:
        return 0.0
    return len(set(got_ids[:k]) & set(expected)) / len(set(expected))


def reciprocal_rank(got_ids: list[str], expected: list[str], k: int = 8) -> float:
    want = set(expected)
    for rank, g in enumerate(got_ids[:k], start=1):
        if g in want:
            return 1.0 / rank
    return 0.0


def overlap(a: list[int], b: list[int]) -> float:
    """Share of b (the exact brute-force answer) that a (two-stage) also returned."""
    return len(set(a) & set(b)) / max(len(b), 1)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def summarize(per_question: list[dict]) -> dict:
    """Means over questions that have expected ids; approved ones separately. Agreement over all."""

    def block(rows: list[dict]) -> dict:
        scored = [r for r in rows if r["expected"]]
        return {
            "n": len(scored),
            "recall_at_8": _mean([r["recall_at_8"] for r in scored]),
            "mrr": _mean([r["rr"] for r in scored]),
        }

    return {
        "approved": block([r for r in per_question if r["status"] == "approved"]),
        "all": block(per_question),
        "agreement": _mean([r["agreement"] for r in per_question]),
    }
