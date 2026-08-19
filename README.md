# YouTube Galaxy MLOps

A production MLOps pipeline for visualizing and querying 20,000+ YouTube creator profiles alongside stat-based archetypes from the Kaggle "Global YouTube Statistics 2023" dataset. Built as a hands-on learning project for 5 MLOps tools.

Live at **spookypharaoh.com** (once deployed):
- **Galaxy** — 3D creator cluster visualization built from content-similarity embeddings
- **Chat** — RAG chatbot that answers questions about the creator data
- **Stats** — stat-based archetype view: KMeans clusters on subscriber/view/upload counts, served from DuckDB

---

## Stack

| Tool | Role | Does NOT own |
|---|---|---|
| **Kubernetes** | Runtime for all always-on services and batch Jobs | Training compute scheduling (that's Airflow's job) |
| **Airflow** | DAG scheduling + task sequencing for both pipelines | Moving data (passes S3 URIs and file paths via XCom) |
| **MLflow** | Experiment metrics + model registry + quality gate | Model serving |
| **Weaviate** | Vector index + hybrid search + RAG retrieval | LLM inference |
| **DuckDB** | Structured store for Kaggle stats + archetype cluster labels | The embedding vectors (those live in Weaviate) |

Terraform and Feast were dropped. Terraform: provisioning is a one-time manual step on a single Oracle VM, not worth the IaC overhead. Feast: the stats/rankings model is a periodic batch job with the frontend reading the latest snapshot — no live per-request feature serving, so Feast adds complexity with no real use case.

---

## How this repo is structured

```
youtube-galaxy-mlops/
├── learn/          ← START HERE. Self-contained tutorials for each tool.
│   ├── 01-kubernetes/
│   ├── 02-airflow/
│   ├── 03-duckdb/
│   ├── 04-mlflow/
│   └── 05-weaviate/
│
└── (everything else) ← The real implementation. Use this AFTER learn/.
    ├── dags/           Airflow DAGs (two independent pipeline branches)
    ├── training/       ML training containers (embedding + stats clustering)
    ├── serving/        FastAPI chatbot, embedding service, stats API
    ├── frontend/       Streamlit app (Galaxy, Chat, Stats tabs)
    ├── k8s/            Kubernetes manifests and Helm values
    ├── scrapers/       Fandom wiki scraper container
    └── scripts/        Operational utilities
```

**The connection:** every `learn/` module ends with a "How this maps to the Galaxy project" section that points you at the exact file to read next.

---

## Prerequisites

```bash
# macOS
brew install k3d kubectl helm

# Python (use conda or venv per module — each learn/ folder has its own requirements)
python --version   # needs 3.11+

# Docker Desktop (required for k3d)
# https://docs.docker.com/desktop/install/mac-install/

# Optional: GPU support (desktop only)
# Install NVIDIA Container Toolkit if using COMPUTE_BACKEND=gpu
```

---

## Machine compatibility

| Setting | Desktop (RTX 3080) | MacBook M1 |
|---|---|---|
| `COMPUTE_BACKEND` | `gpu` | `cpu` |
| `LLM_BACKEND` | `ollama` | `groq` |
| k3d config | `k3d-gpu.yaml` | `k3d-cpu.yaml` |
| Training speed (embedding) | ~5–10 min (GPU) | 2+ hours (CPU) |
| Training speed (stats) | <2 min | <2 min |
| Local LLM | Mistral 7B Q8 in k3d pod | Groq free API |

On M1, use `--sample 2000` flag with `train.py` for quick dev iterations instead of the full 20K creator dataset.

Production (Oracle Cloud) always uses `COMPUTE_BACKEND=cpu`, `LLM_BACKEND=groq`.

---

## Learning sequence

Work through these in order. Each step is independently verifiable before moving on.

### Phase 1: Learn the tools (start here)

| Step | Module | What you practice |
|---|---|---|
| 1 | [learn/01-kubernetes/](learn/01-kubernetes/README.md) | Pods, deployments, services, Jobs, Helm, GPU resource requests — written by hand, no shortcuts |
| 2 | [learn/02-airflow/](learn/02-airflow/airflow_intro.ipynb) | DAGs, operators, XCom, scheduling, TaskFlow API |
| 3 | [learn/03-duckdb/](learn/03-duckdb/README.md) | Embedded OLAP store, analytics queries, PVC persistence in k8s |
| 4 | [learn/04-mlflow/](learn/04-mlflow/mlflow_intro.ipynb) | Experiment tracking, model registry, quality gates |
| 5 | [learn/05-weaviate/](learn/05-weaviate/weaviate_intro.ipynb) | Vector search, hybrid search, RAG pipeline |

### Phase 2: Build the real project (after learn/)

Both pipelines are independent and can run on different schedules. Build them in the order below so each step has what it needs.

---

**Step 1 — Kubernetes: start local cluster and deploy base services**
```bash
COMPUTE_BACKEND=cpu ./scripts/start_local.sh   # or COMPUTE_BACKEND=gpu on desktop
make install-airflow
make install-mlflow
make install-weaviate
make install-redis
```
Files: [`k8s/`](k8s/), [`k3d-cpu.yaml`](k3d-cpu.yaml), [`k3d-gpu.yaml`](k3d-gpu.yaml)

> **Why by hand:** prior K8s exposure was limited to running notebooks against a company-managed KubeFlow cluster — no hands-on experience writing Deployments, Services, or Helm charts. Write those here by hand rather than reaching for higher-level abstractions, even where a shortcut exists.

---

**Step 2 — Copy the Fandom scraper**
```bash
cp ../Controversy-Early-Warning-System/src/scrapers/fandom/my_combined.py scrapers/fandom/
```
`scrapers/Dockerfile` expects it at that path. Nothing else is needed.

---

**Step 3 — MLflow: verify experiment tracking**
```bash
make forward-mlflow   # opens http://localhost:5000
python -c "import mlflow; mlflow.set_tracking_uri('http://localhost:5000'); mlflow.log_metric('test', 1)"
```
Files: [`k8s/mlflow/deployment.yaml`](k8s/mlflow/deployment.yaml)

---

**Step 4 — Embedding training pipeline**
```bash
make build-training   # builds training/Dockerfile

# Test locally (CPU mode, small sample):
docker run --rm \
  -e INPUT_PATH=data/fandom/youtubers_data_combined.json \
  -e OUTPUT_PATH=data/features/starmap_data.parquet \
  -e MLFLOW_TRACKING_URI=http://localhost:5000 \
  -e N_CLUSTERS=120 \
  -v $(pwd)/data:/data \
  localhost:5000/galaxy-training:latest
```
Files: [`training/train.py`](training/train.py), [`training/Dockerfile`](training/Dockerfile)

---

**Step 5 — Stats pipeline (Kaggle dataset)**

Download the Kaggle "Global YouTube Statistics 2023" CSV and place it at:
```
data/kaggle/global_youtube_statistics.csv
```

Build and test the stats training container:
```bash
make build-stats-training   # builds training/train_stats.py

docker run --rm \
  -e KAGGLE_CSV_PATH=data/kaggle/global_youtube_statistics.csv \
  -e DUCKDB_PATH=data/youtube_stats.duckdb \
  -e MLFLOW_TRACKING_URI=http://localhost:5000 \
  -e N_CLUSTERS=20 \
  -v $(pwd)/data:/data \
  localhost:5000/galaxy-stats-training:latest
```

Deploy the stats API:
```bash
make build-stats-api
kubectl apply -f k8s/stats-api/ -n galaxy-serving
```
Files: [`training/train_stats.py`](training/train_stats.py), [`serving/stats_api/`](serving/stats_api/), [`k8s/stats-api/deployment.yaml`](k8s/stats-api/deployment.yaml)

---

**Step 6 — Weaviate + chatbot: load data and verify RAG**
```bash
make build-embedding
kubectl apply -f k8s/embedding-service/ -n galaxy-serving
make forward-weaviate   # http://localhost:8081

# Load Parquet into Weaviate
make load-weaviate PARQUET_PATH=data/features/starmap_data.parquet

# Test the chatbot
make build-chatbot
kubectl apply -f k8s/chatbot-api/ -n galaxy-serving
curl -X POST http://localhost:8000/chat/query -d '{"question": "who is similar to MrBeast"}'
```
Files: [`serving/chatbot_api/`](serving/chatbot_api/), [`serving/embedding_service/`](serving/embedding_service/)

---

**Step 7 — Airflow: automate both pipelines**
```bash
make forward-airflow   # http://localhost:8080

# Set Airflow Variables via UI or CLI:
# OCI_BUCKET, OCI_ENDPOINT_URL, OCI_ACCESS_KEY, OCI_SECRET_KEY
# ORACLE_RELOAD_URL, ADMIN_TOKEN, GROQ_API_KEY
# KAGGLE_CSV_PATH (OCI path to the Kaggle CSV)

# Test pipelines end-to-end
make dag-test-train
make dag-test-stats
```
Files: [`dags/training_pipeline_dag.py`](dags/training_pipeline_dag.py), [`dags/stats_pipeline_dag.py`](dags/stats_pipeline_dag.py)

---

**Step 8 — Frontend: deploy and verify**
```bash
make build-frontend
kubectl apply -f k8s/frontend/ -n galaxy-serving
kubectl apply -f k8s/ingress/ingress.yaml -n galaxy-serving
# Visit https://spookypharaoh.com
```
Files: [`frontend/streamlit_app.py`](frontend/streamlit_app.py)

---

## Data pipelines

Two independent branches, both scheduled Wednesday 02:00 UTC:

```
── Branch 1: Fandom embedding pipeline ──────────────────────────────

  Fandom wiki
      ↓  scrapers/fandom/my_combined.py  (Airflow-triggered k8s Job)
  creators.json (20K+ profiles) → Oracle Object Storage
      ↓  training/train.py  (k8s Job — GPU/CPU depending on COMPUTE_BACKEND)
  GTE-Large-v1.5 embeddings → KMeans (120 clusters) + UMAP 3D
      ↓  quality gate: silhouette ≥ 0.40 (MLflow)
  starmap.parquet → Oracle Object Storage
      ↓  POST /api/admin/reload
  Weaviate index updated → Streamlit cache flushed


── Branch 2: Kaggle stats pipeline ──────────────────────────────────

  Kaggle CSV (static snapshot, re-ingested each run)
      ↓  training/train_stats.py  (k8s Job)
  Normalise + log-scale subscriber/view/upload counts
  KMeans (~20 stat-based archetype clusters)
      ↓  quality gate: silhouette ≥ 0.30 (MLflow)
  Cluster labels → DuckDB file on PVC (serving/stats_api reads from here)
      ↓  POST /api/admin/reload
  Streamlit Stats tab cache flushed
```

Both branches call the same `/api/admin/reload` endpoint pattern. The Fandom branch hits the chatbot-api service; the stats branch hits the stats-api service.

---

## Key environment variables

Set as Airflow Variables and Kubernetes Secrets. A `.env.example` is at `quick/.env.example`.

| Variable | Where used | Example |
|---|---|---|
| `COMPUTE_BACKEND` | k3d config, training Job | `gpu` or `cpu` |
| `LLM_BACKEND` | chatbot API | `ollama` or `groq` |
| `GROQ_API_KEY` | chatbot API | from groq.com free tier |
| `ADMIN_TOKEN` | reload endpoints | any secret string |
| `OCI_ENDPOINT_URL` | all OCI storage calls | `https://<ns>.compat.objectstorage.<region>.oraclecloud.com` |
| `OCI_ACCESS_KEY` | all OCI storage calls | Oracle customer secret key |
| `OCI_SECRET_KEY` | all OCI storage calls | Oracle customer secret |
| `MLFLOW_URI` | training, Airflow DAGs | `http://mlflow.galaxy-pipeline:5000` |
| `WEAVIATE_URL` | chatbot, scripts | `http://weaviate.galaxy-serving` |
| `REDIS_URL` | embedding service | `redis://redis-master.galaxy-serving:6379` |
| `KAGGLE_CSV_PATH` | stats pipeline | OCI path or local path to the CSV |

---

## Infrastructure

Single Oracle Cloud A1 Flex VM (4 OCPU, 24GB RAM) — provisioned manually, one time.

| Resource | Cost | Purpose |
|---|---|---|
| Oracle Cloud A1 Flex | **$0** always free | Runs k3s + all production services |
| Oracle Object Storage (20GB) | **$0** always free | Parquet artifacts, MLflow artifacts |
| Groq API | **$0** free tier | LLM for chatbot (14,400 req/day) |
| Local machine | already own | Training, local k3d development |
| **Total** | **$0/month** | |

Backup plan: Hetzner CX32 ($11/month) if Oracle free tier is unavailable.

---

## Phase 2 stretch goals

*(Not started. Requires historical snapshots per pipeline run.)*

- **Sentiment drift** — DistilBERT on bio-text snapshots over time (requires storing one Parquet per run, partitioned by date)
- **Content shift** — creators whose embedding distance from cluster centroid changed most between runs
- **Cluster highlights** — creator closest to each cluster centroid, updated each run
