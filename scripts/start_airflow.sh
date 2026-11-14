#!/usr/bin/env bash
# Run Airflow locally with `airflow standalone` (scheduler + API server + UI on :8080, sqlite).
# State lives in .airflow/ (gitignored); DAGs are read straight from ./dags.
# The admin password is printed on first start and saved in .airflow/simple_auth_manager_passwords.json.generated
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export AIRFLOW_HOME="$ROOT/.airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$ROOT/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export GALAXY_REPO_ROOT="$ROOT"
mkdir -p "$AIRFLOW_HOME"

if [ ! -x "$ROOT/.venv-airflow/bin/airflow" ]; then
  echo "Airflow venv missing. Run: make setup" >&2
  exit 1
fi
exec "$ROOT/.venv-airflow/bin/airflow" standalone
