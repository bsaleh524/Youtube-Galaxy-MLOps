"""
DAG 2: training_pipeline_dag
Schedule: Wednesday 02:00 UTC (or triggered by fandom_scrape_dag)

Full ML pipeline:
  1. Run training Job (embed + cluster + UMAP) on k3s GPU/CPU node
  2. Gate on silhouette score via MLflow
  3. Upload Parquet artifacts to Oracle Object Storage
  4. Feast materialize (offline → online store)
  5. POST to Oracle Cloud to reload Weaviate and invalidate caches
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import mlflow
from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s


NAMESPACE = "galaxy-pipeline"
REGISTRY = os.getenv("CONTAINER_REGISTRY", "localhost:5000")
COMPUTE_BACKEND = os.getenv("COMPUTE_BACKEND", "cpu")
SILHOUETTE_THRESHOLD = 0.40


def _build_training_resources() -> k8s.V1ResourceRequirements:
    """Return resource requests with or without GPU based on COMPUTE_BACKEND."""
    base = {"memory": "10Gi", "cpu": "2"}
    limits = {"memory": "14Gi", "cpu": "4"}
    if COMPUTE_BACKEND == "gpu":
        base["nvidia.com/gpu"] = "1"
        limits["nvidia.com/gpu"] = "1"
    return k8s.V1ResourceRequirements(requests=base, limits=limits)


@dag(
    dag_id="training_pipeline_dag",
    description="Embed + cluster creators, validate with MLflow, deploy to production",
    schedule="0 2 * * 3",   # Wednesday 02:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=15),
    },
    tags=["galaxy", "training", "mlops"],
)
def training_pipeline_dag():

    # ── Step 1: Run training as a Kubernetes Job ─────────────────────────────

    training_job = KubernetesPodOperator(
        task_id="training_job",
        name="galaxy-training-job",
        namespace=NAMESPACE,
        image=f"{REGISTRY}/galaxy-training:latest",
        cmds=["python", "train.py"],
        env_vars={
            "INPUT_PATH":           Variable.get("OCI_RAW_PATH", "data/fandom/youtubers_data_combined.json"),
            "OUTPUT_PATH":          Variable.get("OCI_FEATURES_PATH", "data/features/starmap_data.parquet"),
            "MLFLOW_TRACKING_URI":  Variable.get("MLFLOW_URI", "http://mlflow.galaxy-pipeline:5000"),
            "N_CLUSTERS":           Variable.get("N_CLUSTERS", "120"),
            "OCI_ENDPOINT_URL":     Variable.get("OCI_ENDPOINT_URL", ""),
            "OCI_ACCESS_KEY":       Variable.get("OCI_ACCESS_KEY", ""),
            "OCI_SECRET_KEY":       Variable.get("OCI_SECRET_KEY", ""),
        },
        container_resources=_build_training_resources(),
        is_delete_operator_pod=True,
        get_logs=True,
        do_xcom_push=True,  # train.py writes {"mlflow_run_id": ..., "silhouette": ..., "output_path": ...}
    )

    # ── Step 2: Quality gate via MLflow ──────────────────────────────────────

    @task
    def mlflow_quality_gate(training_output: dict) -> dict:
        """
        Pull the run from MLflow and check silhouette score.
        Raises if below threshold — this marks the DAG run as failed and
        prevents the upload + deployment steps from running.
        """
        run_id = training_output["mlflow_run_id"]
        mlflow_uri = Variable.get("MLFLOW_URI", "http://mlflow.galaxy-pipeline:5000")
        mlflow.set_tracking_uri(mlflow_uri)

        client = mlflow.tracking.MlflowClient()
        run = client.get_run(run_id)
        silhouette = run.data.metrics.get("silhouette_score", 0.0)

        print(f"Run {run_id[:8]}... silhouette_score={silhouette:.4f} (threshold={SILHOUETTE_THRESHOLD})")

        if silhouette < SILHOUETTE_THRESHOLD:
            raise ValueError(
                f"Quality gate FAILED: silhouette={silhouette:.4f} < {SILHOUETTE_THRESHOLD}. "
                "Aborting deployment."
            )

        # Promote model to Production in MLflow registry
        versions = client.search_model_versions(f"run_id='{run_id}'")
        if versions:
            v = versions[0]
            client.transition_model_version_stage("galaxy-kmeans", v.version, "Production")
            print(f"Model version {v.version} promoted to Production")

        return {**training_output, "silhouette": silhouette}

    # ── Step 3: Upload artifacts to Oracle Object Storage ────────────────────

    @task
    def upload_artifacts(gate_result: dict) -> dict:
        """
        Upload the generated Parquet to Oracle Object Storage so Oracle Cloud
        can serve it and Feast can materialize from it.
        """
        import boto3, datetime as dt

        output_path = gate_result["output_path"]
        bucket = Variable.get("OCI_BUCKET", "galaxy-artifacts")
        endpoint = Variable.get("OCI_ENDPOINT_URL", "")
        run_date = dt.datetime.utcnow().strftime("%Y-%m-%d")
        dest_key = f"features/starmap/{run_date}/starmap_data.parquet"
        latest_key = "features/starmap/latest/starmap_data.parquet"

        if endpoint:  # Oracle Object Storage
            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=Variable.get("OCI_ACCESS_KEY"),
                aws_secret_access_key=Variable.get("OCI_SECRET_KEY"),
            )
            s3.upload_file(output_path, bucket, dest_key)
            s3.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": dest_key}, Key=latest_key)
            print(f"Uploaded to s3://{bucket}/{dest_key}")
        else:
            print(f"[LOCAL] Would upload {output_path} to {dest_key}")

        return {**gate_result, "s3_path": f"s3://{bucket}/{dest_key}"}

    # ── Step 4: Feast materialize ─────────────────────────────────────────────

    @task
    def feast_materialize(upload_result: dict):
        """Push updated features from offline store (OCI Parquet) to online store (Redis)."""
        import subprocess, datetime as dt

        end_date = dt.datetime.utcnow().isoformat()
        result = subprocess.run(
            ["feast", "materialize-incremental", end_date],
            cwd=os.path.join(os.environ.get("AIRFLOW_HOME", "/opt/airflow"), "../features"),
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            raise RuntimeError(f"feast materialize failed: {result.stderr}")
        print("Feast materialization complete")

    # ── Step 5: Notify Oracle Cloud to reload ────────────────────────────────

    @task
    def oracle_reload(upload_result: dict):
        """
        POST to the Galaxy FastAPI admin endpoint on Oracle Cloud.
        This triggers Weaviate upsert + cache invalidation.
        """
        import httpx

        reload_url = Variable.get("ORACLE_RELOAD_URL", "http://localhost:8000/api/admin/reload")
        admin_token = Variable.get("ADMIN_TOKEN", "changeme")
        s3_path = upload_result["s3_path"]

        try:
            resp = httpx.post(
                reload_url,
                json={"parquet_s3_path": s3_path},
                headers={"X-Admin-Token": admin_token},
                timeout=120,
            )
            resp.raise_for_status()
            print(f"Oracle reload triggered: {resp.json()}")
        except Exception as e:
            print(f"Oracle reload failed (non-fatal): {e}")
            # Don't fail the DAG if the reload fails — pipeline completed successfully

    # ── Wire it together ──────────────────────────────────────────────────────

    trained = training_job.output
    gated = mlflow_quality_gate(trained)
    uploaded = upload_artifacts(gated)

    # Feast and Oracle reload can run in parallel after upload
    feast_materialize(uploaded)
    oracle_reload(uploaded)


training_pipeline_dag()
