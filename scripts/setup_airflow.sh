#!/usr/bin/env bash
# Create .venv-airflow with Apache Airflow installed against the official constraints file.
# Airflow is kept out of the main uv environment because its pins conflict with the ML stack;
# DAG tasks shell out to `uv run --group pipeline python -m pipeline.<step>` instead.
set -euo pipefail

AIRFLOW_VERSION="${AIRFLOW_VERSION:-3.4.0}"
PYTHON_VERSION="3.11"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv-airflow"
CONSTRAINTS="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

if [ -x "$VENV/bin/airflow" ] && "$VENV/bin/airflow" version 2>/dev/null | grep -q "^${AIRFLOW_VERSION}$"; then
  echo "Airflow ${AIRFLOW_VERSION} already installed in .venv-airflow"
  exit 0
fi

echo "Creating .venv-airflow (Airflow ${AIRFLOW_VERSION}, Python ${PYTHON_VERSION})"
uv venv --python "$PYTHON_VERSION" "$VENV"
uv pip install --python "$VENV/bin/python" \
  "apache-airflow==${AIRFLOW_VERSION}" \
  --constraint "$CONSTRAINTS"
echo "Done. Start it with: make airflow"
