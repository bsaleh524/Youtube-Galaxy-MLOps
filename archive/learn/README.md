# Learning Path: MLOps Tools

> **ARCHIVED.** This folder is the learning material from the *original* plan for this project, kept as-is for reference. The project has since been simplified (see "Original architecture" and "Why it changed" at the bottom). Kubernetes, and the manifests in `../k8s/` and `../k3d/`, are no longer part of the plan. The Airflow, MLflow and DuckDB modules still apply to the new design. Weaviate was replaced by a serverless/embedded vector store.

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

---

## Original architecture (the plan this folder was written for)

The original goal was a production-style MLOps stack, built by hand to learn five tools: **Kubernetes, Airflow, MLflow, Weaviate and DuckDB**. Everything ran on one Oracle Cloud A1 Flex VM (4 OCPU, 24GB, free tier) running k3s, with k3d for local development.

```
Oracle VM (k3s)
├── namespace galaxy-pipeline:  Airflow, MLflow, training Jobs (k8s Jobs)
└── namespace galaxy-serving:   Weaviate, chatbot-api, embedding-service,
                                stats-api (DuckDB on a PVC), Redis,
                                Ollama (GPU only), Streamlit frontend, ingress
```

Two independent pipelines, both scheduled Wednesdays 02:00 UTC:

1. **Fandom embedding pipeline:** scrape youtube.fandom.com (about 20.8K creators) → embed with GTE-Large-v1.5 → KMeans (120 clusters) + UMAP 3D → MLflow quality gate (silhouette ≥ 0.40) → `starmap.parquet` in Oracle Object Storage → load into Weaviate → `POST /api/admin/reload`.
2. **Kaggle stats pipeline:** Kaggle "Global YouTube Statistics 2023" CSV → KMeans (about 20 archetypes) on log-scaled counts → quality gate (silhouette ≥ 0.30) → DuckDB file on a PVC → stats-api → reload.

Serving: Streamlit frontend (Galaxy, Chat, Stats tabs) at spookypharaoh.com. The chatbot did hybrid search in Weaviate and used Groq (or local Ollama on GPU) for answers. Airflow only passed S3 paths and metrics around through XCom. The data itself moved through object storage.

Tool responsibilities in the original design:

| Tool | Role |
|---|---|
| Kubernetes | Runtime for every service and batch Job |
| Airflow | Scheduling and task sequencing |
| MLflow | Experiment tracking, model registry, quality gate |
| Weaviate | Vector index, hybrid search, RAG retrieval |
| DuckDB | Structured store for stats and archetype labels |

(Feast and Terraform had already been dropped before this point.)

## Why it changed

The architecture was sized for a team, not a hobby site. The data is small (about 85MB of embeddings), changes slowly, and serves one person's site. Running Kubernetes, Airflow, MLflow, Weaviate and Redis on one VM meant maintaining five services for very little traffic. The Kubernetes part was learning-only and had no good fit in a production path that trains at home and publishes results.

New direction (summary):

- **Kubernetes removed.** Manifests and k3d configs are kept in `../k8s/` and `../k3d/` for reference only.
- **Airflow and MLflow kept, but run locally** (on the Mac or desktop) for the scheduled scrape → embed → cluster → evaluate → publish job. MLflow tracks clustering runs and RAG retrieval evaluation.
- **Weaviate replaced by a serverless/embedded vector store**, chosen to avoid server hosting and monthly cost. This was a deliberate cost and ops tradeoff, not a limitation of Weaviate, which handles this scale fine.
- **Serving is light:** static pages for Galaxy and Stats, plus a small chat API (semantic search first, then an LLM answering over the retrieved creators).
