"""Quality gate: pass or fail a build's eval report before it may be published.

    uv run python -m pipeline.gate [--version V] [--config eval/gate.yaml]

Reads data/runs/eval-<version>/report.json (from `make eval`), compares it with the thresholds
in eval/gate.yaml and with the live build's eval run in MLflow (the `champion`), prints one
line per check and writes data/runs/eval-<version>/gate.json. Exit 0 = pass, 1 = fail.
`make publish` refuses a build without a passing gate.json for its version.

Checks: silhouette >= floor; approved recall@8 >= live recall - tolerance; creators >= ratio x
live creators (and > 0); brute-force agreement >= minimum. Recall and creators pass when there
is nothing to compare with (first gated publish, no approved questions, or the questions file
changed since the live build was scored); the reason says so.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, fields
from pathlib import Path

import yaml


@dataclass(frozen=True)
class GateConfig:
    silhouette_floor: float
    recall_tolerance: float
    count_ratio: float
    agreement_min: float


def load_config(path: Path) -> GateConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    for f in fields(GateConfig):
        if raw.get(f.name) is None:
            raise ValueError(f"{path}: missing {f.name}")
    return GateConfig(**{f.name: float(raw[f.name]) for f in fields(GateConfig)})


def _c(name, passed, value, threshold, reason) -> dict:
    return {
        "name": name,
        "passed": bool(passed),
        "value": value,
        "threshold": threshold,
        "reason": reason,
    }


def _silhouette(report: dict, cfg: GateConfig) -> dict:
    s, floor = report.get("silhouette"), cfg.silhouette_floor
    if s is None:
        return _c(
            "silhouette",
            False,
            None,
            floor,
            "Silhouette could not be computed (fewer than 2 clusters?).",
        )
    if s >= floor:
        return _c(
            "silhouette",
            True,
            s,
            floor,
            f"Silhouette {s:.3f} is at or above the floor {floor:.3f}.",
        )
    return _c(
        "silhouette",
        False,
        s,
        floor,
        f"Silhouette {s:.3f} is below the floor {floor:.3f}: clusters got blurrier than the baseline run.",
    )


def _recall(report: dict, previous: dict | None, cfg: GateConfig) -> dict:
    approved = report["summary"]["approved"]
    value = approved["recall_at_8"]
    if not approved["n"] or value is None:
        return _c(
            "recall", True, None, None, "skipped (no approved questions in eval/questions.yaml)"
        )
    if previous is None:
        return _c(
            "recall",
            True,
            value,
            None,
            f"Recall@8 {value:.3f}; no previous publish to compare with.",
        )
    before = previous.get("metrics", {}).get("recall_at_8_approved")
    if before is None:
        return _c(
            "recall",
            True,
            value,
            None,
            "skipped (the live build has no approved recall to compare with)",
        )
    if previous.get("params", {}).get("questions_sha256") != report.get("questions_sha256"):
        return _c(
            "recall",
            True,
            value,
            None,
            "skipped (eval questions changed since the live build was scored; "
            "re-run `make eval BUILD=<live build>` to compare)",
        )
    floor = before - cfg.recall_tolerance
    if value >= floor - 1e-9:
        return _c(
            "recall",
            True,
            value,
            floor,
            f"Recall@8 {value:.3f} vs live {before:.3f} (allowed down to {floor:.3f}).",
        )
    return _c(
        "recall",
        False,
        value,
        floor,
        f"Recall@8 {value:.3f} dropped below {floor:.3f} (live build: {before:.3f}): "
        "search finds fewer of the expected creators.",
    )


def _creators(report: dict, previous: dict | None, cfg: GateConfig) -> dict:
    n = int(report.get("creators") or 0)
    if n <= 0:
        return _c("creators", False, n, None, "The build has no creators.")
    before = (previous or {}).get("metrics", {}).get("creators")
    if previous is None or before is None:
        return _c("creators", True, n, None, f"{n} creators; no previous publish to compare with.")
    need = int(cfg.count_ratio * before)
    if n >= need:
        return _c("creators", True, n, need, f"{n} creators (need at least {need}).")
    return _c(
        "creators",
        False,
        n,
        need,
        f"Only {n} creators, need at least {need} ({cfg.count_ratio:.0%} of the live {int(before)}): "
        "the data looks partial.",
    )


def _agreement(report: dict, cfg: GateConfig) -> dict:
    a, need = report["summary"].get("agreement"), cfg.agreement_min
    if a is None:
        return _c("agreement", False, None, need, "No questions to measure agreement on.")
    if a >= need:
        return _c(
            "agreement",
            True,
            a,
            need,
            f"Two-stage search found {a:.3f} of the exact top 8 (need {need:.3f}).",
        )
    return _c(
        "agreement",
        False,
        a,
        need,
        f"Two-stage search found only {a:.3f} of the exact top 8 (need {need:.3f}): the speed shortcut costs too much.",
    )


def check(report: dict, previous: dict | None, cfg: GateConfig) -> dict:
    checks = [
        _silhouette(report, cfg),
        _recall(report, previous, cfg),
        _creators(report, previous, cfg),
        _agreement(report, cfg),
    ]
    return {
        "version": report["version"],
        "passed": all(c["passed"] for c in checks),
        "compared_with": (previous or {}).get("version"),
        "checks": checks,
    }


def write_gate(result: dict, runs_dir: Path) -> Path:
    out = Path(runs_dir) / f"eval-{result['version']}" / "gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    return out


def read_gate(runs_dir: Path, version: str) -> dict | None:
    p = Path(runs_dir) / f"eval-{version}" / "gate.json"
    return json.loads(p.read_text()) if p.exists() else None


def previous_publish(data_dir: Path) -> dict | None:
    from pipeline.tracking import champion

    return champion(data_dir)


def main(argv: list[str] | None = None) -> int:
    from pipeline.config import load_settings
    from pipeline.publish import newest_build

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--version", help="build version (default: newest build)")
    ap.add_argument("--config", type=Path, default=Path("eval/gate.yaml"))
    a = ap.parse_args(argv)
    data_dir = load_settings().data_dir
    version = a.version or newest_build(data_dir / "artifacts" / "galaxy").name
    rpath = data_dir / "runs" / f"eval-{version}" / "report.json"
    if not rpath.exists():
        print(f"no eval report for {version}; run `make eval` first", file=sys.stderr)
        return 1
    result = check(json.loads(rpath.read_text()), previous_publish(data_dir), load_config(a.config))
    path = write_gate(result, data_dir / "runs")
    for c in result["checks"]:
        print(
            f"{'PASS' if c['passed'] else 'FAIL'}  {c['name']:<10} {c['reason']}", file=sys.stderr
        )
    verdict = "PASSED" if result["passed"] else "FAILED: nothing will be published"
    print(
        f"gate {verdict} ({version}; compared with {result['compared_with'] or 'nothing'}) -> {path}",
        file=sys.stderr,
    )
    print(json.dumps({"version": version, "passed": result["passed"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
