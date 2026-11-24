"""MLflow tracking for eval runs, and the `champion` alias that marks the live build.

    uv run python -m pipeline.tracking show                    # what's live, per MLflow
    uv run python -m pipeline.tracking champion --version V    # mark an evaluated build as live

The store is sqlite at <data_dir>/mlflow/mlflow.db (the same DB `make mlflow` serves), with
artifacts under <data_dir>/mlflow/artifacts. Each `make eval` is one run in experiment
"galaxy-refresh", tagged galaxy.version. Publishing points alias "champion" of registered model
"galaxy" at a model version made from that run's bundle/ artifacts (the build manifests).
mlflow is imported inside functions so the light CI group can import this module's callers.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pipeline.evaluate import format_markdown

EXPERIMENT = "galaxy-refresh"
MODEL = "galaxy"
ALIAS = "champion"
VERSION_TAG = "galaxy.version"


def tracking_uri(data_dir: Path) -> str:
    db = (Path(data_dir) / "mlflow" / "mlflow.db").resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db}"


def _client(data_dir: Path):
    logging.getLogger("mlflow").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)
    from mlflow import MlflowClient

    return MlflowClient(tracking_uri=tracking_uri(data_dir), registry_uri=tracking_uri(data_dir))


def _experiment_id(client, data_dir: Path) -> str:
    exp = client.get_experiment_by_name(EXPERIMENT)
    if exp is not None:
        return exp.experiment_id
    artifacts = (Path(data_dir) / "mlflow" / "artifacts").resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    return client.create_experiment(EXPERIMENT, artifact_location=str(artifacts))


def _metrics(report: dict) -> dict[str, float]:
    s = report["summary"]
    raw = {
        "recall_at_8_approved": s["approved"]["recall_at_8"],
        "mrr_approved": s["approved"]["mrr"],
        "recall_at_8_all": s["all"]["recall_at_8"],
        "mrr_all": s["all"]["mrr"],
        "agreement": s["agreement"],
        "silhouette": report.get("silhouette"),
        "creators": report.get("creators"),
        "questions_approved": s["approved"]["n"],
        "questions_all": s["all"]["n"],
    }
    return {k: float(v) for k, v in raw.items() if v is not None}


def log_eval(report: dict, build_dir: Path, data_dir: Path) -> str:
    """One MLflow run for this eval: params, metrics, report and the build's manifests."""
    client = _client(data_dir)
    exp = _experiment_id(client, data_dir)
    version = report["version"]
    run = client.create_run(exp, run_name=version, tags={VERSION_TAG: version})
    rid = run.info.run_id
    params = {"version": version, "questions_sha256": report["questions_sha256"]}
    params.update({f"search_{k}": v for k, v in report["search_params"].items()})
    for k, v in params.items():
        client.log_param(rid, k, v)
    for k, v in _metrics(report).items():
        client.log_metric(rid, k, v)
    client.log_text(rid, json.dumps(report, indent=1, ensure_ascii=False), "report.json")
    client.log_text(rid, format_markdown(report), "report.md")
    build_dir = Path(build_dir)
    for rel in ("manifest.json", "worker/index_manifest.json"):
        p = build_dir / rel
        if p.exists():
            client.log_artifact(rid, str(p), "bundle")
    client.set_terminated(rid)
    return rid


def _latest_run(client, exp_id: str, version: str):
    runs = client.search_runs(
        [exp_id],
        f"tags.`{VERSION_TAG}` = '{version}'",
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    return runs[0] if runs else None


def set_champion(data_dir: Path, version: str) -> str | None:
    """Point the champion alias at the newest eval run of `version`. None if it was never evaluated."""
    from mlflow.exceptions import MlflowException

    client = _client(data_dir)
    run = _latest_run(client, _experiment_id(client, data_dir), version)
    if run is None:
        return None
    try:
        client.get_registered_model(MODEL)
    except MlflowException:
        client.create_registered_model(MODEL)
    mv = client.create_model_version(
        MODEL,
        source=f"{run.info.artifact_uri}/bundle",
        run_id=run.info.run_id,
        tags={VERSION_TAG: version},
    )
    client.set_registered_model_alias(MODEL, ALIAS, mv.version)
    return str(mv.version)


def champion(data_dir: Path) -> dict | None:
    """{"version", "run_id", "model_version", "metrics"} of the live build, or None if none is set."""
    from mlflow.exceptions import MlflowException

    client = _client(data_dir)
    try:
        mv = client.get_model_version_by_alias(MODEL, ALIAS)
    except MlflowException:
        return None
    run = client.get_run(mv.run_id)
    return {
        "version": run.data.tags.get(VERSION_TAG),
        "run_id": mv.run_id,
        "model_version": str(mv.version),
        "metrics": dict(run.data.metrics),
    }


def main(argv: list[str] | None = None) -> int:
    from pipeline.config import load_settings

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="print the champion")
    c = sub.add_parser("champion", help="mark an evaluated build as the live one")
    c.add_argument("--version", required=True)
    a = ap.parse_args(argv)
    data_dir = load_settings().data_dir
    if a.cmd == "champion":
        mv = set_champion(data_dir, a.version)
        if mv is None:
            print(f"no eval run for {a.version}; run `make eval BUILD=...` first", file=sys.stderr)
            return 1
        print(f"champion -> {a.version} (model {MODEL} version {mv})")
        return 0
    print(json.dumps(champion(data_dir), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
