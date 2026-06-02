# Learning Path: MLOps Tools

Work through each module in order before touching the main project code. Each module is self-contained — no dependencies on the others, no cloud credentials required until Terraform.

## Why this order?

1. **Kubernetes** — everything runs inside K8s, so understand it first
2. **Airflow** — orchestrates the pipeline; concepts depend on understanding containers
3. **Terraform** — provision infrastructure reproducibly before deploying anything real
4. **MLflow** — experiment tracking; easiest tool, great confidence builder
5. **Feast** — feature store; builds on understanding what "features" and "serving" mean
6. **Weaviate** — vector DB + RAG; the most exciting part, saved for last

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
- A conda/venv environment per module (requirements.txt provided in each)

## Modules

| # | Tool | Format | Est. Time |
|---|---|---|---|
| 01 | [Kubernetes](01-kubernetes/) | README + YAML exercises | 2–3 hours |
| 02 | [Airflow](02-airflow/) | Jupyter notebook | 2–3 hours |
| 03 | [Terraform](03-terraform/) | README + .tf exercises | 1–2 hours |
| 04 | [MLflow](04-mlflow/) | Jupyter notebook | 1–2 hours |
| 05 | [Feast](05-feast/) | Jupyter notebook | 2 hours |
| 06 | [Weaviate](06-weaviate/) | Jupyter notebook | 2–3 hours |
