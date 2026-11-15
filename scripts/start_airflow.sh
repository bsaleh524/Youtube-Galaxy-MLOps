#!/usr/bin/env bash
# Run Airflow locally (API server + scheduler + dag processor + triggerer) with SQLite.
# The admin password is printed on first start and saved in
# data/airflow/simple_auth_manager_passwords.json.generated
set -euo pipefail
cd "$(dirname "$0")/.."

export AIRFLOW_HOME="$PWD/data/airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
mkdir -p "$AIRFLOW_HOME"
exec .venv-airflow/bin/airflow standalone
