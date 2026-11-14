# YouTube Galaxy

An explorable map of ~20,800 YouTube creators, grouped by how similar their wiki descriptions are, plus a chat box that answers questions about them. Hobby project, built to run for **$0/month**, with Airflow and MLflow doing the real MLOps work on a home machine.

> **Status: re-plan complete, implementation pending.** The repo was originally a Kubernetes/Oracle Cloud stack (see [`archive/`](archive/)). It was simplified to the design below. This README describes the **target** state. To build it, hand [`docs/IMPLEMENTATION_PROMPT.md`](docs/IMPLEMENTATION_PROMPT.md) to a Claude Code instance. Commands marked *(planned)* don't exist yet.

---

## The idea in one paragraph

Everything heavy happens **on your own machine**: scrape the Fandom wiki, embed the text, cluster it, evaluate it, and only publish if quality checks pass. Publishing produces a small set of static files. A static website (Hostinger) draws the map from those files, and a tiny free Cloudflare Worker answers chat questions. There is no server to babysit, and when your machine is off the site keeps working with the last published data.

## Architecture

```
 YOUR MACHINE (Mac / desktop)                                   THE INTERNET
 ────────────────────────────                                   ────────────

 Airflow DAG  galaxy_refresh   (weekly schedule or manual trigger)
 ┌────────────────────────────────────────────────────────────────────┐
 │ 1 scrape      incremental: fetch only new/changed wiki pages       │
 │               raw JSON ──(backup)──▶ Synology                      │
 │ 2 embed       bge-small-en-v1.5 (384-dim), only changed creators   │
 │ 3 cluster     KMeans (~120) + UMAP 2D + UMAP 3D + neighbours       │
 │ 4 evaluate    recall@k on hand-written questions ──▶ MLflow        │
 │ 5 GATE        quality floor + no regression ── fail ─▶ STOP        │
 │                                         (live site untouched)      │
 │ 6 build       static map files + chat index                        │
 │ 7 publish ─────┬── SFTP ───────────────────▶ HOSTINGER (static)    │
 │                │                             Galaxy map + chat UI  │
 │                └── wrangler deploy ────────▶ CLOUDFLARE WORKER     │
 └────────────────────────────────────────────────────────────────────┘      chat API (free tier)
 MLflow (local, sqlite)  ·  data/ (gitignored)                                   │
                                                                                 │
 VISITOR                                                                         │
  browser ─ loads map files from Hostinger (no backend involved)                 │
  browser ─ chat question ──▶ Worker:  embed query (Workers AI)                  │
                                       pick nearest clusters via centroids       │
                                       cosine search inside them (in memory)     │
                                       [ask mode] top results ─▶ LLM ─▶ answer   │
```

### Why it is shaped this way

| Decision | Reason |
|---|---|
| Train/schedule at home, publish static artifacts | The data is small (about 8MB of int8 vectors) and changes slowly. A cloud cluster for it is all cost and upkeep. |
| Hostinger Premium only serves static files | It is shared hosting. No long-running Python, no Airflow, no databases of ours. |
| Chat runs on a Cloudflare Worker | Free tier, no server, and it can embed queries and call an LLM through Workers AI. |
| No vector database | Cloudflare Vectorize's free plan caps stored dimensions below what 20.8K×384 needs, and a paid plan was rejected on cost. The index is a file searched in memory. |
| Two-stage search (centroids, then members) | Brute force over 20.8K×384 likely exceeds the free plan's 10 ms CPU limit. Probing only the nearest ~3 of 120 clusters is about 40× less work. |
| 2D map first, 3D toggle | 2D is easier to read and works on phones. Both layouts are precomputed in the pipeline. |
| Similar creators are precomputed | The map's "similar to X" panel needs no Worker at all. |

**Weaviate was replaced by an in-memory index on purpose, to avoid server hosting and monthly cost.** It handles this scale fine, and nothing is wrong with it. This project just has no budget for a box to run it on.

## Stack

| Tool | Role | Where it runs |
|---|---|---|
| **Airflow** | Scheduling and sequencing of the refresh pipeline | Local machine |
| **MLflow** | Tracks clustering/eval runs, stores the quality metrics the gate reads | Local machine |
| **sentence-transformers** (`BAAI/bge-small-en-v1.5`) | Embeddings, 384-dim | Local machine |
| **scikit-learn / UMAP** | KMeans clusters, 2D and 3D layouts | Local machine |
| **Cloudflare Worker + Workers AI** | Query embedding, search, LLM answers | Cloudflare free tier |
| **Static site** (Vite + TypeScript + deck.gl) | Galaxy map, search, chat widget | Hostinger |
| **Synology** | Backups of raw scrapes | Home network |

Dropped: Kubernetes, Oracle Cloud, Weaviate, Redis, DuckDB, Kaggle stats pipeline, Streamlit, Feast, Terraform. All are preserved in [`archive/`](archive/).

## Target repo layout

```
youtube-galaxy-mlops/
├── README.md  CLAUDE.md  Makefile  pyproject.toml  .env.example
├── pipeline/           Python package: scrape, embed, cluster, build, eval, gate, publish
├── dags/               galaxy_refresh_dag.py (thin: shells out to pipeline/)
├── eval/               questions.yaml (hand-written eval set) + reports
├── web/                Static site (Vite + TS + deck.gl) → builds to web/dist
├── worker/             Cloudflare Worker (TypeScript) + wrangler config
├── scrapers/fandom/    Fandom scraper (copied from the sibling repo, fixed, incremental)
├── scripts/            Setup helpers (Airflow venv, MLflow server)
├── docs/               IMPLEMENTATION_PROMPT.md, notes
├── data/               gitignored: raw/, embeddings/, artifacts/, mlflow/
└── archive/            Previous plan, kept as-is (k8s, learn/, stats, Weaviate, Streamlit)
```

## What gets published

Each run builds one **versioned artifact set**. The site reads `manifest.json` (not cached) which points to the current version's files, and it is uploaded last, so a half-finished publish never breaks the site.

| File | Used by | Contents |
|---|---|---|
| `manifest.json` | site | version, build time, creator count, model name, metrics |
| `nodes` | site | per creator: id, title, cluster, 2D and 3D coordinates (columnar, compact) |
| `neighbors` | site | each creator's ~10 nearest neighbours (exact, computed locally) |
| `clusters.json` | site | cluster id, name, centroid position, size, leader creator |
| `details/cluster_N.json` | site | bios and links, loaded lazily per cluster |
| `index.bin` + `centroids.bin` + meta | Worker | int8 vectors ordered by cluster, centroids, packed titles and short bios |

Creators are referenced by stable id (e.g. `fandom_500338`), never by array position, so the Worker and the site can be one version apart without breaking.

## The chat

One endpoint, two modes, built in this order:

1. **`search`** (ship first): embed the question, return the closest creators. No LLM. Cheapest, most robust, and arguably the best part.
2. **`ask`**: take the top ~8 results, put their bios in a prompt, and stream an LLM answer that cites the creators it used. The LLM only sees retrieved text, so it answers from your data, not from memory.

Query embedding and the LLM both use **Workers AI**, so no API keys are needed. Groq is a supported alternative if you provide a key. Free-tier Workers AI hard-stops at its daily quota, so the chat degrades to a friendly "resting for today" message rather than a bill.

## Quality gate

A refresh is published only if all of these hold. The point is that a bad scrape or a bad run never reaches the live site.

- Silhouette is above a floor **measured from a baseline run**, not a guess. The old 0.40 threshold was never validated and is probably unreachable for 120 text clusters.
- Retrieval **recall@8 on the eval set** has not regressed beyond a tolerance.
- Creator count is at least ~90% of the last published run (guards against partial scrapes).
- The two-stage search agrees with exact brute force on the eval set (measures what the speed shortcut costs).

Cluster names carry over between runs by matching each new cluster to the closest previous one. New clusters with no match are listed for you to name.

## What you need to provide

Claude Code can write the code. It cannot do these:

| # | What | Why |
|---|---|---|
| 1 | **Cloudflare account** (free), run `npx wrangler login`, note your Account ID | Deploys the Worker, enables Workers AI |
| 2 | **Cloudflare API token** with Workers AI permission, in `.env` | One-time local check that local and Workers AI embeddings match |
| 3 | **LLM choice for chat.** Default is Workers AI (no key). Optionally a Groq API key as a Worker secret | Needed only for `ask` mode. Some hosted models need a one-time license acceptance. |
| 4 | **Hostinger SFTP details** in `.env`: host, port, user, password or key, and the target folder | Publishing the static site. Confirm SFTP is enabled in hPanel. |
| 5 | **Where on spookypharaoh.com the map lives.** Default `/galaxy/` so it won't overwrite an existing site | Sets the site's base path |
| 6 | **~30 eval questions** with the creators you'd expect back. Claude can draft candidates, you verify | The quality gate and RAG evaluation depend on them |
| 7 | **Review of cluster names** after the first run | Names are seeded from your old labels, but you approve them |
| 8 | **Local tooling:** Python 3.11, `uv`, Node 20+. Docker is not required | See setup below |
| 9 | **Synology backup path** (optional) | Backup copy of each raw scrape |
| 10 | **Keep the machine awake** during a scheduled run (or trigger manually) | Airflow only runs while your machine is on |

## Legal and etiquette

- Fandom wiki text is generally licensed **CC BY-SA**. The site must **credit the wiki and link each creator's source page**. Verify the licence terms before publishing.
- The scraper must be polite: a delay between requests, an incremental mode, and a generic User-Agent. Do not put personal contact details in it.
- Creator thumbnails are hotlinked from Fandom's CDN. Prefer text-only cards or lazy loading, and be ready to drop them if that breaks.

## Setup *(planned)*

```bash
# prerequisites: python 3.11, uv, node 20+
make setup            # uv sync, npm install in web/ and worker/, create the Airflow venv
cp .env.example .env  # then fill in the values from the table above
make mlflow           # local MLflow UI on :5000
make airflow          # local Airflow on :8080
make pipeline         # run scrape → … → gate once, without publishing
make eval             # run the retrieval eval alone
make web-dev          # local map with hot reload
make worker-dev       # local Worker via wrangler
make publish          # gated publish: SFTP + wrangler deploy
```

The first run can reuse the 20,807-creator dataset already scraped in the sibling repo (`Controversy-Early-Warning-System/data/fandom/`). No re-crawl is needed to get started.

## Risks and things to verify early

These are the assumptions the design leans on. **Phase 1 of the implementation prompt exists to test them before anything else is built.**

| Risk | What could go wrong | Fallback |
|---|---|---|
| Worker CPU limit | Free plan allows ~10 ms CPU per request. Search over probed clusters should fit, but it's unmeasured. | Probe fewer clusters, quantise harder, or accept the $5 paid plan |
| Where the index lives | Cloudflare's current docs I read said 64 MiB uncompressed script size, while older docs said a few MB compressed on free. Unverified. | Serve the index as a static asset, or from KV or R2 |
| Embedding mismatch | Workers AI's bge-small must produce vectors compatible with the local ones. Its default pooling differs from the sentence-transformers default (CLS). | Pass `pooling: "cls"`, add the query prefix, test parity before building |
| bge-small context | Max 512 tokens. About 1 in 10 descriptions is longer and gets truncated. | Embed the title plus the opening text, then check with the eval set |
| UMAP instability | The layout can shift between runs, so the map "jumps". | Fixed seeds, and optionally align to the previous layout |
| Free-tier limits | Workers 100K requests/day, Workers AI 10K Neurons/day. | The site keeps working. Only `ask` degrades gracefully. |

Free-tier numbers and model IDs change. Check current Cloudflare docs when building.

## Roadmap

1. Archive old code, scaffold the new layout.
2. **Spike:** Worker CPU, index delivery, embedding parity. Go/no-go on the Worker approach.
3. Local pipeline: incremental scrape, embed, cluster, export.
4. Static map (2D, then 3D toggle, search, neighbours, clusters).
5. Worker: `search` mode, then `ask` mode.
6. Eval set, MLflow tracking, quality gate.
7. Airflow DAG wrapping the pipeline.
8. Publish to Hostinger and Cloudflare, then deploy.

**Later ideas** (not in scope): music recommendations for creators (another DAG publishing another artifact set), sentiment drift over time, cluster highlights.

## History

This repo began as a hands-on learning project for Kubernetes, Airflow, MLflow, Weaviate and DuckDB, targeting an Oracle Cloud VM. That plan, its tutorials and manifests are in [`archive/`](archive/); the explanation of the original architecture and why it changed is at the bottom of [`archive/learn/README.md`](archive/learn/README.md).
