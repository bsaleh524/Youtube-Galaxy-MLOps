# YouTube Galaxy MLOps — AI Context

> For human-readable docs, workflow, and setup instructions see [README.md](README.md).

## What this project is

Operationalizes two existing repos into a production MLOps pipeline:
- `../Controversy-Early-Warning-System/` — Fandom wiki scraper (`my_combined.py`)
- `../Youtube-Galaxy-Streamlit-App/` — 3D galaxy visualization (reference for embedding/clustering logic)

New repo adds: scheduling, experiment tracking, feature store, vector DB, RAG chatbot, IaC.

## Tools and their exact responsibilities

| Tool | Owns | Does NOT own |
|---|---|---|
| Terraform | Oracle Cloud infra (instance, storage, network) | What runs inside k3s |
| Kubernetes | Runtime for all always-on services | Training compute (that's a Job) |
| Airflow | DAG scheduling + task sequencing | Moving data (passes S3 URIs via XCom) |
| MLflow | Experiment metrics + model registry + quality gate | Model serving |
| Feast | Feature definitions + offline→online materialization | The embeddings themselves (those are in Weaviate) |
| Weaviate | Vector index + semantic search + RAG retrieval | LLM inference |

## Key file locations

```
training/train.py              — refactored starmap_builder.py; reads S3, writes S3, logs MLflow
dags/training_pipeline_dag.py  — main pipeline DAG; wires all tools together
serving/chatbot_api/rag_pipeline.py — Weaviate hybrid search + prompt assembly + Groq/Ollama
features/feature_views.py      — Feast entity + feature view definitions
infra/modules/oracle/          — all Terraform resources
k8s/                           — Helm values and manifests per service
```

## Multi-machine flags

```
COMPUTE_BACKEND=gpu   → training Job requests nvidia.com/gpu: 1 (desktop only)
COMPUTE_BACKEND=cpu   → no GPU request (M1, Oracle ARM)
LLM_BACKEND=ollama    → chatbot calls ollama-service:11434 (desktop only)
LLM_BACKEND=groq      → chatbot calls Groq API (M1, Oracle Cloud)
```

## Important constraints

- **No YouTube API** — all data from Fandom wiki only
- **Rankings are Phase 2** — `feature_views.py` has placeholder comments for ranking views
- **`scrapers/fandom/my_combined.py` must be manually copied** from `../Controversy-Early-Warning-System/src/scrapers/fandom/` — it is not committed here
- **Oracle Always Free** is the production target; Hetzner CX32 ($11/month) is the fallback
- **SageMaker removed** — local 3080 handles all training

## XCom contract (Airflow ↔ training Job)

`training/train.py` writes to `/airflow/xcom/return.json`:
```json
{"mlflow_run_id": "...", "silhouette_score": 0.47, "output_path": "s3://...", "creator_count": 20807}
```

`dags/training_pipeline_dag.py` reads this via `KubernetesPodOperator.output`.

## Namespace layout

```
galaxy-pipeline  →  Airflow, MLflow, training Jobs
galaxy-serving   →  Weaviate, chatbot API, embedding service, Redis, Ollama, frontend
```
