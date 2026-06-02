# YouTube Galaxy MLOps

A production MLOps pipeline for visualizing and querying 20,000+ YouTube creator profiles. Built as a hands-on learning project for 6 MLOps tools.

Live at **spookypharaoh.com** (once deployed):
- **Galaxy** — 3D creator cluster visualization with live rankings
- **Chat** — RAG chatbot that answers questions about the creator data
- **Rankings** *(placeholder — Phase 2)* — leaderboard pages for creator categories such as Most Controversial, Most Views, Rising Stars, Randomly Selected, and Newest Added. Currently a placeholder tab in the app; the ranking signals will be derived from Fandom data and bio-text sentiment without any external APIs

---

## How this repo is structured

The repo has two separate layers that connect to each other:

```
youtube-galaxy-mlops/
├── learn/          ← START HERE. Self-contained tutorials for each tool.
│   ├── 01-kubernetes/
│   ├── 02-airflow/
│   ├── 03-terraform/
│   ├── 04-mlflow/
│   ├── 05-feast/
│   └── 06-weaviate/
│
└── (everything else) ← The real implementation. Use this AFTER learn/.
    ├── infra/          Terraform — Oracle Cloud provisioning
    ├── k8s/            Kubernetes manifests and Helm values
    ├── dags/           Airflow DAGs
    ├── training/       ML training container (KMeans + UMAP + MLflow)
    ├── serving/        FastAPI chatbot + embedding microservice
    ├── features/       Feast feature store definitions
    ├── scrapers/       Fandom wiki scraper container
    ├── frontend/       Streamlit visualization app
    └── scripts/        Operational utilities
```

**The connection:** every `learn/` module ends with a "How this maps to the Galaxy project" section that points you at the exact file to read next. You learn the tool in isolation, then see it applied in the real codebase.

---

## Prerequisites

Install these before starting:

```bash
# macOS
brew install k3d kubectl helm terraform

# Python (use conda or venv per module — each learn/ folder has its own requirements)
python --version   # needs 3.11+

# Docker Desktop (required for k3d)
# https://docs.docker.com/desktop/install/mac-install/

# Optional: GPU support (desktop only)
# Install NVIDIA Container Toolkit if using COMPUTE_BACKEND=gpu
```

---

## Machine compatibility

This repo runs on two machines with different capabilities:

| Setting | Desktop (RTX 3080) | MacBook M1 |
|---|---|---|
| `COMPUTE_BACKEND` | `gpu` | `cpu` |
| `LLM_BACKEND` | `ollama` | `groq` |
| k3d config | `k3d-gpu.yaml` | `k3d-cpu.yaml` |
| Training speed | ~5–10 min (GPU) | 2+ hours (CPU) |
| Local LLM | Mistral 7B Q8 in k3d pod | Groq free API |

On M1, use `--sample 2000` flag with `train.py` for quick dev iterations instead of the full 20K creator dataset.

Production (Oracle Cloud) always uses `COMPUTE_BACKEND` = N/A, `LLM_BACKEND=groq`.

---

## Learning sequence

Work through these in order. Each step is independently verifiable before moving on.

### Phase 1: Learn the tools (start here)

| Step | Module | What you practice |
|---|---|---|
| 1 | [learn/01-kubernetes/](learn/01-kubernetes/README.md) | Pods, deployments, services, Jobs, Helm, GPU resource requests |
| 2 | [learn/02-airflow/](learn/02-airflow/airflow_intro.ipynb) | DAGs, operators, XCom, scheduling, TaskFlow API |
| 3 | [learn/03-terraform/](learn/03-terraform/README.md) | Providers, resources, variables, state, modules |
| 4 | [learn/04-mlflow/](learn/04-mlflow/mlflow_intro.ipynb) | Experiment tracking, model registry, quality gates |
| 5 | [learn/05-feast/](learn/05-feast/feast_intro.ipynb) | Feature views, materialization, offline/online stores |
| 6 | [learn/06-weaviate/](learn/06-weaviate/weaviate_intro.ipynb) | Vector search, hybrid search, RAG pipeline |

### Phase 2: Build the real project (after learn/)

Follow this order — each step depends on the previous ones being in place.

**Step 1 — Terraform: provision Oracle Cloud**
```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
# fill in your Oracle Cloud credentials
terraform -chdir=infra init
terraform -chdir=infra apply
# Output: server_public_ip → add as A record in Hostinger for spookypharaoh.com
```
Files: [`infra/`](infra/)

**Step 2 — Kubernetes: start local cluster and deploy base services**
```bash
COMPUTE_BACKEND=cpu ./scripts/start_local.sh   # or COMPUTE_BACKEND=gpu on desktop
make install-mlflow
make install-weaviate
make install-redis
```
Files: [`k8s/`](k8s/), [`k3d-cpu.yaml`](k3d-cpu.yaml), [`k3d-gpu.yaml`](k3d-gpu.yaml)

**Step 3 — MLflow: verify experiment tracking works**
```bash
make forward-mlflow   # opens http://localhost:5000
# Run a quick test: python -c "import mlflow; mlflow.set_tracking_uri('http://localhost:5000'); mlflow.log_metric('test', 1)"
```
Files: [`k8s/mlflow/deployment.yaml`](k8s/mlflow/deployment.yaml), [`training/train.py`](training/train.py) (see MLflow calls)

**Step 4 — Training container: build and run locally**
```bash
# First: copy the scraper from the existing repo
cp ../Controversy-Early-Warning-System/src/scrapers/fandom/my_combined.py scrapers/fandom/

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

**Step 5 — Weaviate + chatbot: load data and verify RAG**
```bash
make build-embedding
kubectl apply -f k8s/embedding-service/ -n galaxy-serving
make forward-weaviate   # http://localhost:8081

# Load existing Parquet into Weaviate (uses the starmap from the old repo)
make load-weaviate PARQUET_PATH=../Youtube-Galaxy-Streamlit-App/data/processed/plotly/starmap_data.parquet

# Test the chatbot
make build-chatbot
kubectl apply -f k8s/chatbot-api/ -n galaxy-serving
curl -X POST http://localhost:8000/chat/query -d '{"question": "who is similar to MrBeast"}'
```
Files: [`serving/chatbot_api/`](serving/chatbot_api/), [`serving/embedding_service/`](serving/embedding_service/), [`scripts/load_weaviate.py`](scripts/load_weaviate.py)

**Step 6 — Feast: wire up feature store**
```bash
cd features
feast apply
feast materialize-incremental $(date -u +%Y-%m-%dT%H:%M:%S)
```
Files: [`features/`](features/)

**Step 7 — Airflow: automate the full pipeline**
```bash
make install-airflow
make forward-airflow   # http://localhost:8080

# Set Airflow Variables via UI or CLI:
# OCI_BUCKET, OCI_ENDPOINT_URL, OCI_ACCESS_KEY, OCI_SECRET_KEY
# ORACLE_RELOAD_URL, ADMIN_TOKEN, GROQ_API_KEY

# Test the pipeline end-to-end
make dag-test-train
```
Files: [`dags/`](dags/)

**Step 8 — Frontend: deploy and verify**
```bash
make build-frontend
kubectl apply -f k8s/frontend/ -n galaxy-serving
kubectl apply -f k8s/ingress/ingress.yaml -n galaxy-serving
# Visit https://spookypharaoh.com
```
Files: [`frontend/streamlit_app.py`](frontend/streamlit_app.py)

---

## Missing piece: copy the scraper

The `scrapers/fandom/my_combined.py` file is not in this repo — it lives in the original `Controversy-Early-Warning-System` repo. Copy it before building the scraper container:

```bash
cp ../Controversy-Early-Warning-System/src/scrapers/fandom/my_combined.py scrapers/fandom/
```

The `scrapers/Dockerfile` expects it at that path. Everything else is already here.

---

## Key environment variables

These are set as Airflow Variables (via the UI) and as Kubernetes Secrets. A `.env.example` is provided for local development.

| Variable | Where used | Example |
|---|---|---|
| `COMPUTE_BACKEND` | k3d, training Job | `gpu` or `cpu` |
| `LLM_BACKEND` | chatbot API | `ollama` or `groq` |
| `GROQ_API_KEY` | chatbot API | from groq.com free tier |
| `ADMIN_TOKEN` | reload endpoint | any secret string |
| `OCI_ENDPOINT_URL` | all OCI storage calls | `https://<ns>.compat.objectstorage.<region>.oraclecloud.com` |
| `OCI_ACCESS_KEY` | all OCI storage calls | Oracle customer secret |
| `OCI_SECRET_KEY` | all OCI storage calls | Oracle customer secret |
| `MLFLOW_URI` | training, Airflow DAGs | `http://mlflow.galaxy-pipeline:5000` |
| `WEAVIATE_URL` | chatbot, scripts | `http://weaviate.galaxy-serving` |
| `REDIS_URL` | embedding service, Feast | `redis://redis-master.galaxy-serving:6379` |

---

## Data pipeline (what happens end-to-end)

```
Every few days (Airflow cron):

  Fandom wiki
      ↓  scrapers/fandom/my_combined.py
  creators.json (20K+ profiles)
      ↓  training/train.py  (GPU k3s Job)
  embeddings.parquet  +  KMeans model  →  MLflow registry
      ↓  quality gate (silhouette ≥ 0.40)
  upload to Oracle Object Storage
      ↓  feast materialize
  Redis online store (fast feature serving)
      ↓  Weaviate upsert
  Vector index updated
      ↓  POST /api/admin/reload
  Streamlit cache invalidated → users see fresh galaxy
```

---

## Stretch goals (Phase 2)

Rankings derived from Fandom data only — no external APIs:
- **Newest Added** — sort by `scraped_at` timestamp
- **Cluster Highlights** — creator closest to each cluster centroid
- **Sentiment Drift** — DistilBERT on bio text snapshots over time (uses existing `data_analyzer.py`)
- **Content Shift** — creators whose embedding distance from centroid changed most between runs

Phase 2 requires storing historical bio-text snapshots (one Parquet per pipeline run, partitioned by date). The `features/feature_views.py` has placeholder comments for these views.

---

## Infrastructure cost

| Resource | Cost | Purpose |
|---|---|---|
| Oracle Cloud A1 Flex (4 OCPU, 24GB RAM) | **$0** always free | Runs k3s + all production services |
| Oracle Object Storage (20GB) | **$0** always free | Parquet artifacts, MLflow artifacts |
| Groq API | **$0** free tier | LLM for chatbot (14,400 req/day) |
| Local machine | already own | Training, local k3d development |
| **Total** | **$0/month** | |

Backup plan: Hetzner CX32 ($11/month) if Oracle free tier is unavailable.
