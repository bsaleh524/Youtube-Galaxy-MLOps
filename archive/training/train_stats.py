"""
Stats clustering training job.

Reads the Kaggle "Global YouTube Statistics 2023" CSV, trains a KMeans model
on normalised subscriber/view/upload counts, writes cluster labels to DuckDB,
and logs the run to MLflow.

XCom output written to /airflow/xcom/return.json:
  {"mlflow_run_id": "...", "silhouette_score": 0.42, "row_count": 995}
"""

import json
import os
import sys

import duckdb
import mlflow
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


DUCKDB_PATH      = os.environ.get("DUCKDB_PATH", "/data/youtube_stats.duckdb")
KAGGLE_CSV_PATH  = os.environ.get("KAGGLE_CSV_PATH", "data/kaggle/global_youtube_statistics.csv")
MLFLOW_URI       = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow.galaxy-pipeline:5000")
N_CLUSTERS       = int(os.environ.get("N_CLUSTERS", "20"))
XCOM_PATH        = "/airflow/xcom/return.json"


def load_and_clean(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="latin-1")

    # Kaggle column names contain spaces and mixed capitalisation
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Core numeric features — drop rows with missing values in these
    feature_cols = ["subscribers", "video_views", "uploads"]
    df = df.dropna(subset=feature_cols).copy()

    # Coerce to numeric (some fields are stored as strings with commas)
    for col in feature_cols:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    df = df.dropna(subset=feature_cols)

    # Log-scale to tame the power-law distribution
    for col in feature_cols:
        df[f"{col}_log"] = np.log1p(df[col].clip(lower=0))

    return df


def train(df: pd.DataFrame) -> tuple[KMeans, float, np.ndarray]:
    feature_cols = ["subscribers_log", "video_views_log", "uploads_log"]
    X = df[feature_cols].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
    labels = model.fit_predict(X_scaled)
    score = silhouette_score(X_scaled, labels, sample_size=min(len(df), 500))

    return model, score, labels


def write_to_duckdb(df: pd.DataFrame, labels: np.ndarray) -> None:
    df = df.copy()
    df["stat_cluster_id"] = labels.astype(int)

    con = duckdb.connect(DUCKDB_PATH)
    con.execute("DROP TABLE IF EXISTS creator_stats")
    con.execute("""
        CREATE TABLE creator_stats AS
        SELECT
            youtuber        AS youtuber_name,
            subscribers,
            video_views,
            uploads,
            category,
            "country"       AS country,
            stat_cluster_id
        FROM df
    """)

    row_count = con.execute("SELECT COUNT(*) FROM creator_stats").fetchone()[0]
    print(f"[duckdb] wrote {row_count} rows to {DUCKDB_PATH}")
    con.close()


def main() -> None:
    mlflow.set_tracking_uri(MLFLOW_URI)

    with mlflow.start_run(experiment_id=mlflow.set_experiment("galaxy-stats-clustering").experiment_id) as run:
        mlflow.log_param("n_clusters", N_CLUSTERS)
        mlflow.log_param("features", "subscribers_log,video_views_log,uploads_log")

        df = load_and_clean(KAGGLE_CSV_PATH)
        print(f"Loaded {len(df)} rows from {KAGGLE_CSV_PATH}")

        model, silhouette, labels = train(df)
        mlflow.log_metric("silhouette_score", silhouette)
        print(f"silhouette_score={silhouette:.4f}")

        # Register model
        mlflow.sklearn.log_model(model, "stats-kmeans", registered_model_name="galaxy-stats-kmeans")

        write_to_duckdb(df, labels)

        # Write XCom result for Airflow
        result = {
            "mlflow_run_id":   run.info.run_id,
            "silhouette_score": silhouette,
            "row_count":       int(len(df)),
        }
        os.makedirs(os.path.dirname(XCOM_PATH), exist_ok=True)
        with open(XCOM_PATH, "w") as f:
            json.dump(result, f)

        print(f"Done. {result}")


if __name__ == "__main__":
    main()
