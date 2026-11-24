#!/usr/bin/env bash
# Local MLflow tracking server: sqlite backend, artifacts on disk under data/mlflow.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${MLFLOW_PORT:-5001}"   # 5000 is taken by macOS AirPlay Receiver
mkdir -p data/mlflow/artifacts
exec uv run mlflow server \
  --backend-store-uri "sqlite:///data/mlflow/mlflow.db" \
  --default-artifact-root ./data/mlflow/artifacts \
  --host 127.0.0.1 --port "$PORT"
