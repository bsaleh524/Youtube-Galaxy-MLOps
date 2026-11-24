# Archive

The previous design of this repo, kept on purpose. Nothing here is used by the current build.

| Path | What it was |
|---|---|
| `k3d/` | Local k3d cluster configs (CPU/GPU variants) |
| `k8s/` | Kubernetes manifests and Helm values: Airflow, MLflow, Weaviate, Redis, Ollama, stats/chatbot APIs, ingress |
| `learn/` | Hands-on tutorials for Kubernetes, Airflow, DuckDB, MLflow and Weaviate |
| `training/` | Containerised embedding/clustering training job and the Kaggle stats job |
| `serving/` | FastAPI services: chatbot API (RAG over Weaviate), embedding service (Redis cache), stats API (DuckDB) |
| `frontend/` | Streamlit galaxy app and its Dockerfile |
| `dags/` | The four old Airflow DAGs (scrape, training, stats, drift monitor; Kubernetes-pod based) |
| `quick/` | A docker-compose quick-start: ingest into Weaviate, search, RAG chat |
| `scripts/` | Old helpers (load Weaviate, start the local cluster) |
| `scrapers/` | The scraper's Kubernetes Job entry point and Dockerfile (uploaded to Oracle Object Storage) |
| `Makefile.old` | k3d/Helm/Terraform/Feast/Weaviate targets |
| `pyproject.old.toml` | The old per-service dependency groups |

## Why it was archived

The original plan ran everything on Kubernetes on an Oracle Cloud VM, with Weaviate, Redis, DuckDB and Streamlit as long-running services. For ~20.8K creators that change slowly, that was all cost and upkeep. The project moved to:

- a **local pipeline** (Airflow + MLflow on the owner's machine)
- **static files** on Hostinger
- **one free Cloudflare Worker** for chat

See the root [`README.md`](../README.md). The original architecture and the reasons it changed are also written up at the bottom of [`learn/README.md`](learn/README.md).
