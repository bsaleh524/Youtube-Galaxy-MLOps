"""
DAG 3: stats_pipeline_dag
Schedule: Wednesday 02:00 UTC (same window as training_pipeline_dag, independent)

Kaggle stats pipeline:
  1. Ingest Kaggle CSV from Oracle Object Storage → validate + clean
  2. Run stats clustering Job (KMeans on subscriber/view/upload counts)
  3. Gate on silhouette score via MLflow
  4. Write cluster labels back into DuckDB on the stats-api PVC
  5. POST to /api/admin/reload to flush the frontend cache
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s


NAMESPACE = "galaxy-pipeline"
REGISTRY = os.getenv("CONTAINER_REGISTRY", "localhost:5000")
COMPUTE_BACKEND = os.getenv("COMPUTE_BACKEND", "cpu")
SILHOUETTE_THRESHOLD = 0.30   # lower bar — numeric clusters are noisier than embedding clusters


@dag(
    dag_id="stats_pipeline_dag",
    description="Ingest Kaggle stats, cluster into archetypes, write to DuckDB",
    schedule="0 2 * * 3",   # Wednesday 02:00 UTC — same window as embedding pipeline
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=15),
    },
    tags=["galaxy", "stats", "mlops"],
)
def stats_pipeline_dag():

    # ── Step 1: Stats training Job ────────────────────────────────────────────
    # Reads the Kaggle CSV from OCI, trains KMeans, writes cluster labels to DuckDB.
    # The Job mounts the same PVC that the stats-api Deployment reads from.

    stats_job = KubernetesPodOperator(
        task_id="stats_training_job",
        name="galaxy-stats-job",
        namespace=NAMESPACE,
        image=f"{REGISTRY}/galaxy-stats-training:latest",
        cmds=["python", "train_stats.py"],
        env_vars={
            "KAGGLE_CSV_PATH":       Variable.get("KAGGLE_CSV_PATH", "data/kaggle/global_youtube_statistics.csv"),
            "DUCKDB_PATH":           "/data/youtube_stats.duckdb",
            "MLFLOW_TRACKING_URI":   Variable.get("MLFLOW_URI", "http://mlflow.galaxy-pipeline:5000"),
            "N_CLUSTERS":            Variable.get("STATS_N_CLUSTERS", "20"),
            "OCI_ENDPOINT_URL":      Variable.get("OCI_ENDPOINT_URL", ""),
            "OCI_ACCESS_KEY":        Variable.get("OCI_ACCESS_KEY", ""),
            "OCI_SECRET_KEY":        Variable.get("OCI_SECRET_KEY", ""),
        },
        # TODO: mount the stats-api PVC here so the Job can write the DuckDB file.
        # volume_mounts=[k8s.V1VolumeMount(name="stats-data", mount_path="/data")],
        # volumes=[k8s.V1Volume(name="stats-data", persistent_volume_claim=...)],
        container_resources=k8s.V1ResourceRequirements(
            requests={"memory": "2Gi", "cpu": "1"},
            limits={"memory": "4Gi", "cpu": "2"},
        ),
        is_delete_operator_pod=True,
        get_logs=True,
        do_xcom_push=True,   # train_stats.py writes {"mlflow_run_id": ..., "silhouette": ..., "row_count": ...}
    )

    # ── Step 2: Quality gate ──────────────────────────────────────────────────

    @task
    def mlflow_quality_gate(job_output: dict) -> dict:
        import mlflow

        run_id = job_output["mlflow_run_id"]
        mlflow_uri = Variable.get("MLFLOW_URI", "http://mlflow.galaxy-pipeline:5000")
        mlflow.set_tracking_uri(mlflow_uri)

        client = mlflow.tracking.MlflowClient()
        run = client.get_run(run_id)
        silhouette = run.data.metrics.get("silhouette_score", 0.0)

        print(f"Run {run_id[:8]}... silhouette_score={silhouette:.4f} (threshold={SILHOUETTE_THRESHOLD})")

        if silhouette < SILHOUETTE_THRESHOLD:
            raise ValueError(
                f"Stats quality gate FAILED: silhouette={silhouette:.4f} < {SILHOUETTE_THRESHOLD}."
            )

        versions = client.search_model_versions(f"run_id='{run_id}'")
        if versions:
            v = versions[0]
            client.transition_model_version_stage("galaxy-stats-kmeans", v.version, "Production")
            print(f"Stats model version {v.version} promoted to Production")

        return {**job_output, "silhouette": silhouette}

    # ── Step 3: Reload ────────────────────────────────────────────────────────
    # Same /api/admin/reload endpoint as the embedding pipeline. The stats-api
    # Deployment listens on a separate port/service but the admin token is shared.

    @task
    def stats_reload(gate_result: dict):
        import httpx

        reload_url = Variable.get("ORACLE_RELOAD_URL", "http://localhost:8000/api/admin/reload")
        admin_token = Variable.get("ADMIN_TOKEN", "changeme")

        try:
            resp = httpx.post(
                reload_url,
                json={"source": "stats_pipeline"},
                headers={"X-Admin-Token": admin_token},
                timeout=30,
            )
            resp.raise_for_status()
            print(f"Stats reload triggered: {resp.json()}")
        except Exception as e:
            print(f"Stats reload failed (non-fatal): {e}")

    # ── Wire ──────────────────────────────────────────────────────────────────

    job_output = stats_job.output
    gated = mlflow_quality_gate(job_output)
    stats_reload(gated)


stats_pipeline_dag()
