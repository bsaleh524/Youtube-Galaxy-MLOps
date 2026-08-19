# YouTube Galaxy MLOps — AI Context

> For human-readable docs, workflow, and setup instructions see [README.md](README.md).

## What this project is

Operationalizes two existing repos into a production MLOps pipeline:
- `../Controversy-Early-Warning-System/` — Fandom wiki scraper (`my_combined.py`)
- `../Youtube-Galaxy-Streamlit-App/` — 3D galaxy visualization (reference for embedding/clustering logic)

New repo adds: scheduling, experiment tracking, vector DB, RAG chatbot, stat-based clustering, structured data store.

## Stack and tool responsibilities

| Tool | Owns | Does NOT own |
|---|---|---|
| Kubernetes | Runtime for all always-on services and batch Jobs | Scheduling (that's Airflow) |
| Airflow | DAG scheduling + task sequencing | Moving data (passes S3 URIs via XCom) |
| MLflow | Experiment metrics + model registry + quality gate | Model serving |
| Weaviate | Vector index + hybrid search + RAG retrieval | LLM inference |
| DuckDB | Structured store for Kaggle stats + archetype cluster labels | The embedding vectors (those are in Weaviate) |

**Removed from stack (do not add back):**
- **Feast** — dropped. No live per-request feature serving needed; batch snapshot + direct DB read is sufficient.
- **Terraform** — dropped. Single Oracle VM, one-time manual provisioning; IaC overhead not justified at this project size.

## Two independent pipeline branches

```
Branch 1 (Fandom embedding):
  fandom_scrape_dag → training_pipeline_dag
  → train.py: embed (GTE-Large-v1.5) + cluster (KMeans 120) + UMAP
  → quality gate: silhouette ≥ 0.40
  → starmap.parquet → Oracle Object Storage → Weaviate upsert

Branch 2 (Kaggle stats):
  stats_pipeline_dag
  → train_stats.py: KMeans on subscriber/view/upload counts (log-scaled)
  → quality gate: silhouette ≥ 0.30
  → DuckDB file on PVC → stats-api Deployment reads it
```

Both branches call `POST /api/admin/reload` on their respective service after a successful run.

## Key file locations

```
training/train.py              — embedding + clustering pipeline (reads Fandom JSON, writes starmap.parquet)
training/train_stats.py        — stats clustering pipeline (reads Kaggle CSV, writes to DuckDB)
dags/training_pipeline_dag.py  — Fandom embedding DAG
dags/stats_pipeline_dag.py     — Kaggle stats DAG
dags/fandom_scrape_dag.py      — Fandom scraping DAG (runs before training_pipeline_dag)
dags/model_drift_monitor_dag.py — monthly drift check
serving/chatbot_api/main.py    — FastAPI: RAG chat + /api/admin/reload for Weaviate
serving/chatbot_api/rag_pipeline.py — Weaviate hybrid search + prompt assembly + Groq/Ollama
serving/embedding_service/main.py  — FastAPI: GTE-Large-v1.5 embeddings with Redis cache
serving/stats_api/main.py      — FastAPI: DuckDB queries for Stats tab + /api/admin/reload
k8s/stats-api/deployment.yaml  — Deployment + PVC for DuckDB file + stats-api Service
frontend/streamlit_app.py      — Streamlit app: Galaxy tab, Chat tab, Stats tab
```

## Multi-machine flags

```
COMPUTE_BACKEND=gpu   → training Job requests nvidia.com/gpu: 1 (desktop RTX 3080 only)
COMPUTE_BACKEND=cpu   → no GPU request (M1 MacBook, Oracle ARM)
LLM_BACKEND=ollama    → chatbot calls ollama-service:11434 (desktop only)
LLM_BACKEND=groq      → chatbot calls Groq API (M1, Oracle Cloud)
```

## Important constraints

- **No YouTube API** — Fandom pipeline uses Fandom wiki only. Stats pipeline uses static Kaggle CSV.
- **Stats tab is now real** — it shows archetype clusters from `train_stats.py`, not a Phase 2 placeholder.
- **DuckDB file access pattern** — the training Job (batch, sequential) writes the file; the stats-api Deployment reads it (read_only=True). Never have both accessing it concurrently. The reload endpoint confirms the file is readable; no in-service writes happen.
- **`scrapers/fandom/my_combined.py` must be manually copied** from `../Controversy-Early-Warning-System/src/scrapers/fandom/` — it is not committed here.
- **Oracle Always Free** is the production target; Hetzner CX32 ($11/month) is the fallback.
- **Kubernetes manifests are written by hand** — this is intentional. Prior K8s exposure was KubeFlow-only (no hands-on with Deployments, Services, Helm values). Writing these manually is the point.

## XCom contracts (Airflow ↔ training Jobs)

`training/train.py` writes to `/airflow/xcom/return.json`:
```json
{"mlflow_run_id": "...", "silhouette_score": 0.47, "output_path": "s3://...", "creator_count": 20807}
```

`training/train_stats.py` writes to `/airflow/xcom/return.json`:
```json
{"mlflow_run_id": "...", "silhouette_score": 0.34, "row_count": 995}
```

## Namespace layout

```
galaxy-pipeline  →  Airflow, MLflow, training Jobs (both embedding and stats)
galaxy-serving   →  Weaviate, chatbot-api, embedding-service, stats-api, Redis, Ollama, frontend
```

## MLflow experiment names

```
galaxy-embedding-clustering  →  training/train.py runs
galaxy-stats-clustering      →  training/train_stats.py runs
```

## Quality gate thresholds

```
Embedding model (galaxy-kmeans):      silhouette ≥ 0.40
Stats model (galaxy-stats-kmeans):    silhouette ≥ 0.30  (lower — numeric clusters are noisier)
```
