# archive/

The previous design of this project: a Kubernetes (k3d locally, Oracle Cloud VM in prod) stack with
Weaviate, Redis, DuckDB stats, Streamlit, Feast/Terraform experiments and Helm-installed Airflow/MLflow.
It was replaced in November 2026 by a $0/month design (local Airflow + MLflow, static Hostinger site,
free Cloudflare Worker). See the top-level README for the current architecture.

Kept for reference and learning. Nothing here is built, tested, or imported by the current code.
Do not delete.

| Path | What it was |
|---|---|
| `k3d/`, `k8s/` | Local cluster configs and Kubernetes manifests / Helm values (Airflow, MLflow, Weaviate, Redis, Ollama, ingress) |
| `learn/` | Tutorials and notebooks (Kubernetes, Airflow, DuckDB, MLflow, Weaviate); the bottom of `learn/README.md` explains why the plan changed |
| `training/` | GTE embedding + clustering training job and Kaggle stats job (Docker images for k8s Jobs) |
| `serving/` | FastAPI services: chatbot RAG API (Weaviate + Groq), embedding service (Redis cache), stats API (DuckDB) |
| `frontend/` | Streamlit app |
| `dags/` | The four Airflow 2.x DAGs that launched KubernetesPodOperator jobs (uses the deprecated MLflow stages API) |
| `quick/` | A docker-compose Weaviate quick-start (ingest, search, RAG chat) |
| `scripts/` | k3d start script and Weaviate loader |
| `scrapers/` | Dockerfile and k8s Job entrypoint that uploaded scrapes to Oracle Object Storage |
| `Makefile.old` | k3d/Helm/Terraform/Feast targets |
| `pyproject.old.toml` | Old dependency groups (`learn`, `training`, `quick`, `stats-api`, `chatbot-api`, `embedding-service`) |
