# YouTube Galaxy — Design

Date: 2026-11-15 · Status: draft for approval

This design sits on top of two existing documents and **does not repeat them**:

- `README.md` — target architecture, stack, published-file list, quality gate.
- `docs/IMPLEMENTATION_PROMPT.md` — the detailed work order (environment, per-phase tasks, operating rules, checkpoints).
- `CLAUDE.md` — hard rules (no paid services, no k8s/Weaviate/etc., secrets, CC BY-SA attribution, generic User-Agent).

Everything in those documents stands **except where this design says otherwise**. The deltas are collected in "Changes to the work order" below.

## Intent

An explorable, colourful 2D/3D "galaxy" of ~20.8K YouTube creators from the Fandom YouTube wiki, clustered by text similarity, with a chat box for finding creators. It has three audiences at once, and all three matter:

1. **Viewers** of the owner's YouTube channel (SpookyPharaoh) — something fun to share and poke at.
2. **Portfolio** — a credible, honest MLOps project (scheduled pipeline, experiment tracking, evaluation, quality gate, versioned rollback-able releases).
3. **Learning** — the owner wants to understand what is built, especially the evaluation.

It is also the **first feature of a larger hobby site**. A music-recommendation feature and other "silly things" are expected later, so the structure must let new features be added without touching the galaxy.

Budget: **$0/month**, permanently.

## Goals

- A visually exciting map: one distinct colour per cluster (N clusters → N colours), immediately showing fun niche categories.
- 2D default, 3D toggle, search, detail panel with 10 similar creators, cluster legend, attribution, mobile-friendly.
- Chat `search` mode (semantic creator search) on a free Cloudflare Worker.
- A local pipeline that refreshes weekly, incrementally, and only publishes when quality checks pass.
- Something live early (see Delivery order).

## Non-goals (for this design)

- `ask` mode (LLM answers) in the first release — it is a later step, after search is live.
- The music recommender or any second feature — only the room for it (site layout and pipeline conventions).
- Any server, database, or paid service.

## Anti-goals (a failure even if it "works")

- A map that looks dull or muddy (e.g. a handful of broad colours) — the colourful 120-ish-category look is the point.
- Cluster names that are generic or duplicated ("Gaming Content Creators" ×20).
- Colours or names that reshuffle every weekly refresh, so the map feels different each time.
- Anything that can start billing.
- A portfolio claim the repo can't back up (docs that don't match reality).

## Constraints

From CLAUDE.md/README (unchanged): Hostinger Premium static-only; Cloudflare free plan only; `BAAI/bge-small-en-v1.5` with CLS pooling and bge query prefix, verified for parity; stable creator ids; secrets only in `.env`/Worker secrets; CC BY-SA attribution with per-creator source links; generic scraper User-Agent; no commits unless asked; `git mv` for relocation; never delete `archive/`; never modify the sibling repo.

New facts found during brainstorming:

- **Start fresh from `main`.** Branch `before-superpowers` (5 commits: an earlier Phase 0 + Phase 1 spike) was set aside on purpose by the owner. Do not merge, rebase or cherry-pick from it, do not reuse its measurements or `NOTES.md` facts (re-verify everything in Phase 1), and do not delete the branch.
- **Working-tree leftovers** from that branch are on disk as ignored files: `pipeline/`, `tests/`, `worker/`, `.venv-airflow/`, `archive/quick/`, `archive/serving/`, `.pytest_cache/`. Phase 0 removes them **after showing the owner the list**. `.env` is **kept** (it may hold credentials) and reconciled with the new `.env.example`.
- **Seed descriptions differ slightly** between `starmap_data.parquet` and the seed JSON. Embed from the JSON; use the parquet only for `id → cluster_name`.

- **Domain:** `spookypharaoh.com` is registered on Hostinger with **no site yet** (default Hostinger placeholder page). Nothing to conflict with.
- **Seed cluster names come from the old app's final output, not `creators_labeled.json`.** The owner confirms `creators_labeled.json` (15 broad names, 2,477 "Unknown_Cluster") was an old artifact and was not used. The real names are in `../Controversy-Early-Warning-System/data/processed/plotly/`:
  - `starmap_data.parquet` (newest, Mar 2026) ≡ `starmap_data_big_tsne_trimmed_120_labeled.csv` ≡ `starmap_data_big_umap_trimmed_120_labeled.csv` in cluster assignment and names (verified: identical `cluster_id` and `cluster_name` for all 20,807 ids).
  - Columns: `id, title, description, thumbnail, youtube_url, cluster_id, x, y, z, cluster_name`. 120 distinct, specific names (e.g. "Minecraft Commentary & SMPs", "Geometry Dash Levels & Demons"). Cluster sizes 40–366, median ~170.
  - Names were produced by pasting a cluster file into Gemini by hand (`naming_clusters.ipynb`).
- **Creator ids** are `fandom_{pageid}` (from the MediaWiki parse API `pageid`), so they are stable across page renames. The incremental scraper must produce ids the same way.
- **The seed scrape has no revision ids**, so an incremental run cannot tell what changed since it was taken.
- Local tooling present: `uv`, Node 24.

## Approaches considered (delivery order)

The tooling is fixed by the README; the open choice was the order of work.

| | Order | Trade-off |
|---|---|---|
| A | The work order as written: spike → pipeline → site → Worker → eval/gate → Airflow → first publish. | Safest, but nothing is live until almost everything is built. |
| **B (chosen)** | Spike first, then pipeline → site → **publish map without chat** → Worker search → publish chat → eval/MLflow/gate → Airflow → `ask`. | Something real ships early and the riskiest assumption is still tested first. Cost: the first live publish happens before the automated gate exists, so it is reviewed by eye at Checkpoint 2. |
| C | Map first, Worker spike later. | Fastest visible progress, but a Worker that doesn't fit the free plan would be discovered late. Rejected. |

**Chosen: B**, by the owner.

## Delivery order (replaces the work order's phase sequence)

Each step keeps the content of the corresponding work-order phase unless changed below. Checkpoints stay mandatory stops.

1. **Phase 0 — Archive and scaffold.** As in the work order.
2. **Phase 1 — Worker spike** (go/no-go). As in the work order. 🛑 Checkpoint 1 (needs `wrangler login` + Cloudflare credentials).
3. **Phase 2 — Local pipeline** (scrape, embed, cluster, names, build). Includes a **cluster-count comparison** (see below). 🛑 Checkpoint 2: owner reviews names, sanity checks, and **picks the cluster count**; the assistant explains the quality scores in plain language before asking.
4. **Phase 3 — Static site** (map only; chat widget built but hidden/disabled until the Worker exists) **plus the site home page.**
5. **First publish — map only.** A minimal `pipeline/publish.py` for the Hostinger side only (SFTP, versioned dirs, manifest last, `--dry-run`, rollback). Write the Hostinger part of `docs/DEPLOY.md`. 🛑 Checkpoint: dry-run shown; real upload only on the owner's "go". There is no automated gate yet; the owner's Checkpoint-2 review is the gate for this one release.
6. **Phase 4 — Worker, `search` mode only.** Production quality per the work order, minus `ask`. 🛑 Checkpoint 3 (local demo, look and feel).
7. **Publish chat.** Extend `publish.py` with Worker-first deploy and `/health` verification; enable the chat widget. 🛑 Checkpoint before the real deploy.
8. **Phase 5 — Eval, MLflow, gate.** As in the work order. The gate then wraps every subsequent publish.
9. **Phase 6 — Airflow** weekly DAG. As in the work order, but the cluster task runs **assign mode** (see "Weekly refresh: fixed clusters"). Add a manual `make recluster` target that is never scheduled.
10. **`ask` mode.** LLM answers over SSE as described in the work order's Phase 4 `ask` bullets, plus the Phase 1 LLM findings. 🛑 Checkpoint: report measured Neuron cost per answer and the implied daily answer budget; offer Groq if quality is poor.
11. **Phase 8 — Docs and cleanup**, plus portfolio items (below).

## Changes to the work order

### Weekly refresh: fixed clusters (replaces re-clustering every run)

The work order re-clusters on every run. Instead, the cluster step has **two modes**:

- **Fit mode** (`make recluster`, and the first run): full KMeans + UMAP 2D/3D fit. Names and colours carry over from the previous model by centroid cosine + Hungarian match (or, on the very first fit, from the seed parquet, see below). Layout is Procrustes-aligned to the previous one. Writes `unnamed_clusters.md` and naming packs. **Requires a manual naming review before publishing.** Never scheduled. The 60/120/200 comparison at Checkpoint 2 uses fit mode.
- **Assign mode** (every weekly / Airflow run): load the persisted model and keep cluster identity and coordinates fixed.
  - New or changed creators: nearest-centroid cluster assignment, placed with the fitted UMAP reducers' `transform`.
  - Unchanged creators keep their coordinates exactly.
  - Removed creators are dropped.
  - Exact top-10 neighbours are recomputed over all vectors (cheap).
  - Centroids (for the Worker's search) and cluster leaders are recomputed from current members, but cluster keys, names and colours never change.

The **persisted cluster model** lives in `data/model/galaxy/`: fitted KMeans centroids, the fitted UMAP 2D and 3D reducers (pickled), and the cluster registry (`cluster_key → name, colour`). It is logged to MLflow with the fit run.

Effects elsewhere:
- Procrustes alignment and centroid-Hungarian carry-over happen **only in fit mode**.
- The gate's silhouette check runs in both modes. In assign mode it catches drift, and its floor comes from the chosen fit run.
- The run report shows the share of creators added or reassigned since the last fit. Above a threshold (builder's call, e.g. 15%) it **recommends** a re-cluster. It never blocks a publish on this alone.
- The Airflow DAG runs assign mode only.

### Cluster names (replaces Phase 2 step 5's bootstrap)

- **Seed source:** `../Controversy-Early-Warning-System/data/processed/plotly/starmap_data.parquet` (`id → cluster_name`). Not `creators_labeled.json`.
- **Bootstrap:** build the overlap matrix between new clusters and old named clusters by shared creator ids. Use Hungarian assignment on overlap (e.g. Jaccard) so each old name is used **at most once**. A new cluster whose best overlap is below a threshold stays unnamed.
- **Later re-clusters (fit mode only):** carry names over by centroid cosine + Hungarian. Weekly assign-mode runs never rename anything.
- **First publish:** every cluster has a real name, either from the seed or given by the owner at Checkpoint 2.
- **Placeholders** (top keywords) may go live only after a manual re-cluster that produces more clusters than there are names. The owner does not expect this to happen.
- **Unnamed clusters:** `unnamed_clusters.md` lists them, and the pipeline also writes a **naming pack** per unnamed cluster (cluster id, size, ~30 top titles nearest the centroid, short bio snippets, plus TF-IDF keyword suggestions). The owner pastes it into any free chatbot (as was done with Gemini originally) and writes names into `data/cluster_names.json`. The pipeline never calls an LLM for naming. Placeholder name until then: top keywords.

### Cluster colours (new)

- **One distinct colour per cluster.** Palette size = number of clusters.
- **Colours carry over** between runs together with names. Each cluster has a stable identity (a persistent `cluster_key`, carried by the Hungarian match), and its colour is stored in `data/cluster_names.json` (or a sibling `cluster_registry.json`) alongside the name. New clusters get the unused colour that is most distinct from the existing ones. Colours never reshuffle because cluster *indices* changed.
- Neighbouring clusters may still look alike. Hover tooltip and legend give the exact name.

### Layout stability

Weekly runs don't move existing points (assign mode). On a re-cluster, Procrustes alignment to the previous layout is **on by default** (the work order says optional), because a jumping map is an anti-goal.

### Cluster-count comparison (new, part of Phase 2)

120 was a guess. On the first run, cluster at **60, 120 and 200** (same seed), and report silhouette, cluster-size distribution, the number of seed names that matched, and a few example clusters for each. The owner picks the count at Checkpoint 2, after a plain-language explanation of what silhouette measures and why text clusters score low (typically ~0.03–0.10). `N_CLUSTERS` in `.env` is then set to that choice. The gate's silhouette floor is derived from the chosen run.

### Incremental scrape baseline (adds to Phase 2 step 2)

On the first incremental run with no state file, **treat the seed snapshot as current**: fetch current `lastrevid` for all seed titles in batches of 50, write them as the baseline state, and fetch no page content. Only later changes trigger fetches. `--full` remains available. New pages found in the category listing on that first run are fetched normally.

### Thumbnails

Loaded **only in the detail panel**, lazily, from the URL in the data. On error, fall back to a text-only card. No thumbnails on the map itself.

### Site structure: room for more features (new)

- **Root of spookypharaoh.com:** a small static home page (title, one-line description, card linking to `/galaxy/`, footer). It is built from `web/` as a second Vite entry, or from a tiny `site/` folder. **Builder's call** which, as long as it is one build command.
- **Galaxy:** `/galaxy/` (unchanged `SITE_BASE_PATH`, `HOSTINGER_REMOTE_DIR=public_html/galaxy`). Its published files stay self-contained under that folder.
- **Publishing the home page** goes to `public_html/` root and must never touch other feature folders. Publishing the galaxy must never touch the root or other features.
- **Pipeline convention:** the galaxy's outputs live under `data/artifacts/galaxy/<version>/`, not `data/artifacts/<version>/`. A future feature (e.g. music) would get its own `pipeline/<feature>/` modules, its own `data/artifacts/<feature>/`, its own DAG and its own site folder. Do **not** build any shared "feature framework" now. Just keep the galaxy self-contained and the paths namespaced.

### Chat in the first release

- The Worker ships with `search` only. `POST /api/chat` with `mode: "ask"` returns a clear "not available yet" response.
- The widget offers search only until `ask` ships.

### Portfolio and learning additions (new)

- **GitHub Actions CI** (free for public repos and within free minutes for private): run `pytest`, `ruff`, and the `worker/` vitest suite on push. It does **not** run the pipeline, deploy anything, or need secrets.
- **README** gains real screenshots (map, MLflow run, gate output) at Phase 8, and an honest "what was measured" section (CPU p95, parity score, silhouette, recall).
- **Plain-language explanations at every checkpoint report:** what was measured, what the number means, and what a good or bad value looks like. Required at Checkpoint 2 for silhouette and the cluster-count choice, and at the eval checkpoint for recall@k, MRR and brute-force agreement.

## Decided by the owner

- Delivery order B.
- Flat clusters, one colour per cluster, colours carry over.
- Cluster count chosen by the owner from the 60/120/200 comparison.
- Seed names from the old app's labelled parquet/CSV.
- Incremental scrape starts from the seed snapshot (no re-crawl).
- Thumbnails only in the detail panel, with a text fallback.
- Search first, `ask` later.
- Root home page linking to `/galaxy/`; future features in sibling folders.
- Start completely fresh from `main`; `before-superpowers` stays set aside.
- Fixed clusters on weekly runs; re-cluster only by hand (`make recluster`), with a naming review.
- Placeholder names only after a manual re-cluster that creates more clusters than there are names.

## Assistant's calls (owner may override)

- Hungarian one-to-one matching for name bootstrap, with an overlap threshold.
- Naming packs for manual naming in a free chatbot, with keyword placeholders.
- Procrustes alignment on by default (fit mode).
- Persisted cluster model in `data/model/galaxy/`; a "recommend re-cluster" drift threshold in the run report.
- Removing the set-aside branch's ignored leftovers in Phase 0 (after showing the list), keeping `.env`.
- Cluster colours stored with names in a persistent registry.
- `data/artifacts/galaxy/<version>/` namespacing.
- GitHub Actions CI for tests only.
- The first map publish is hand-reviewed rather than gated.

## Left to the builder

Everything the work order leaves open: Airflow 2.x vs 3.x (verify the docs), index delivery mechanism (Phase 1 decides), the Workers AI LLM model (Phase 1), exact file formats for nodes and neighbours, the palette algorithm, the home page's build mechanism, rate-limit mechanism, schedule day and time, the overlap threshold value, and test structure. Every external fact gets verified and recorded in `docs/NOTES.md` with its source URL and date.
