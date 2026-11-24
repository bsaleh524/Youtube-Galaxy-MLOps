# Plan 2 — Local Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local pipeline: seed snapshot, embed, cluster (fit and assign modes), names and colours, and the versioned artifact build. Run it on the seed data at 60, 120 and 200 clusters, then stop at 🛑 Checkpoint 2 so the owner can pick the cluster count and review the names.

**Architecture:** One module per step under `pipeline/`, each runnable as `uv run python -m pipeline.<step>`. Steps talk through files under `data/` only, never through imports of each other's state. That keeps them runnable one at a time now and as Airflow tasks later (Plan 6). Heavy libraries (torch, sentence-transformers, umap, mlflow) are imported **inside functions**, so the `ci` group still runs every pure-logic test.

**Tech Stack:** Python 3.11, uv, numpy, pandas/pyarrow, scikit-learn (KMeans, silhouette, TF-IDF), scipy (`linear_sum_assignment`, `orthogonal_procrustes`; installed with scikit-learn), umap-learn, sentence-transformers, requests, beautifulsoup4, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-15-youtube-galaxy-design.md`. Its sections "Weekly refresh: fixed clusters", "Cluster names", "Cluster colours", "Layout stability", "Cluster-count comparison" and "Incremental scrape baseline" (now moot, see Tasks 2–3) **override** Phase 2 of `docs/IMPLEMENTATION_PROMPT.md` wherever the two differ. Plan 1 is `docs/superpowers/plans/2026-11-15-plan-1-foundation-and-worker-spike.md`.

## Facts carried in from Checkpoint 1 (docs/NOTES.md)

- **Index delivery is bundled Data modules** (commit 9c5eafb). `worker/src/main.ts` imports `worker/assets/{index.bin,centroids.bin,meta.bin,index_manifest.json}` into the script. Limits:
  - script size: 64 MiB uncompressed;
  - isolate memory: 128 MB;
  - global scope at startup: 1 s.

  This plan only *produces* those four files. Copying them into `worker/assets/` and deploying is Plan 4.
- **Keep meta small.** The p99 CPU tail is open as [issue #1](https://github.com/bsaleh524/Youtube-Galaxy-MLOps/issues/1). A bigger bundle may make startup or GC worse.
  - Worker bios: ≤ 400 chars.
  - Meta records carry only `id, title, cluster, url, snippet`. These are the fields `worker/src/format.ts` `MetaRecord` already reads.
  - The build reports `meta.bin` and total bundle size, and warns above 20 MB.
- **Embedding parity is settled.** Use `BAAI/bge-small-en-v1.5`, CLS pooling (sentence-transformers' default for this model) and normalised vectors. Passages get no prefix.
- **Binary formats already exist.** `pipeline/index_format.py` (`quantize_rows`, `write_index`, `write_centroids`, `write_meta`) and `pipeline/search.py` are reused unchanged. The cross-language fixture must keep passing.
- **Seed facts, checked 2026-11-17:**
  - `starmap_data.parquet` has 20,807 rows, ids that all match `^fandom_\d+$`, and 120 distinct `cluster_name`s.
  - The seed JSON is 47.6 MB.

## Global Constraints

Plan 1's Global Constraints still apply. The ones that matter most here:
- $0, no paid services.
- Don't modify `../Controversy-Early-Warning-System/`. Reading and copying are fine.
- Generic User-Agent `galaxy-hobby-scraper/1.0`, with no personal details in any request.
- Commit **and push** after every task, to `superpowers-rework`. Stage specific paths. Never stage `data/` or `.env`.
- Verify every external fact (MediaWiki API limits and parameters, Fandom robots.txt) against official docs. Record it in `docs/NOTES.md` with the URL and date.
- **Key everything on id (`fandom_{pageid}`), never title.** This covers the embed cache, name bootstrap and build. There are 8 known case-only title pairs, e.g. `TARGET`/`Target`.
- Every output directory is namespaced under `galaxy`: `data/artifacts/galaxy/<version>/` and `data/model/galaxy/`.
- Fixed seeds everywhere: KMeans `random_state=42` and UMAP `random_state=42`. Same inputs give the same outputs.
- Tests never touch the network or `../Controversy-Early-Warning-System/`. They use small in-repo fixtures and fakes.

## Data layout produced by this plan

```
data/raw/snapshots/<YYYYMMDD-HHMMSS>/creators.json   # schema: id,title,description,thumbnail,youtube_url,url
data/raw/snapshots/<...>/manifest.json               # count, sha256, source, created_at
data/raw/current -> snapshots/<latest>               # text file holding the snapshot dir name (no symlinks)
data/seed/seed_cluster_names.json                    # {id: cluster_name} from starmap_data.parquet
data/embeddings/embeddings.npy                       # float32 (n,384), L2-normalised
data/embeddings/rows.json                            # model, ids, text hashes, sha256 of embeddings.npy
data/model/galaxy/                                   # persisted cluster model (see Task 6)
data/model/galaxy/registry.json                      # cluster_key -> {name, colour, source, active, size, keywords}; saved with the model
data/cluster_names.json                              # owner's manual names: {cluster_key: name}
data/runs/<run_id>/                                  # per-run reports (compare_k.md, unnamed_clusters.md, naming_packs/)
data/artifacts/galaxy/<version>/                     # site + worker files (Task 9)
```

`<version>` is `YYYYMMDD-HHMMSS-<first 8 hex of the embeddings sha256>`. The same version string goes into `manifest.json` and `index_manifest.json`.

## Review Focus

1. **Same-title pages** (`TARGET` `fandom_449281` and `Target` `fandom_372805`). Both must survive snapshot → embed → cluster → build. → Task 1, 4 and 9 tests.
2. **Scraper baseline without a re-crawl.** The first incremental run with no state file fetches only `lastrevid`, in batches of 50 pageids, and **zero page content** for seed pages. → Task 3 test: the fake client counts `action=parse` calls.
3. **Pages gone from the wiki are kept and flagged** (owner decision 2026-11-18). The snapshot step (dump importer, [issue #4](https://github.com/bsaleh524/Youtube-Galaxy-MLOps/issues/4)) carries them forward with their last known text and `missing_from_wiki_since: <date>`; the site shows "no longer on the wiki". Only ids on a manual removal list (`data/removed_ids.txt`: spam, duplicates) leave the snapshot. Anything absent from the snapshot disappears from embeddings and artifacts, and nothing is left behind by index position. → Task 4 and 7 tests; carry-forward tested with the importer.
4. **Assign mode never changes cluster identity.** Keys, names, colours and existing creators' coordinates stay byte-identical across an assign run. → Task 7 test.
5. **One-to-one name bootstrap.** Each seed name is used at most once. Below the overlap threshold, a cluster stays unnamed. → Task 8 test.
6. **Colours** are distinct (pairwise minimum distance reported) and stable across runs. → Task 8 test.
7. **One record per wiki page, not per channel.** Some pages list several channels by the same creator (e.g. anything4views and Cold Ones). Keep one record per page (`fandom_{pageid}`) and keep the first channel link in `youtube_url`, as the seed does. Never split a page into several nodes. Collecting every channel link is a later polish item: [issue #2](https://github.com/bsaleh524/Youtube-Galaxy-MLOps/issues/2). → Task 2 test: a fixture page with two channel links gives one record.
8. **Artifacts reference ids only.** `neighbors` and `clusters.json` leaders use ids, and `nodes` order is not something consumers rely on. → Task 9 test.

---

### Task 1: Seed snapshot and seed names

**Files:**
- Create: `pipeline/snapshot.py`, `pipeline/seed.py`, `tests/test_snapshot.py`, `tests/fixtures/creators_small.json` (≈12 synthetic records including a same-title pair, a Japanese title and an emoji)

**Interfaces:**
- `pipeline.snapshot`:
  - `RECORD_KEYS = ("id","title","description","thumbnail","youtube_url","url")`
  - `validate_records(records: list[dict]) -> None` raises `ValueError` on:
    - a missing key;
    - an id that doesn't match `^fandom_\d+$`;
    - a duplicate id.

    Duplicate titles are allowed.
  - `write_snapshot(records, root: Path, source: str) -> Path` writes `creators.json` (sorted by id, UTF-8, `ensure_ascii=False`) and `manifest.json` (`count`, `sha256` of the creators file, `source`, `created_at` UTC ISO). It points `data/raw/current` at the new snapshot and returns the snapshot dir.
  - `load_current(root: Path) -> tuple[list[dict], dict]` returns the records and the manifest.
- `python -m pipeline.seed [--source-json PATH] [--source-parquet PATH]`. The defaults are the sibling-repo paths from the spec. It does two things:
  - copies the JSON in as the first snapshot (`source="seed"`);
  - writes `data/seed/seed_cluster_names.json` (`{id: cluster_name}`), reading only the columns `id, cluster_name` from the parquet.

  If the parquet ids that aren't in the JSON exceed 0.5%, it fails loudly. Otherwise it prints counts.

- [x] **Step 1: Write failing tests.** Cover:
  - validate rejects a duplicate id and accepts duplicate titles;
  - snapshot round-trip keeps non-ASCII text byte-exact;
  - the manifest sha256 matches the file;
  - `current` points at the newest snapshot.
- [x] **Step 2: Implement `pipeline/snapshot.py`** until the tests pass.
- [x] **Step 3: Implement `pipeline/seed.py`.** Run it for real. Record the count, the sha256 and the id overlap with the parquet in `docs/NOTES.md`.
- [x] **Step 4: `make test` passes. Commit and push.** (`feat(pipeline): seed snapshot and seed cluster names`)

### Tasks 2–3: Scraper — DROPPED (owner decision, 2026-11-18)

Fandom's Terms of Use forbid automated access without written permission (`docs/NOTES.md`, "Task 2 step 1"). The only published dump is from 2025-10-27 and sits in S3 deep archive, so it can't be downloaded. The pipeline therefore runs **frozen on the seed snapshot**. The owner has asked Fandom for a fresh dump. A dump importer will be built only once one exists: [issue #4](https://github.com/bsaleh524/Youtube-Galaxy-MLOps/issues/4). No scraper code is written, and the old project's scraper stays untouched.

What changes downstream:
- "Refresh" means **a new snapshot appeared**, not a weekly scrape. `make pipeline` and the Plan 6 DAG check whether the current snapshot's sha256 differs from the one last built. If it doesn't, they finish fast.
- The Review Focus items about the scraper (#2, #3) and the multi-channel test move to the dump importer (issue #4). Same-title pages are still tested in Tasks 4 and 9.

### Task 4: Embed (incremental)

**Files:**
- Create: `pipeline/embed.py`, `pipeline/textprep.py`, `tests/test_embed.py`

**Interfaces:**
- `textprep.embed_text(rec, max_chars=2000) -> tuple[str, bool]` returns `f"{title} - {description}"`, cut at `max_chars` on a word boundary, and whether it was truncated. `max_chars` comes from the `--max-chars` flag (default 2000).
- `textprep.text_hash(text) -> str`: the sha256 hex of the UTF-8 text plus the model name, so changing the model invalidates the cache.
- `embed.plan(records, rows_df) -> (reuse: dict[id,row], todo: list[id], dropped: list[id])` is a pure function.
- `embed.run(encoder, records, out_dir)`:
  - writes new `embeddings.npy` and `rows.json` atomically (rows.json is written last and records the matrix's sha256, so a mismatched pair is detected) (temp file, then rename);
  - copies reused vectors, encodes only `todo`, and drops removed ids;
  - logs counts, the truncated count, and throughput (creators/s);
  - `encoder` is any object with `encode(list[str]) -> np.ndarray`, so tests use a fake.
- `python -m pipeline.embed [--max-chars N] [--batch-size 64]`. The real encoder is `SentenceTransformer(EMBEDDING_MODEL, device=cuda|mps|cpu)` with `normalize_embeddings=True`. Reuse the `_device()` logic from `parity_check.py` and move it into `pipeline/device.py`.

- [x] **Step 1: Write failing tests with a fake encoder.** Cover:
  - first run encodes everything;
  - second run with one changed description encodes 1;
  - a removed id is gone from rows and the matrix shape shrinks;
  - row ↔ id mapping stays right after a removal;
  - truncation keeps words whole and is counted;
  - same-title records get separate rows;
  - output vectors have norm 1 ± 1e-5.
- [x] **Step 2: Implement until green.**
- [x] **Step 3: Real run on the seed.** Record in NOTES: runtime, device, throughput, truncated count, and the embeddings file size. Sanity check: cosine of `fandom_449281` vs `fandom_372805` is printed, not asserted.
- [x] **Step 4: Commit and push.** (`feat(pipeline): incremental embedding with text-hash cache`)

### Task 5: Shared cluster helpers

**Files:**
- Create: `pipeline/clusterlib.py`, `tests/test_clusterlib.py`

**Interfaces (all pure numpy/scipy/sklearn, no UMAP):**
- `fit_kmeans(X, k, seed=42) -> (labels, centroids_unit)` uses `KMeans(n_init=10)`, then L2-normalises the centroids.
- `assign_nearest(X, centroids_unit) -> labels` assigns by cosine.
- `top_neighbors(X, k=10, block=2048) -> np.ndarray[int32] (n,k)`: exact cosine, excludes self, works in blocks so memory stays under ~200 MB at n=20.8K.
- `leaders(X, labels, centroids_unit) -> dict[int,int]` returns cluster → row nearest its centroid. An empty cluster is absent.
- `silhouette_cosine(X, labels, sample=10000, seed=42) -> float`.
- `procrustes_align(new, old) -> new_aligned`: rotation, uniform scale and translation, fitted on shared rows only.
- `size_stats(labels, k) -> dict` returns min/median/max, a count of empty clusters, and a count under 20.

- [x] **Step 1: Write failing tests on small synthetic blobs** (4 well-separated Gaussian blobs on the unit sphere). Cover:
  - kmeans recovers the blobs;
  - `assign_nearest` agrees with kmeans labels on training points;
  - `top_neighbors` matches brute force and never includes self;
  - `procrustes_align` recovers a known rotation and scale to 1e-6;
  - silhouette lands in the expected range;
  - an empty cluster doesn't crash `leaders` or `size_stats`.
- [x] **Step 2: Implement until green. Commit and push.** (`feat(pipeline): cluster helpers`)

### Task 6: Cluster — fit mode and persisted model

**Files:**
- Create: `pipeline/cluster.py`, `pipeline/galaxy_model.py`, `tests/test_cluster_fit.py` (marked `@pytest.mark.skipif(no umap)` so the `ci` group skips it)

**Interfaces:**
- `galaxy_model` saves and loads `data/model/galaxy/`:
  - `model.json`: `k`, `seed`, `fit_run_id`, `embedding_model`, the embeddings sha, `cluster_keys` (list, index = KMeans label), `silhouette`;
  - `centroids.npy`;
  - `umap2d.pkl`, `umap3d.pkl`;
  - `layout.parquet`: id, cluster_key, x2, y2, x3, y3, z3.

  Saving goes to a temp dir and then renames it, so a crash never leaves half a model. The previous model is kept as `data/model/galaxy.prev/` for alignment and carry-over.
- `cluster.fit(X, ids, k, prev_model | None) -> FitResult`. It runs, in order:
  1. KMeans.
  2. UMAP 2D and 3D (`metric="cosine"`, `random_state=42`, `n_neighbors=15`, `min_dist=0.1`).
  3. Procrustes alignment to `prev_model`'s layout on shared ids, if a previous model exists. On by default.
  4. Neighbours, leaders, silhouette and size stats.

  Cluster keys are left unassigned here. Task 8 assigns them.
- `python -m pipeline.cluster --mode fit [--k N] [--run-id ID] [--no-save]`. `--no-save` writes to `data/runs/<run_id>/model/` instead of the live model, without the ~240 MB UMAP pickles; Task 10 uses it.

- [x] **Step 1: Write failing tests on 300 synthetic points** (only where umap is installed). Cover:
  - layout shape and finiteness;
  - the same seed gives an identical layout;
  - save then load round-trips exactly;
  - a second fit with a slightly perturbed X, aligned to the first, gives a mean point displacement below that of the unaligned fit;
  - a crash mid-save, simulated by raising inside save, leaves the old model intact.
- [x] **Step 2: Implement until green.** Record the umap-learn version and the time for one fit at n=20.8K in NOTES.
- [x] **Step 3: Commit and push.** (`feat(pipeline): cluster fit mode with persisted model`)

### Task 7: Cluster — assign mode

**Files:**
- Modify: `pipeline/cluster.py`
- Create: `tests/test_cluster_assign.py`

**Interfaces:**
- `cluster.assign(X, ids, model) -> AssignResult`:
  - Unchanged ids (same id and the same text_hash as when the model last saw them) keep their stored `cluster_key` and coordinates **exactly**.
  - New or changed ids get `assign_nearest` and `umap2d/3d.transform`.
  - Ids absent from the snapshot are dropped (with carry-forward, that means only manual removals).
  - Neighbours are recomputed over all vectors.
  - Centroids (unit mean of current members) and leaders are recomputed. Keys, names and colours are untouched.
  - The result reports `drift_share` = (added + reassigned) / n since the fit. Above `DRIFT_RECOMMEND = 0.15` it logs "re-cluster recommended". It never fails on that.

  `layout.parquet` gains a `text_hash` column so assign can tell unchanged from changed. Task 6 writes it.
- `python -m pipeline.cluster --mode assign` is the default mode. Plan 6's DAG only uses this mode.

- [x] **Step 1: Write failing tests.** These use a fake model with identity "transform" functions, so they don't need umap. Cover:
  - unchanged creators' rows are byte-identical before and after;
  - a new creator lands in the nearest cluster;
  - a removed creator is gone;
  - cluster keys, names and colours are unchanged;
  - `drift_share` is computed correctly;
  - a cluster whose members all left keeps its key and centroid, and has no leader.
- [x] **Step 2: Implement until green. Commit and push.** (`feat(pipeline): cluster assign mode keeps identity fixed`)

### Task 8: Cluster names, keys and colours

**Files:**
- Create: `pipeline/names.py`, `pipeline/palette.py`, `tests/test_names.py`, `tests/test_palette.py`

**Interfaces:**
- `names.bootstrap_from_seed(labels, ids, seed_names: dict[id,str], threshold=0.2)` returns `dict[label, name|None]`.
  - It uses the Jaccard overlap between each new cluster's id set and each seed-name id set.
  - It runs `linear_sum_assignment` on −Jaccard, which uses each name at most once.
  - A matched pair below `threshold` is discarded (left unnamed).

  The threshold is the builder's call (spec). Report the Jaccard distribution at Checkpoint 2 so the owner can judge it.
- `names.carry_over(new_centroids, prev_centroids, prev_keys, min_cos=0.8) -> dict[label, key|None]`: cosine + Hungarian. Fit mode only.
- `names.assign_keys(...)`:
  - matched clusters inherit a key (and so a name and colour);
  - unmatched clusters get new keys `c{next_int:03d}`.

  Keys are never reused after a cluster disappears.
- **Registry** `data/cluster_registry.json`: `{key: {name, colour, source: "seed"|"owner"|"carried"|"placeholder"}}`.
  - Owner names in `data/cluster_names.json` (`{key: name}`) always win.
  - An unnamed cluster gets the placeholder: top 3 TF-IDF keywords over member titles and descriptions, e.g. `"roblox · obby · tycoon"`.
- `names.write_review(run_dir, ...)` writes:
  - `unnamed_clusters.md`;
  - `naming_packs/<key>.md` for each unnamed cluster: key, size, the 30 titles nearest the centroid, 1-line bio snippets, the top 10 TF-IDF keywords, and a ready-to-paste prompt for a free chatbot.

  It never calls an LLM.
- `palette.new_colours(existing: list[hex], n_new) -> list[hex]` chooses greedily from a dense candidate set in OKLCH. It keeps lightness 0.62–0.82 for a dark background, takes chroma at the gamut limit, and maximises the minimum OKLab distance to all existing colours. It is deterministic. `palette.min_distance(colours) -> float`.

- [x] **Step 1: Write failing tests.** Cover:
  - bootstrap uses each name at most once, even when two clusters both overlap one name most;
  - an overlap below the threshold gives None;
  - carry-over maps a permuted copy of the centroids back to the same keys;
  - new keys never collide with old or retired ones;
  - owner names override seed names;
  - the placeholder comes from keywords;
  - `palette.new_colours(existing=[], 200)` gives 200 unique valid hex colours with a reported minimum distance;
  - adding 5 colours to an existing 120 never changes the 120.
- [x] **Step 2: Implement until green.** Wire it into `cluster.py`: fit mode with no previous model uses `bootstrap_from_seed`, and fit mode with a previous model uses `carry_over`. Assign mode reads the registry only.
- [x] **Step 3: Commit and push.** (`feat(pipeline): stable cluster keys, seed name bootstrap, colours`)

### Task 9: Build artifacts

**Files:**
- Create: `pipeline/build_artifacts.py`, `tests/test_build_artifacts.py`

**Interfaces:**
- `python -m pipeline.build_artifacts [--out data/artifacts/galaxy]` reads the current snapshot, embeddings, model and registry. It writes `data/artifacts/galaxy/<version>/`:
  - **Site:**
    - `manifest.json`: `version`, `built_at`, `creators`, `clusters`, `embedding_model`, `metrics` (silhouette, sizes), `files` (relative paths and byte sizes).
    - `nodes.json`: columnar arrays `{id:[], title:[], cluster:[], x2:[], y2:[], x3:[], y3:[], z3:[]}`. Coordinates are rounded to 3 decimals, and `cluster` is the integer position in `clusters.json`.
    - `neighbors.json`: `{id: [10 ids]}`.
    - `clusters.json`: `[{key, name, colour, size, leader_id, cx2, cy2, cx3, cy3, cz3}]`.
    - `details/cluster_<key>.json`: `{id: {bio ≤ 500 chars, source_url, youtube_url, thumbnail}}`.
  - **Worker:**
    - `worker/index.bin`, with rows **ordered by cluster**;
    - `worker/centroids.bin`;
    - `worker/meta.bin`, with records `{id, title, cluster: name, url: source_url, snippet: bio ≤ 400 chars}`;
    - `worker/index_manifest.json`: `{version, n, dim, k, model}`, the shape `worker/src/index_loader.ts` validates.

  All four go through `pipeline/index_format.py`.
- At the end it prints a size table: each file's raw size and gzip size, the site total, and the Worker bundle total. It warns if the Worker bundle is over 20 MB (issue #1) and fails if it is over 60 MiB.
- Bios are cut on word boundaries and end with `…`. The CC BY-SA source URL is always present.

- [x] **Step 1: Write failing tests** on a 12-creator build from a tiny fake model:
  - every id appears once in `nodes`;
  - `neighbors` values are all known ids;
  - `index.bin` row order matches cluster offsets;
  - reading meta row r gives the id that `index.bin` row r belongs to;
  - the `TARGET`/`Target` pair both appear in `nodes` and in meta as distinct ids;
  - `pipeline.search.two_stage_search` on the built index finds an exact-copy query as top-1;
  - bios respect their length caps without splitting a UTF-8 character;
  - the manifest's file sizes match the disk.
- [x] **Step 2: Implement until green.**
- [x] **Step 3: Cross-check against the Worker.** Copy one real build's `worker/*` into a temp dir and run the worker's vitest `validateLoaded` logic. Or check the same invariants in Python (`n`, `dim`, `k`, `offsets[k] == n`). This proves the TS loader accepts it.
- [x] **Step 4: Commit and push.** (`feat(pipeline): versioned galaxy artifact build`)

### Task 10: Cluster-count comparison (60 / 120 / 200)

**Files:**
- Create: `pipeline/compare_k.py`, `tests/test_compare_k.py` (report formatting only, with fake fit results)

**Interfaces:**
- `python -m pipeline.compare_k [--ks 60,120,200] [--run-id ID]` runs `cluster.fit(..., save=False)` once per k on the same embeddings and seed, and bootstraps names for each.
- It writes `data/runs/<run_id>/compare_k.md` with, per k:
  - silhouette;
  - size min/median/max and the counts of empty and under-20 clusters;
  - seed names matched, and the Jaccard distribution of the matches;
  - unnamed count;
  - fit runtime;
  - 5 example clusters: name, size, and 8 titles nearest the centroid.

  The same seed and data give identical numbers on a re-run.
- It also writes, per k, the `unnamed_clusters.md` and naming packs, so the owner sees the naming workload of each choice.

- [x] **Step 1: Write the report-format test, then implement.**
- [x] **Step 2: Run it for real on the seed embeddings.** Record the per-k runtime in NOTES.
- [x] **Step 3: Commit and push.** (`feat(pipeline): cluster-count comparison report`)

### Task 11: Makefile, end-to-end run, CI

**Files:**
- Modify: `Makefile`, `README.md` (commands only, where they are now true)

- [x] **Step 1: Add Makefile targets.**
  - `seed`, `embed`, `cluster` (assign), `recluster` (fit, never scheduled), `compare-k` and `build`.
  - `pipeline` runs embed → cluster → build (skipping quickly when the snapshot sha256 is unchanged since the last build), without eval/gate (Plan 5) and without publish.
  - Every target calls `uv run python -m …`.
- [x] **Step 2: Fresh end-to-end run on the seed.**
  1. Move `data/model`, `data/embeddings` and `data/cluster_registry.json` aside first, with `mv` to `data/_before_plan2_run/`. Never delete them.
  2. Run `make seed embed`, then `make recluster` with the k chosen at Checkpoint 2 (use 120 provisionally until then), then `make build`.
  3. Time each step.
  4. Run `make pipeline` a second time with no changes. It must finish fast and report "nothing changed".
- [x] **Step 3: Check CI.** `.github/workflows/test.yml` already exists from Plan 1. Make sure every new test file either needs only the `ci` group or skips cleanly without torch and umap. Then confirm the run is green on GitHub (`gh run list --limit 1`).
- [x] **Step 4: Run `make test`. Commit and push.** (`build: pipeline make targets and CI`)

### Task 12: 🛑 Checkpoint 2 — report to the owner

- [x] **Step 1: Run 15 sanity checks.** Pick 15 well-known creators across different niches. For each, list its 10 neighbours and its cluster name, and mark whether they look right (✓/✗) with a one-line reason. Include the `TARGET`/`Target` pair.
- [x] **Step 2: Write the report in plain language.** It covers:
  - runtime per step;
  - device used;
  - creators truncated;
  - artifact sizes, site and Worker bundle, raw and gzip;
  - the `compare_k.md` table;
  - the unnamed-cluster list for each k;
  - the sanity checks.

  It must explain:
  - **what silhouette measures**: how much closer each creator is to its own cluster than to the next nearest one, on a scale from −1 to 1;
  - **why text clusters score low** (typically ~0.03–0.10): topics overlap and the embeddings are high-dimensional, so a low number is normal and not a failure;
  - **what to trade off**: more clusters give more specific names and colours but more naming work and smaller clusters. Fewer clusters give broader, duller groups (an anti-goal).
- [x] **Step 3: Ask the owner to do three things:**
  1. pick the cluster count;
  2. review the names in `data/cluster_registry.json` and the naming packs, putting fixes in `data/cluster_names.json`;
  3. say whether the 0.2 Jaccard threshold looks right.
- [x] **Step 4: After the owner answers:** (k=120; placeholder names kept; threshold stays 0.2 for now, owner wants it stricter later; #5 after Plan 3)
  1. Set `N_CLUSTERS` in `.env.example`, as a comment showing the chosen default. The owner edits `.env`.
  2. Run `make recluster build` with the chosen k.
  3. Record the chosen fit run's silhouette in NOTES as the baseline for Plan 5's gate floor.
  4. Commit and push.
- [x] **Step 5: Write Plan 3** (static site + home page + map-only publish) and ask the owner to review it.
