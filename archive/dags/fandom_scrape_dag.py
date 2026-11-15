"""
DAG 1: fandom_scrape_dag
Schedule: Weekly, Sunday 01:00 UTC

Runs the Fandom wiki scraper as a Kubernetes Job, uploads the output
to Oracle Object Storage, and triggers training_pipeline_dag if a
meaningful number of new creators were found.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from kubernetes.client import models as k8s


NAMESPACE = "galaxy-pipeline"
REGISTRY = os.getenv("CONTAINER_REGISTRY", "localhost:5000")
NEW_CREATOR_THRESHOLD = 100  # trigger training only if this many new creators


@dag(
    dag_id="fandom_scrape_dag",
    description="Scrape Fandom wiki for YouTube creator profiles",
    schedule="0 1 * * 0",   # Sunday 01:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["galaxy", "scraping"],
)
def fandom_scrape_dag():

    # ── Step 1: Run the scraper as a Kubernetes Job ──────────────────────────

    scrape_job = KubernetesPodOperator(
        task_id="scrape_fandom",
        name="galaxy-scrape-job",
        namespace=NAMESPACE,
        image=f"{REGISTRY}/galaxy-scraper:latest",
        cmds=["bash", "run.sh"],
        env_vars={
            "OUTPUT_BUCKET": Variable.get("OCI_BUCKET", "galaxy-artifacts"),
            "OUTPUT_PREFIX": "raw/fandom",
            "OCI_ENDPOINT_URL": Variable.get("OCI_ENDPOINT_URL", ""),
            "OCI_ACCESS_KEY": Variable.get("OCI_ACCESS_KEY", ""),
            "OCI_SECRET_KEY": Variable.get("OCI_SECRET_KEY", ""),
        },
        container_resources=k8s.V1ResourceRequirements(
            requests={"memory": "2Gi", "cpu": "500m"},
            limits={"memory": "4Gi", "cpu": "1"},
        ),
        is_delete_operator_pod=True,
        get_logs=True,
        do_xcom_push=True,  # scraper writes {"s3_path": ..., "creator_count": ...} to /airflow/xcom/return.json
    )

    # ── Step 2: Check how many new creators were found ───────────────────────

    @task
    def check_new_creators(scrape_output: dict) -> dict:
        """
        Compare the new creator count against what was last stored.
        Returns a dict with new_count and whether training should be triggered.
        """
        new_count = scrape_output.get("creator_count", 0)
        s3_path = scrape_output.get("s3_path", "")

        # In production, compare against the count stored in Airflow Variables
        last_count = int(Variable.get("last_creator_count", default_var=0))
        delta = new_count - last_count

        print(f"Creator count: {new_count} (was {last_count}, delta={delta:+d})")

        # Update the stored count
        Variable.set("last_creator_count", new_count)

        return {
            "s3_path": s3_path,
            "new_count": new_count,
            "delta": delta,
            "should_train": delta >= NEW_CREATOR_THRESHOLD,
        }

    # ── Step 3: Conditionally trigger training ───────────────────────────────

    @task.branch
    def route(check_result: dict) -> str:
        return "trigger_training" if check_result["should_train"] else "skip"

    trigger_training = TriggerDagRunOperator(
        task_id="trigger_training",
        trigger_dag_id="training_pipeline_dag",
        conf={"triggered_by": "fandom_scrape_dag"},
        reset_dag_run=True,
    )

    @task
    def skip():
        print(f"Not enough new creators to trigger training. "
              f"Threshold is {NEW_CREATOR_THRESHOLD}.")

    # ── Wire it together ─────────────────────────────────────────────────────

    scraped = scrape_job.output
    checked = check_new_creators(scraped)
    route(checked) >> [trigger_training, skip()]


fandom_scrape_dag()
