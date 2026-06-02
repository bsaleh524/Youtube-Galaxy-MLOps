"""
Galaxy MLOps Training Job
Runs as a Kubernetes Job (GPU on desktop, CPU on M1/Oracle).

Environment variables:
  INPUT_PATH            Path to creator JSON (local path or s3:// URI)
  OUTPUT_PATH           Where to write the Parquet output
  MLFLOW_TRACKING_URI   MLflow server URI
  N_CLUSTERS            Number of KMeans clusters (default: 120)
  OCI_ENDPOINT_URL      Oracle Object Storage S3-compat endpoint (omit for local)
  OCI_ACCESS_KEY        OCI customer secret access key
  OCI_SECRET_KEY        OCI customer secret secret key

Writes to /airflow/xcom/return.json (for KubernetesPodOperator XCom):
  {"mlflow_run_id": "...", "silhouette_score": 0.47, "output_path": "..."}
"""

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import davies_bouldin_score, silhouette_score
from umap import UMAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── Device detection ──────────────────────────────────────────────────────────

def get_device() -> str:
    if torch.cuda.is_available():
        log.info("CUDA GPU detected")
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        log.info("Apple MPS detected")
        return "mps"
    log.info("Using CPU (no GPU available)")
    return "cpu"


# ── Storage helpers (local file or Oracle Object Storage via S3-compat API) ───

def _s3_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=os.environ["OCI_ENDPOINT_URL"],
        aws_access_key_id=os.environ["OCI_ACCESS_KEY"],
        aws_secret_access_key=os.environ["OCI_SECRET_KEY"],
    )


def load_creators(input_path: str) -> list[dict]:
    """Load creator JSON from local path or s3:// URI."""
    if input_path.startswith("s3://"):
        parts = input_path[5:].split("/", 1)
        bucket, key = parts[0], parts[1]
        log.info(f"Downloading s3://{bucket}/{key}")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            _s3_client().download_file(bucket, key, f.name)
            tmp = f.name
        with open(tmp) as f:
            return json.load(f)
    else:
        log.info(f"Loading local file: {input_path}")
        with open(input_path) as f:
            return json.load(f)


def save_parquet(df: pd.DataFrame, output_path: str) -> str:
    """Save Parquet to local path or upload to s3:// URI. Returns local path."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        local_path = f.name
    df.to_parquet(local_path, index=False, engine="pyarrow")
    log.info(f"Saved Parquet ({len(df):,} rows) to {local_path}")

    if output_path.startswith("s3://"):
        parts = output_path[5:].split("/", 1)
        bucket, key = parts[0], parts[1]
        _s3_client().upload_file(local_path, bucket, key)
        log.info(f"Uploaded to s3://{bucket}/{key}")
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(local_path, output_path)
        log.info(f"Saved to {output_path}")

    return local_path


# ── Core ML pipeline ─────────────────────────────────────────────────────────

def embed_creators(
    creators: list[dict],
    model_name: str,
    device: str,
    batch_size: int = 4,
) -> np.ndarray:
    log.info(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name, trust_remote_code=True, device=device)

    # Same text format as the original starmap_builder.py
    texts = [f"{c['title']} - {c.get('description', '')[:32000]}" for c in creators]
    log.info(f"Embedding {len(texts):,} creators on {device}...")

    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        device=device,
        normalize_embeddings=True,
    )
    log.info(f"Embeddings shape: {embeddings.shape}")
    return embeddings


def cluster_and_project(
    embeddings: np.ndarray,
    n_clusters: int,
) -> tuple[np.ndarray, np.ndarray, KMeans]:
    log.info(f"Running KMeans with n_clusters={n_clusters}...")
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)

    log.info("Running UMAP for 3D projection...")
    reducer = UMAP(
        n_components=3,
        n_neighbors=30,
        min_dist=0.1,
        metric="cosine",
        random_state=42,
    )
    coords = reducer.fit_transform(embeddings)
    return labels, coords, kmeans


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    input_path = os.environ["INPUT_PATH"]
    output_path = os.environ["OUTPUT_PATH"]
    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    n_clusters = int(os.environ.get("N_CLUSTERS", "120"))
    model_name = os.environ.get("EMBEDDING_MODEL", "Alibaba-NLP/gte-large-en-v1.5")
    device = get_device()

    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment("galaxy-production")

    with mlflow.start_run() as run:
        run_id = run.info.run_id
        log.info(f"MLflow run: {run_id}")

        mlflow.log_params({
            "n_clusters": n_clusters,
            "embedding_model": model_name,
            "device": device,
            "umap_n_neighbors": 30,
            "umap_min_dist": 0.1,
            "umap_metric": "cosine",
        })

        # Load
        creators = load_creators(input_path)
        mlflow.log_metric("creator_count", len(creators))
        log.info(f"Loaded {len(creators):,} creators")

        # Embed
        embeddings = embed_creators(creators, model_name, device)

        # Cluster + project
        labels, coords, kmeans = cluster_and_project(embeddings, n_clusters)

        # Metrics
        sample_size = min(5000, len(embeddings))
        sil = silhouette_score(embeddings, labels, sample_size=sample_size, random_state=42)
        db = davies_bouldin_score(embeddings, labels)
        mlflow.log_metrics({"silhouette_score": sil, "davies_bouldin_score": db})
        log.info(f"Silhouette: {sil:.4f}  Davies-Bouldin: {db:.4f}")

        # Build output DataFrame
        df = pd.DataFrame([
            {
                "creator_id": c["id"],
                "title": c["title"],
                "description": c.get("description", "")[:500] + ("..." if len(c.get("description", "")) > 500 else ""),
                "thumbnail": c.get("thumbnail", ""),
                "youtube_url": c.get("youtube_url", ""),
                "cluster_id": int(labels[i]),
                "cluster_name": "",  # populated by a separate labeling step
                "x": float(coords[i, 0]),
                "y": float(coords[i, 1]),
                "z": float(coords[i, 2]),
            }
            for i, c in enumerate(creators)
        ])

        # Save Parquet
        local_path = save_parquet(df, output_path)

        # Log model and Parquet as artifacts
        mlflow.log_artifact(local_path, artifact_path="parquet")
        mlflow.sklearn.log_model(
            kmeans,
            artifact_path="kmeans_model",
            registered_model_name="galaxy-kmeans",
        )

        # Write XCom output for Airflow KubernetesPodOperator
        xcom_path = Path("/airflow/xcom/return.json")
        xcom_path.parent.mkdir(parents=True, exist_ok=True)
        xcom_path.write_text(json.dumps({
            "mlflow_run_id": run_id,
            "silhouette_score": sil,
            "output_path": output_path,
            "creator_count": len(creators),
        }))

        log.info(f"Training complete. Silhouette={sil:.4f}")
        return sil


if __name__ == "__main__":
    score = main()
    sys.exit(0 if score >= 0.35 else 1)
