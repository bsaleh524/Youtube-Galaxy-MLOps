"""Run the local pipeline once: embed → cluster (assign) → build → evaluate → gate. Never publishes.

    uv run python -m pipeline.run [--force]

Skips everything and prints "nothing changed" when the last build was made from the same
inputs: the current snapshot's sha256, data/cluster_names.json and the model's fit run. Each
build records these in its manifest under "inputs".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path


def file_sha256(path: Path) -> str | None:
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def current_inputs(data_dir: Path) -> dict:
    from pipeline.snapshot import load_current

    data_dir = Path(data_dir)
    _, manifest = load_current(data_dir / "raw")
    model_json = data_dir / "model" / "galaxy" / "model.json"
    fit_run = json.loads(model_json.read_text(encoding="utf-8")).get("fit_run_id") if model_json.exists() else None
    return {
        "snapshot_sha256": manifest["sha256"],
        "cluster_names_sha256": file_sha256(data_dir / "cluster_names.json"),
        "fit_run_id": fit_run,
    }


def latest_build_inputs(artifacts: Path) -> dict | None:
    builds = sorted(p for p in Path(artifacts).glob("*") if p.is_dir() and not p.name.startswith("."))
    for b in reversed(builds):
        m = b / "manifest.json"
        if m.exists():
            return json.loads(m.read_text(encoding="utf-8")).get("inputs")
    return None


Step = tuple[str, Callable[[list[str]], int]]
STEP_NAMES = ["embed", "cluster", "build", "evaluate", "gate"]


def run(data_dir: Path, steps: list[Step], force: bool = False, log=print) -> dict:
    """Run steps in order unless inputs match the last build. Returns a summary."""
    data_dir = Path(data_dir)
    if not force and (data_dir / "model" / "galaxy" / "model.json").exists():
        last = latest_build_inputs(data_dir / "artifacts" / "galaxy")
        if last is not None and last == current_inputs(data_dir):
            log("nothing changed since the last build; skipping (use --force to rebuild)")
            return {"skipped": True, "seconds": {}}
    seconds = {}
    for name, fn in steps:
        t = time.perf_counter()
        code = fn([])
        seconds[name] = round(time.perf_counter() - t, 1)
        if code:
            raise SystemExit(f"step {name} failed with exit code {code}")
        log(f"{name}: {seconds[name]} s")
    return {"skipped": False, "seconds": seconds}


def main(argv: list[str] | None = None) -> int:
    from pipeline import build_artifacts, cluster, embed, evaluate, gate
    from pipeline.config import load_settings

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="run even if nothing changed")
    a = ap.parse_args(argv)
    settings = load_settings()
    fns = [embed.main, cluster.main, build_artifacts.main, evaluate.main, gate.main]
    steps = list(zip(STEP_NAMES, fns, strict=True))  # a failing gate stops the run with exit 1
    log = lambda s: print(s, file=sys.stderr)
    summary = run(settings.data_dir, steps, force=a.force, log=log)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
