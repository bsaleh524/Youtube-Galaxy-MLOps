"""Score a finished build on the eval questions, the way the live Worker answers them.

    uv run python -m pipeline.evaluate [--build DIR] [--questions eval/questions.yaml] [--no-mlflow]

For each question: if it names a creator ("channels like X", see pipeline.name_lookup), the query
is that creator's stored vector and the creator itself is dropped; otherwise the question is
embedded locally with the bge query prefix. Both go through the same two-stage search over the
build's int8 index as worker/src/chat.ts, and through exact brute force for comparison.

Writes data/runs/eval-<version>/report.json and report.md (never inside the build dir, which is
uploaded) and, unless --no-mlflow, logs the run to MLflow (pipeline.tracking).

Metrics: recall@8 (share of expected creators in the top 8), MRR (1/rank of the first expected
creator, 0 if none in the top 8), agreement (share of the exact top 8 the two-stage search also
found), silhouette (cluster separation, on the build's int8 vectors) and the creator count.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pipeline.evalset import load_questions, overlap, recall_at_k, reciprocal_rank, summarize
from pipeline.index_format import IndexData, read_centroids, read_index, read_meta_record
from pipeline.name_lookup import build_name_index, find_named_creator
from pipeline.search import brute_force_search, two_stage_search

K = 8
SEARCH = {
    "probe_min": 3,
    "min_candidates": 1500,
    "max_probe": 12,
}  # = worker/src/search.ts defaults

Encode = Callable[[list[str]], np.ndarray]


@dataclass
class Build:
    path: Path
    version: str
    index: IndexData
    centroids: np.ndarray
    ids: list[str]
    titles: list[str]
    topic_words: set[str]
    names: dict[str, int]


def load_build(build_dir: Path) -> Build:
    build_dir = Path(build_dir)
    w = build_dir / "worker"
    if not (w / "index.bin").exists():
        raise FileNotFoundError(f"{build_dir} is not a build (no worker/index.bin)")
    im = json.loads((w / "index_manifest.json").read_text())
    blob = (w / "meta.bin").read_bytes()
    recs = [read_meta_record(blob, i) for i in range(int(im["n"]))]
    titles = [r["title"] for r in recs]
    topic = set(im.get("topic_words") or [])
    return Build(
        path=build_dir,
        version=im["version"],
        index=read_index(w / "index.bin"),
        centroids=read_centroids(w / "centroids.bin"),
        ids=[r["id"] for r in recs],
        titles=titles,
        topic_words=topic,
        names=build_name_index(titles, topic),
    )


def _row_vector(index: IndexData, row: int) -> np.ndarray:
    v = index.q[row].astype(np.float32) * index.scales[row]
    return v / np.linalg.norm(v)


def answer(build: Build, question: str, encode: Encode) -> tuple[str, list[int], list[int]]:
    """(kind, two-stage rows, brute-force rows), top 8 each, as the Worker would answer."""
    from pipeline.config import QUERY_PREFIX

    named = find_named_creator(question, build.names)
    if named is not None:
        q = _row_vector(build.index, named)
        two = [r for r, _ in two_stage_search(q, build.centroids, build.index, k=K + 1, **SEARCH)]
        brute = [r for r, _ in brute_force_search(q, build.index, k=K + 1)]
        drop = lambda rows: [r for r in rows if r != named][:K]
        return "similar", drop(two), drop(brute)
    q = np.asarray(encode([QUERY_PREFIX + question])[0], dtype=np.float32)
    two = [r for r, _ in two_stage_search(q, build.centroids, build.index, k=K, **SEARCH)]
    brute = [r for r, _ in brute_force_search(q, build.index, k=K)]
    return "topic", two, brute


def silhouette(index: IndexData) -> float | None:
    from pipeline.clusterlib import silhouette_cosine

    X = index.q.astype(np.float32) * index.scales[:, None]
    sizes = np.diff(index.offsets.astype(np.int64))
    labels = np.repeat(np.arange(len(sizes)), sizes)
    s = silhouette_cosine(X, labels)
    return None if s is None else float(s)


def evaluate(build_dir: Path, questions_path: Path, encode: Encode) -> dict:
    b = load_build(build_dir)
    questions = load_questions(questions_path, b.ids, b.titles)
    rows = []
    for q in questions:
        kind, two, brute = answer(b, q.question, encode)
        got = [b.ids[r] for r in two]
        scored = bool(q.expected_ids)
        rows.append(
            {
                "question": q.question,
                "status": q.status,
                "kind": kind,
                "expected": q.expected_ids,
                "unknown": q.unknown,
                "got": got,
                "got_titles": [b.titles[r] for r in two],
                "recall_at_8": recall_at_k(got, q.expected_ids, K) if scored else None,
                "rr": reciprocal_rank(got, q.expected_ids, K) if scored else None,
                "agreement": overlap(two, brute),
            }
        )
    return {
        "version": b.version,
        "creators": len(b.ids),
        "silhouette": silhouette(b.index),
        "search_params": {"k": K, **SEARCH},
        "questions_sha256": hashlib.sha256(Path(questions_path).read_bytes()).hexdigest(),
        "summary": summarize(rows),
        "per_question": rows,
    }


def _fmt(x) -> str:
    return "—" if x is None else f"{x:.3f}"


def _summary_line(label: str, b: dict) -> str:
    return f"- {label}: n={b['n']}, recall@8 {_fmt(b['recall_at_8'])}, MRR {_fmt(b['mrr'])}"


def format_markdown(r: dict) -> str:
    s = r["summary"]
    lines = [
        f"# Eval report — {r['version']}",
        "",
        f"- creators: {r['creators']}",
        f"- silhouette (int8): {_fmt(r['silhouette'])}",
        f"- brute-force agreement: {_fmt(s['agreement'])}",
        _summary_line("approved", s["approved"]),
        _summary_line("all (drafts too)", s["all"]),
        "",
        "| status | question | kind | recall@8 | RR | agreement | top results |",
        "|---|---|---|---|---|---|---|",
    ]
    for q in r["per_question"]:
        top = ", ".join(q["got_titles"][:5])
        if q["unknown"]:
            top += f" (unknown expected: {', '.join(q['unknown'])})"
        lines.append(
            f"| {q['status']} | {q['question']} | {q['kind']} | {_fmt(q['recall_at_8'])} |"
            f" {_fmt(q['rr'])} | {_fmt(q['agreement'])} | {top} |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: dict, runs_dir: Path) -> Path:
    out = Path(runs_dir) / f"eval-{report['version']}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (out / "report.md").write_text(format_markdown(report), encoding="utf-8")
    return out / "report.json"


def make_encoder(settings) -> Encode:
    from pipeline.embed import SentenceTransformerEncoder

    return SentenceTransformerEncoder(settings.embedding_model, 32).encode


def main(argv: list[str] | None = None) -> int:
    from pipeline.config import load_settings
    from pipeline.publish import newest_build

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--build", type=Path, help="build dir (default: newest)")
    ap.add_argument("--questions", type=Path, default=Path("eval/questions.yaml"))
    ap.add_argument("--no-mlflow", action="store_true", help="don't log the run to MLflow")
    a = ap.parse_args(argv)
    settings = load_settings()
    build_dir = a.build or newest_build(settings.data_dir / "artifacts" / "galaxy")
    report = evaluate(build_dir, a.questions, make_encoder(settings))
    path = write_report(report, settings.data_dir / "runs")
    print(format_markdown(report), file=sys.stderr)
    print(f"report: {path}", file=sys.stderr)
    if not a.no_mlflow:
        from pipeline.tracking import log_eval

        run_id = log_eval(report, Path(build_dir), settings.data_dir)
        print(f"mlflow run: {run_id}", file=sys.stderr)
    print(json.dumps({"version": report["version"], "report": str(path), **report["summary"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
