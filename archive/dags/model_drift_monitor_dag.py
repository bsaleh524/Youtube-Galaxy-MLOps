"""
DAG 3: model_drift_monitor_dag
Schedule: Monthly (1st of each month, 03:00 UTC)

Loads the Production K-Means model from MLflow, recomputes silhouette
score against recently scraped embeddings, and triggers a full retrain
if quality has degraded beyond a threshold.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import mlflow
import numpy as np
from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.operators.trigger_dagrun import TriggerDagRunOperator


DRIFT_THRESHOLD = 0.05   # retrain if silhouette dropped by more than this


@dag(
    dag_id="model_drift_monitor_dag",
    description="Monthly quality check — retrain if cluster quality has degraded",
    schedule="0 3 1 * *",   # 1st of each month, 03:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["galaxy", "monitoring"],
)
def model_drift_monitor_dag():

    @task
    def check_drift() -> dict:
        """
        1. Load the Production K-Means model from MLflow registry.
        2. Load a sample of recent embeddings (produced by the last training run).
        3. Re-cluster with the production model.
        4. Compute silhouette score and compare against the registered production score.
        """
        mlflow_uri = Variable.get("MLFLOW_URI", "http://mlflow.galaxy-pipeline:5000")
        mlflow.set_tracking_uri(mlflow_uri)
        client = mlflow.tracking.MlflowClient()

        # Load the production model
        try:
            model = mlflow.sklearn.load_model("models:/galaxy-kmeans/Production")
        except mlflow.exceptions.MlflowException as e:
            print(f"No Production model found: {e}. Skipping drift check.")
            return {"should_retrain": False, "reason": "no_production_model"}

        # Get the silhouette score logged with the current Production version
        prod_versions = client.get_latest_versions("galaxy-kmeans", stages=["Production"])
        if not prod_versions:
            return {"should_retrain": False, "reason": "no_production_version"}

        prod_run_id = prod_versions[0].run_id
        prod_run = client.get_run(prod_run_id)
        baseline_silhouette = prod_run.data.metrics.get("silhouette_score", 0.5)

        # Load recent embeddings from the latest features Parquet
        # In production: fetch from Oracle Object Storage
        features_path = Variable.get("OCI_FEATURES_PATH", "data/features/starmap_data.parquet")
        try:
            import pandas as pd
            df = pd.read_parquet(features_path)
            # Sample up to 5000 rows for faster computation
            sample = df.sample(min(5000, len(df)), random_state=42)
            # Reconstruct embeddings from x/y/z is not sufficient — we need the raw embeddings
            # In production, the full embedding Parquet (not the UMAP projection) is stored
            # For now, we use the UMAP coords as a proxy
            coords = sample[["x", "y", "z"]].values
        except Exception as e:
            print(f"Could not load features for drift check: {e}")
            return {"should_retrain": False, "reason": str(e)}

        # Predict with the production model (using UMAP coords as proxy)
        # In production: load the full 1024-dim embeddings and predict
        labels = model.predict(coords)
        from sklearn.metrics import silhouette_score
        current_silhouette = silhouette_score(coords, labels, sample_size=min(2000, len(coords)))

        drift = baseline_silhouette - current_silhouette
        should_retrain = drift >= DRIFT_THRESHOLD

        print(f"Drift check: baseline={baseline_silhouette:.4f}, "
              f"current={current_silhouette:.4f}, drift={drift:+.4f}")

        # Log drift to MLflow for tracking
        with mlflow.start_run(experiment_id=client.get_experiment_by_name("galaxy-production").experiment_id,
                               run_name="drift_check"):
            mlflow.log_metrics({
                "baseline_silhouette": baseline_silhouette,
                "current_silhouette": current_silhouette,
                "silhouette_drift": drift,
            })

        return {
            "should_retrain": should_retrain,
            "current_silhouette": current_silhouette,
            "baseline_silhouette": baseline_silhouette,
            "drift": drift,
        }

    @task.branch
    def route(drift_result: dict) -> str:
        if drift_result["should_retrain"]:
            print(f"Drift {drift_result['drift']:+.4f} exceeds threshold {DRIFT_THRESHOLD}. Triggering retrain.")
            return "trigger_retrain"
        print(f"Drift {drift_result['drift']:+.4f} within acceptable range. No action needed.")
        return "no_action"

    trigger_retrain = TriggerDagRunOperator(
        task_id="trigger_retrain",
        trigger_dag_id="training_pipeline_dag",
        conf={"triggered_by": "model_drift_monitor_dag"},
        reset_dag_run=True,
    )

    @task
    def no_action():
        print("Model quality is healthy. No retraining needed.")

    drift = check_drift()
    route(drift) >> [trigger_retrain, no_action()]


model_drift_monitor_dag()
