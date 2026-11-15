#!/usr/bin/env bash
# Create .venv-airflow with Airflow installed from its official constraints file.
# Airflow gets its own venv because its pins conflict with the ML stack in the main venv.
set -euo pipefail

AIRFLOW_VERSION="3.4.0"
PYTHON_VERSION="3.11"
VENV=".venv-airflow"
CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

cd "$(dirname "$0")/.."

if [ -x "$VENV/bin/airflow" ] && \
   [ "$("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("apache-airflow"))' 2>/dev/null)" = "$AIRFLOW_VERSION" ]; then
  echo "Airflow $AIRFLOW_VERSION already installed in $VENV — skipping."
  exit 0
fi

uv venv --python "$PYTHON_VERSION" "$VENV"
uv pip install --python "$VENV/bin/python" "apache-airflow==${AIRFLOW_VERSION}" --constraint "$CONSTRAINT_URL"
echo "Airflow $AIRFLOW_VERSION installed in $VENV."
