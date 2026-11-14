#!/usr/bin/env bash
# Local MLflow tracking server: sqlite backend + local artifact store, both under data/mlflow/.
# Default port 5001 because macOS AirPlay Receiver usually occupies :5000.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${MLFLOW_PORT:-5001}"
mkdir -p "$ROOT/data/mlflow/artifacts"
cd "$ROOT"
exec uv run --group pipeline mlflow server \
  --backend-store-uri "sqlite:///$ROOT/data/mlflow/mlflow.db" \
  --artifacts-destination "$ROOT/data/mlflow/artifacts" \
  --host 127.0.0.1 --port "$PORT"
