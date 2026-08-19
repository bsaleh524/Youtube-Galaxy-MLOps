# Learning Path: MLOps Tools

Work through each module in order before touching the main project code. Each module is self-contained — no dependencies on the others, no cloud credentials required.

## Why this order?

1. **Kubernetes** — everything runs inside K8s; understand it first, write manifests by hand
2. **Airflow** — orchestrates both pipelines; concepts depend on understanding containers and Jobs
3. **DuckDB** — the stats structured store; simpler than the ML tools, good confidence builder
4. **MLflow** — experiment tracking + quality gate; used by both training pipelines
5. **Weaviate** — vector DB + RAG; the most involved piece, saved for last

## What each module contains

- **Concepts section** — the "why" before the "how"
- **Working examples** — runnable code demonstrating core features
- **Exercises** — tasks to complete with increasing difficulty
- **Project preview** — how this tool maps to the Galaxy project specifically

## Local setup requirements

Each module lists its own requirements. In general you'll need:
- Python 3.11+
- Docker Desktop (for K8s, Weaviate)
- k3d: `brew install k3d` (or `curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash`)
- A conda/venv environment per module (requirements listed in each)

## Modules

| # | Tool | Format | Est. Time |
|---|---|---|---|
| 01 | [Kubernetes](01-kubernetes/) | README + YAML exercises | 2–3 hours |
| 02 | [Airflow](02-airflow/) | Jupyter notebook | 2–3 hours |
| 03 | [DuckDB](03-duckdb/) | README + Python exercises | 1–2 hours |
| 04 | [MLflow](04-mlflow/) | Jupyter notebook | 1–2 hours |
| 05 | [Weaviate](05-weaviate/) | Jupyter notebook | 2–3 hours |
