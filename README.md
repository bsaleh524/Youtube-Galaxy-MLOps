# YouTube Galaxy

An explorable map of ~20,800 YouTube creators, grouped by how similar their wiki descriptions are, plus a chat box that answers questions about them. Hobby project, built to run for **$0/month**, with Airflow and MLflow doing the real MLOps work on a home machine.

> **Status (2026-11-24): map and chat search are live** at spookypharaoh.com/galaxy/ (not announced yet). The chat answers in `search` mode; `ask` mode is not built (issue #8). Plan 5 (eval set, MLflow tracking, quality gate before publish) is built; see [Quality gate](#quality-gate). The repo was originally a Kubernetes/Oracle Cloud stack (see [`archive/`](archive/)). Commands marked *(planned)* don't exist yet.

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

1. **`search`** (live): embed the question, return the closest creators. "channels like X" uses X's own position instead. No LLM. Cheapest, most robust, and arguably the best part.
2. **`ask`** (not built, issue #8; may need a budget): take the top ~8 results, put their bios in a prompt, and stream an LLM answer that cites the creators it used. The LLM only sees retrieved text, so it answers from your data, not from memory.

Query embedding and the LLM both use **Workers AI**, so no API keys are needed. Groq is a supported alternative if you provide a key. Free-tier Workers AI hard-stops at its daily quota, so the chat degrades to a friendly "resting for today" message rather than a bill.

## Quality gate

A refresh is published only if all four checks pass, so a bad scrape or a bad run never reaches the live site. Thresholds live in [`eval/gate.yaml`](eval/gate.yaml); they were set from a baseline run of the live build `20261124-053913-640c47c5` (2026-11-24).

| Check | What it measures | Baseline | Must be |
|---|---|---|---|
| **Silhouette** | How cleanly creators separate into clusters (−1…1, on the published int8 vectors). Text clusters sit near 0.03. | 0.029 | ≥ 0.024 |
| **Recall@8** | On the approved questions in [`eval/questions.yaml`](eval/questions.yaml): the share of expected creators that appear in the top 8 answers. | 0.186 | no more than 0.05 below the live build's |
| **Creators** | How many creators the build has (guards against partial scrapes). | 20,807 | ≥ 90% of the live build's |
| **Agreement** | Share of the exact (brute-force) top 8 that the fast two-stage search still finds. | 0.78 | ≥ 0.70 |

MRR (how high the first expected creator ranks) is recorded too but not gated. The recall comparison is skipped when the questions file changed since the live build was scored (re-run `make eval` on the live build to compare again).

```bash
make pipeline                  # embed -> cluster -> build -> eval -> gate (stops if the gate fails)
make eval                      # or by hand: score the newest build -> data/runs/eval-<version>/report.md
make gate                      # pass/fail it -> data/runs/eval-<version>/gate.json
make mlflow                    # every eval run, metric and the champion: http://127.0.0.1:5001
make champion VERSION=<v>      # mark an already-live build as the champion (publish does this itself)
```

`make publish` (and `publish-chat`) refuse a build without a passing, up-to-date gate result. `--no-gate` overrides it with a warning, and such a build never becomes the champion. After a publish is confirmed live, MLflow's registered model `galaxy` gets the alias `champion` pointing at that build's eval run; the next build is compared against it.

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
# prerequisites: python 3.11, uv, node 24+
make setup            # uv sync, npm install in web/ and worker/, create the Airflow venv
cp .env.example .env  # then fill in the values from the table above
make mlflow           # local MLflow UI on :5000
make airflow          # local Airflow on :8080
make seed             # snapshot the 20,807-creator seed dataset (first run only)
make embed            # embed new/changed creators (~3 min first time, seconds after)
make recluster        # full re-fit (manual only; K=200 to override; FRESH=1 re-names from seed labels)
make sanity           # score embeddings: 15 checks, name-lookalike rate, silhouette (EMB=dir OUT=file.md)
make naming-brief     # one file for a chat assistant to name every placeholder cluster
make import-names FILE=reply.txt  # merge the chat's JSON reply into data/cluster_names.json (DRY=1, FORCE=1)
make compare-k        # compare cluster counts (KS=60,120,200) without touching the live model
make build            # write data/artifacts/galaxy/<version>/
make pipeline         # embed → cluster (assign) → build; skips if nothing changed (FORCE=1)
make eval             # run the retrieval eval alone (planned)
make web-data         # copy the newest build's data into web/.devdata (needed by web-dev)
make web-dev          # local map with hot reload at http://localhost:5173/galaxy/
make web-build        # build the site into web/dist
make preview          # stage the exact Hostinger tree and serve it on :8080 (phone-friendly)
make publish-dry      # show what a publish would upload (connects read-only)
make publish          # Worker first (when WORKER_URL is set), then home page + map to Hostinger; see docs/DEPLOY.md
make rollback VERSION=<version>  # point the live map at an older data version
make chat-dev         # local chat Worker on :8787 with the newest build's index (see docs/DEPLOY.md)
make publish-chat     # redeploy only the chat Worker, then check its /health
```

The first run can reuse the 20,807-creator dataset already scraped in the sibling repo (`Controversy-Early-Warning-System/data/fandom/`). No re-crawl is needed to get started.

How creators are embedded and how each version scored: [docs/EMBEDDINGS.md](docs/EMBEDDINGS.md). Naming clusters (one-shot with a chat assistant, or by hand): [docs/NAMING_CLUSTERS.md](docs/NAMING_CLUSTERS.md).

## Rerunning things

Common jobs after the first setup. Every recipe ends the same way:

```bash
make build      # write a new data version
make preview    # optional: check it at http://localhost:8080/galaxy/ (Ctrl+C to stop)
make publish    # upload; the live check at the end must report the new version
```

Nothing goes live until `make publish` finishes. If a publish looks wrong, `make rollback VERSION=<previous version>` puts the old map back. Versions are the folder names in `data/artifacts/galaxy/`.

**Rename one or a few clusters.** Edit `data/cluster_names.json` (key → name; keys are in `data/model/galaxy/registry.json`), then build, preview, publish. A typo in the JSON stops the build with an error.

**Name every placeholder cluster in one go** (e.g. after a re-cluster leaves new placeholders):

```bash
make naming-brief                                    # writes data/runs/<fit run>/naming_brief.md
# upload naming_brief.md to a Claude Pro / Gemini Pro chat: "Follow the instructions in this file."
# save the whole reply as a text file, e.g. data/naming/names_reply.txt
make import-names FILE=data/naming/names_reply.txt DRY=1   # check: unknown keys, empty names, duplicates
make import-names FILE=data/naming/names_reply.txt         # merge into data/cluster_names.json
```

`make naming-brief` only lists clusters that are still unnamed, so after a full import it says "Nothing to name". `import-names` keeps names you already set unless you add `FORCE=1`. Details: [docs/NAMING_CLUSTERS.md](docs/NAMING_CLUSTERS.md).

**The chat Worker follows the site.** Once `WORKER_URL` is in `.env`, every `make publish` redeploys the Worker with the same build first and checks it. If you roll the site back, also run `uv run python -m pipeline.publish worker --version <VERSION>` (docs/DEPLOY.md).

**Weekly data refresh.** `make pipeline` re-embeds only changed creators, places them in the existing clusters (keys and names don't change), and builds. If nothing changed, it skips; use `FORCE=1` to rebuild anyway. Then preview and publish.

**Re-cluster** (after a big data change or new embedding rules):

```bash
make embed        # only if the embedding text or model changed
make sanity       # optional: score the embeddings (docs/EMBEDDINGS.md §3)
make recluster    # K=120 by default; names carry over to clusters that barely moved
make naming-brief # name any clusters that came out new
```

Then build, preview, publish. **Never use `FRESH=1` once `data/cluster_names.json` has names.** It renumbers every cluster, so your names would land on the wrong ones (docs/EMBEDDINGS.md §7). A plain `make recluster` matches new clusters to old ones by centre. Your name survives on any cluster that barely moved; a cluster that changed a lot gets a new key and a placeholder.

**Files to keep safe.** These live in `data/`, which is not in git:
- `data/cluster_names.json`: your names. Keep a copy somewhere.
- `data/model/galaxy/`: the live model (`galaxy.prev` is the one before).
- `data/raw/`: the creator snapshots.

Chat replies like `names_reply.txt` belong under `data/` too, so they never get committed.

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
