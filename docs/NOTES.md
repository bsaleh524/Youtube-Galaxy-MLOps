# Notes: verified facts and decisions

Every external fact the build relies on is listed here with its source and the date it was checked. Free-tier numbers and model IDs change, so re-check anything older than a few months before relying on it.

## Verified external facts

| Fact | Value | Source | Checked |
|---|---|---|---|
| Workers test setup | `vitest@^4.1` + `@cloudflare/vitest-plugin` (installed 1.8.2) via `cloudflareTest()` in `vitest.config.ts`; tests import `exports`/`env` from `cloudflare:workers`. Wrangler 4.162.0. npm needs `install-scripts approve esbuild workerd` (recorded in `worker/package.json` `allowScripts`). | https://developers.cloudflare.com/workers/testing/vitest-integration/write-your-first-test/ | 2026-11-15 |
| Airflow version | **3.4.0** (latest on PyPI, released 2026-11-06; supports Python 3.11–3.14) | https://pypi.org/project/apache-airflow/ | 2026-11-15 |
| Airflow install | `pip install "apache-airflow==${V}" --constraint https://raw.githubusercontent.com/apache/airflow/constraints-${V}/constraints-${PY}.txt` (we use `uv pip install` into `.venv-airflow`) | https://airflow.apache.org/docs/apache-airflow/stable/start.html | 2026-11-15 |
| `airflow standalone` | Runs API server, scheduler, DAG processor, triggerer on SQLite; dev only. Admin password saved in `$AIRFLOW_HOME/simple_auth_manager_passwords.json.generated`. Launches components as `airflow` subprocesses from PATH, so the venv's bin must be on PATH (found by testing). | https://airflow.apache.org/docs/apache-airflow/stable/start.html | 2026-11-15 |
| Airflow 3 DAG imports | `from airflow.sdk import dag, task` (not 2.x `airflow.decorators`) | https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/taskflow.html | 2026-11-15 |
| Workers Free limits | CPU **10 ms**/request; **100,000** requests/day (reset 00:00 UTC); script 64 MiB uncompressed (no compressed limit); memory **128 MB**/isolate; 50 subrequests/request; startup 1 s | https://developers.cloudflare.com/workers/platform/limits/ | 2026-11-15 |
| Workers static assets | 20,000 files per version; **25 MiB** per file. Docs don't say whether asset reads via the binding count toward request limits. | https://developers.cloudflare.com/workers/platform/limits/ | 2026-11-15 |
| Assets binding | wrangler `assets: {directory, binding: "ASSETS", run_worker_first: true}`; code reads `env.ASSETS.fetch("https://assets.local/<path>")` (only the pathname matters) | https://developers.cloudflare.com/workers/static-assets/binding/ | 2026-11-15 |
| KV (free) | 100,000 reads/day; 1,000 writes/day; max value **25 MiB**; 1 GB storage | https://developers.cloudflare.com/kv/platform/limits/ | 2026-11-15 |
| R2 | Not evaluated further: the pricing page doesn't say whether a payment method is needed, and static assets already fit | https://developers.cloudflare.com/r2/pricing/ | 2026-11-15 |
| bge-small on Workers AI | `@cf/baai/bge-small-en-v1.5`; input `text` (string or array); `pooling`: `mean` (default) or `cls` (recommended); cls and mean embeddings are **not compatible**; 512 tokens max per input; 384-dim output in `data[]` | https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/ | 2026-11-15 |
| Workers AI free quota | **10,000 Neurons/day** on Free, reset 00:00 UTC; beyond that requests fail with an error (no overage on Free) | https://developers.cloudflare.com/workers-ai/platform/pricing/ | 2026-11-15 |
| bge-small Neuron cost | 1,841 Neurons per 1M input tokens, so a ~20-token query costs ~0.04 Neurons. Embedding cost is negligible. | https://developers.cloudflare.com/workers-ai/platform/pricing/ | 2026-11-15 |
| Small LLM Neuron costs (per 1M in/out) | llama-3.1-8b-instruct-fp8-fast 4,119/34,868; mistral-7b-instruct-v0.1 10,000/17,300; granite-4.0-h-micro 1,542/10,158; llama-3.2-3b 4,625/30,475 | https://developers.cloudflare.com/workers-ai/platform/pricing/ | 2026-11-15 |
| LLM deprecations | On **2026-11-20**: `llama-3.2-1b-instruct`, `llama-3.2-3b-instruct`, `llama-3.1-8b-instruct-fp8` and 13 others are retired (HTTP 410, code 5028). Not listed: mistral-7b, granite-4.0-h-micro, bge-small. Suggested small replacements: `gemma-4-26b-a4b-it`, `qwen3.8-27b`. | https://developers.cloudflare.com/changelog/post/2026-11-05-planned-model-deprecations/ | 2026-11-15 |
| Workers AI REST | `POST https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/ai/run/<model>` with `Authorization: Bearer $TOKEN` | https://developers.cloudflare.com/workers-ai/models/llama-3.2-3b-instruct/ | 2026-11-15 |
| Rate Limiting binding | `ratelimits: [{name, namespace_id, simple: {limit, period}}]`; period must be 10 or 60 s; per-location, eventually consistent (a loose filter). **Free-plan availability not stated in the docs.** Verify on first deploy; fall back to an in-isolate limiter. | https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/ | 2026-11-15 |
| CPU time measurement | No per-request CPU in `wrangler tail` docs. Use the dashboard "CPU Time per execution" quantile chart, or the GraphQL Analytics API (`https://api.cloudflare.com/client/v4/graphql`, dataset `workersInvocationsAdaptive`, `quantiles { cpuTimeP50 cpuTimeP99 }`). Higher quantiles can exceed the limit without errors because of rollover. | https://developers.cloudflare.com/workers/observability/metrics-and-analytics/ ; https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-workers-metrics/ | 2026-11-15 |

## Decisions

- 2026-11-15 — MLflow runs on port **5001**, because macOS AirPlay Receiver uses 5000.
- 2026-11-15 — **Index delivery: Workers static assets** (first in the preference order). `index.bin` (~8 MB) is well under the 25 MiB per-file limit, needs no KV writes or payment method, and ships atomically with each `wrangler deploy`, so the Worker and its index version can never drift apart. The Worker reads the files via the `ASSETS` binding with `run_worker_first: true` and caches the parsed typed arrays in module scope. KV, R2 and bundling were not needed.
- 2026-11-15 — **CPU measurement method:** deploy, drive load with `scripts/spike_load.sh`, then read `cpuTimeP50/P99` from GraphQL `workersInvocationsAdaptive` (plus the dashboard chart). No P95 field exists, so we report P50 and P99, and P99 is the stricter one.
- 2026-11-15 — **LLM for `ask`:** decided later (Plan 7). The llama-3.2 small models are retired on 2026-11-20. Current small candidates still listed: `@cf/meta/llama-3.1-8b-instruct-fp8-fast` (status to confirm in the catalog), `@cf/ibm-granite/granite-4.0-h-micro` (cheapest), `@cf/mistral/mistral-7b-instruct-v0.1`. Rough budget at ~2K input + 400 output tokens: granite ≈ 7 Neurons/answer (~1,400/day); llama-8b-fast ≈ 22 Neurons (~450/day); mistral ≈ 27 Neurons (~370/day). Re-verify all of this in Plan 7.
- 2026-11-15 — **Local benchmark (Node 24 on the dev Mac, NOT the Workers runtime)** on the 20,800×384 synthetic index with 120 clusters (`npm run bench` in `worker/`): two-stage search mean **1.04 ms**, p99 **1.23 ms**; brute force mean 8.04 ms, p99 22.9 ms. Two-stage is ~7.8× faster. Brute force alone would use most or all of the 10 ms free-plan CPU budget. Deployed numbers come at Checkpoint 1.

## Checkpoint 1 measurements (2026-11-17, deployed free-plan Worker, synthetic 20,800×384 index, 120 clusters)

- **Deploy:** `https://galaxy-chat.galaxy-worker.workers.dev`, index served from static assets. A brand-new workers.dev subdomain failed TLS handshakes for ~2 minutes after the first deploy (certificate provisioning), then worked.
- **Embedding parity** (`pipeline.parity_check`, 20 passages + 10 prefixed queries): `pooling=cls` min **1.00000**, mean 1.00000 → PASS. Control `pooling=mean`: min 0.88974, mean 0.92884 → FAIL. CLS is mandatory.
- **End-to-end `/spike/embed-search`** (Workers AI embed + two-stage): works; probed 8 clusters / 1,522 candidates.
- **Server CPU per request** (GraphQL `workersInvocationsAdaptive`, `scripts/worker_cpu.py`; needs token permission Account Analytics: Read). 0 errors in ~1,200 requests.

| Window (UTC) | Requests | CPU p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|---|
| 01:28 (run 1, first minute) | 289 | 2.26 ms | 9.86 | 35.95 | 52.03 |
| 01:45 (run 2, first minute) | 199 | 4.36 | 24.11 | 49.65 | 55.32 |
| 01:46 (run 2, warm) | 415 | 1.80 | 5.07 | 18.43 | 27.88 |
| 01:47 (run 2, warm, partial) | 88 | 1.76 | 3.34 | 12.14 | 12.14 |

  Median fits easily (edge ≈ 1.7× the local Node benchmark). The tail shrinks as isolates warm (index load + unoptimised JIT on first requests), but even warm p99 is 12–18 ms, above the 10 ms budget. Client latency p50 ~118 ms (network-dominated).

### Option 1 (allocation-free top-k, unrolled dot product), redeployed 2026-11-17 02:42 UTC

Local mean 0.64 → 0.58 ms. Deployed, 900 requests, 0 errors:

| Window (UTC) | Requests | CPU p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|---|
| 02:42 (first requests after deploy) | 11 | 29.74 ms | 46.97 | 49.98 | 49.98 |
| 02:43 | 391 | 2.23 | 5.15 | 25.27 | 32.67 |
| 02:44 | 426 | 1.94 | 4.90 | 47.41 | 76.65 |
| 02:45 (partial) | 88 | 2.50 | 14.30 | 28.96 | 28.96 |

**Conclusion:** the tail is not GC in the search loop. Requests landing on a fresh isolate cost ~30–50 ms CPU,
which is the cold load of the ~19 MB index from static assets (fetch + arrayBuffer). Cloudflare keeps
starting new isolates during a run, so ~1–2% of requests pay it and set p99. Warm search is ~2 ms.
Fixes must target cold-load CPU (smaller index/meta, or moving the load out of the request path), not search.

### Option A: index bundled as Data modules and warmed at startup (2026-11-17)

Version c007311c. The index is bundled into the script (11.1 MB, 7.8 MB gzipped, under the 64 MiB limit), parsed at global scope, and warmed with 20 searches. The deploy passed the 1 s startup limit. Same `spike_load.sh` run as before: 900 requests, 04:05:48–04:08:03 UTC, 0 errors.

| Minute (UTC) | Requests | p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|---|
| 04:05 (cold) | 36 | 2.06 ms | 3.74 ms | 4.41 ms | 4.41 ms |
| 04:06 | 404 | 2.13 ms | 3.38 ms | 14.1 ms | 30.3 ms |
| 04:07 | 438 | 1.89 ms | 3.35 ms | 22.6 ms | 32.8 ms |
| 04:08 | 24 | 2.23 ms | 13.1 ms | 29.1 ms | 29.1 ms |

The cold first minute went from p50 29.7 ms to 2.06 ms, and p90 is lower in every minute. The p99 is still over 10 ms (14–29 ms). Wall time about equals CPU time on those requests, so they are spending the time on CPU, not waiting on I/O. The cause is not known yet. The two candidates are startup CPU being billed to an isolate's first request, and GC pauses. The next step is to tag each request with its per-isolate request number and read per-request CPU from Workers Logs.

### Checkpoint 1 decision (2026-11-17)

**GO.** The owner chose to defer the p99 tail to a polish step: [issue #1](https://github.com/bsaleh524/Youtube-Galaxy-MLOps/issues/1). The reasons:
- p50/p90 are well under budget.
- All ~3,000 spike requests succeeded.
- The synthetic index will be replaced anyway.

Remeasure once the real index is deployed (Plan 4), and escalate if CPU-limit errors appear.

Final Checkpoint 1 results:
- Index delivery: bundled Data modules.
- Embedding parity: PASS (CLS pooling).
- CPU: p50 ~2 ms, p90 ~3.5 ms, p99 open (issue #1).
- LLM choice: deferred to Plan 7.

### Records are wiki pages, not channels (owner note, 2026-11-17)
Some Fandom pages cover several channels by the same creator (e.g. anything4views and Cold Ones). Each page stays one record (`fandom_{pageid}`), with the first channel link in `youtube_url`. Channels sharing a page are related, which is fine for clustering. Possible polish: keep every channel link ([issue #2](https://github.com/bsaleh524/Youtube-Galaxy-MLOps/issues/2)).

## Plan 2

### Task 1: seed snapshot (2026-11-17)
`uv run python -m pipeline.seed` took 1.7 s.
- **Snapshot:** `data/raw/snapshots/20261118-041529/`, 20,807 records. sha256 of `creators.json`: `19e7a79c1ecddfe934f13ee6c332126d14cf8bd862d8956919c91e9e292583f2`.
- **Source JSON:** 0 duplicate ids, 0 malformed ids. All records have the six schema keys. 46 have `youtube_url: null`, which is allowed.
- **Seed names** (`data/seed/seed_cluster_names.json`): every snapshot id has a name, with no ids on either side missing from the other. 120 distinct names.
- **Same-title pair:** `TARGET` (`fandom_449281`, "Mobile Gaming (Clash/Brawl)") and `Target` (`fandom_372805`, "Government & Public Services") stay separate records with separate names.

### Task 2 step 1: Fandom robots.txt and terms (2026-11-17) — 🛑 flagged to owner
- **Live site:** `youtube.fandom.com/robots.txt` and `www.fandom.com/terms-of-use` now return a Cloudflare bot challenge or a 403/402 to non-browser clients. `api.php` still answers 200 JSON to the generic UA. Tested with one `siteinfo` call and one `prop=info` call for pageids 449281|372805.
- **robots.txt**, read from the Wayback copy of 2026-08-11 (`web.archive.org/web/20260811004727/https://youtube.fandom.com/robots.txt`):
  - `User-agent: *` has `Allow: /api.php?action=` and `Disallow: /wiki/Special:` (plus `User:`, `Template:` and `Help:` pages).
  - GPTBot, CCBot, SemrushBot, serpstatbot and ImagesiftBot are fully disallowed.
- **Terms of Use**, read from the Wayback copy of 2026-11-15 (`web.archive.org/web/20261115004908/https://www.fandom.com/terms-of-use`). Quoted:
  - "not use any robot, spider, scraper or other automated means to access the Services for any purpose without our express written permission";
  - "Use any robot, spider, site search and/or retrieval application, or other device to scrape, extract, retrieve or index any portion of the content";
  - "Without our express, prior written consent, use or copy the content for the development of any software program, including, but not limited to, training a machine learning or artificial intelligence (AI) system".

  The content clause opens with "Except as expressly permitted by the Company (for example with respect to the use of text content … as set forth at our licensing page)". That points to the CC BY-SA licence on wiki text. The automated-access clause has no such exception.
- **Conclusion:** robots.txt allows API access. The Terms forbid automated access without written permission. The scraper (Tasks 2–3) is on hold until the owner decides.

### Data source decision (2026-11-18)
- **Fandom dump:** `https://s3.amazonaws.com/wikia_xml_dumps/y/yo/youtube_pages_current.xml.7z`, 66.6 MB, Last-Modified 2025-10-27, storage class `DEEP_ARCHIVE`. A GET returns `InvalidObjectState`, so it can't be downloaded, and it is older than the seed (2025-12-13).
- **Owner decision:**
  - no scraper (Plan 2 Tasks 2–3 dropped);
  - run frozen on the seed snapshot;
  - the owner has asked Fandom for a fresh dump;
  - build a dump importer once one exists ([issue #4](https://github.com/bsaleh524/Youtube-Galaxy-MLOps/issues/4)).

### Task 4: embedding (2026-11-18)
`uv run python -m pipeline.embed`, on Apple MPS, with `BAAI/bge-small-en-v1.5` (normalised, CLS, no prefix for passages).
- **First run:** encoded 20,807 creators in 172 s (121/s), 3 min 8 s wall time including model load.
- **Second run with nothing changed:** encoded 0, reused 20,807, 8.6 s wall time (mostly loading torch).
- **Truncation at 2,000 chars:** 5,319 texts (26%) were cut, on word boundaries.
- **Token counts** (bge tokenizer, 1,000-text sample): p50 280, p90 462, max 540. 0.8% of texts are over 512 tokens and lose their last few tokens to the model's own cutoff, which is acceptable.
- **Files:** `embeddings.npy` 32.0 MB (20,807 × 384 float32), `rows.json` 1.8 MB.
- **Checks:**
  - every vector has norm 1 ± 2e-7;
  - TARGET vs Target cosine is 0.727, so they are separate rows with different texts;
  - Markiplier's nearest neighbours are Ethan Nestor, LS Mark, ImMarksman and Jacksepticeye;
  - MrBeast's nearest neighbours include Karl, MrBeast Memes and MrBeast Burger.

### Task 5: cluster helpers (2026-11-18)
scikit-learn 1.9.0 and scipy 1.17.1 are now also in the `ci` group (no torch), so CI tests the helpers. Preview on the real 20,807 × 384 embeddings, run on the M-series CPU:
- **Exact top-10 neighbours:** 4.9 s.
- **KMeans k=120** (`n_init=10`, seed 42): 23.7 s. Cluster sizes: min 16, median 157.5, max 448, 0 empty, 1 under 20.
- **Silhouette** (cosine, 10K sample): **0.014**, computed in 0.9 s. That is below the spec's "typical 0.03–0.10" for text. It's a preview only: Task 10 compares k = 60/120/200 and Checkpoint 2 explains the number.

### Task 6: cluster fit mode (2026-11-18)
- **Versions:** umap-learn 0.5.12, numba 0.67.0, pynndescent 0.6.0.
- **Determinism fix:** KMeans on float32 input gave different labels on repeated runs in the same process with the same seed. The likely cause is sklearn's OpenMP reductions running in a different order; 8 threads were in use. Fitting on float64 gave identical labels over 3 repeats and took 6.6 s instead of 25 s. `clusterlib.fit_kmeans` now casts to float64. Two separate `pipeline.cluster --mode fit --k 120` runs then gave byte-identical labels, centroids, 2D/3D layouts and neighbours.
- **Real fit, k=120:** 20,807 creators, about 47 s of compute plus about 25 s of start-up and loading. Stages: kmeans 8.1 s, UMAP 2D 20.2 s, UMAP 3D 11.1 s, neighbours 5.1 s, silhouette 0.8 s.
  - Silhouette 0.0120.
  - Sizes: min 43, median 173, max 440, 0 empty, 0 under 20.
- **Model size:** about 240 MB per saved model. `umap2d.pkl` is 125 MB and `umap3d.pkl` 113 MB, because UMAP keeps its training data and neighbour index for `.transform`. `layout.npz` is 7.4 MB and centroids 184 KB. With `galaxy.prev` kept, that is about 0.5 GB on disk. This affects backup sizing (issue #3). Task 10's comparison runs should not pickle reducers.

## 2026-11-18 — Task 7: cluster assign mode

- `python -m pipeline.cluster` now defaults to `--mode assign` (weekly). Unchanged creators (same id and text hash) keep cluster and coordinates byte-for-byte; new/edited ones go to the nearest centroid and are placed with the saved UMAP reducers; removed ones are dropped. Neighbours and centroids (unit mean of members; an emptied cluster keeps its old centroid) are recomputed. Keys/names/colours untouched.
- Text hashes live in `layout.npz` (not a parquet, as the plan first said). A new `from_fit` column marks rows placed by the last fit; `drift_share` = share of rows *not* from the fit, so it is cumulative since the fit and handles removals. Over 0.15 it logs "re-cluster recommended" and still succeeds.
- Real-data smoke (scratch, not saved): fit k=120 on 20,757, then assign with 50 new, 20 re-hashed, 10 removed → 12.6 s; 20,727 unchanged rows byte-identical; all 20 re-hashed (same vectors) kept their cluster and moved ~0.54 units on a ~10-unit layout (UMAP `transform` vs `fit_transform` jitter, expected).
- A model saved with `--no-save` (no reducers) can't place new creators; assign then fails with a clear message, unless nothing is new.

## 2026-11-18 — Decision: keep creators that vanish from the wiki

Owner decision. When a fresh dump no longer contains a page we already have, the importer (issue #4) carries the record forward with its last known text and `missing_from_wiki_since: <date>`, and the site marks it "no longer on the wiki" (the CC BY-SA source link would be dead). A manual list `data/removed_ids.txt` drops pages deleted for good reason (spam, duplicates). Embed and cluster need no change: they process whatever the snapshot holds. Also confirmed: edited creators moving a little on re-placement is fine; unchanged creators keep their exact spot so the map doesn't shuffle weekly.

## 2026-11-18 — Task 8: cluster keys, names, colours

- **Registry location:** `data/model/galaxy/registry.json`, saved atomically *with* the model (not `data/cluster_registry.json` as the plan first said), so keys, names and colours can never disagree with the centroids they belong to, and `galaxy.prev/` carries its own registry for carry-over. Shape: `{"next_key": N, "clusters": {key: {name, colour, source, active, size, keywords}}}`. Retired keys stay in it (`active: false`), so keys are never reused and their colours are never handed to a new cluster.
- **Owner names:** `data/cluster_names.json` (`{"c007": "Minecraft PvP Servers"}`) always wins. Build (Task 9) should also overlay it so renames show without a re-fit.
- **Placeholder keywords:** plain cluster-level TF-IDF picked rare proper nouns ("vaultboy · bassnectar · damyard" for a music cluster). Replaced with member-level lift: score = p_c·log(p_c/p) on the share of members whose text contains the word, requiring ≥3 members, dropping words in >50% of all texts plus a short wiki-boilerplate list (born, age, note, zones…). Same cluster now reads "music · songs · artists".
- **First live fit (run `20261118-fit-k120`, k=120):** 71 clusters named from the seed, 49 placeholders, 0 duplicate names. One-to-one Jaccard of the seed match: min 0.00, median 0.257, max 0.804; 49 below 0.2. Histogram (bins 0/.05/.1/.15/.2/.25/.3/.4/.5/.6/.9): 23, 14, 9, 3, 9, 9, 17, 16, 10, 10. Lowest accepted matches (0.20–0.23) still look right (e.g. "Spongebob Parodies & YTPs" ↔ spongebob, squarepants, poop). Some placeholders show embedding quirks worth discussing at Checkpoint 2, e.g. a cluster of creators sharing the first name Alex ("alex · alexander · alexandra").
- **Colours:** 120 at OKLab min pairwise distance 0.040 (60 → 0.057, 200 → 0.030). With 120 clusters some pairs are close; they rarely sit next to each other on the map, but say so at Checkpoint 2.
- An assign run on the fresh model: 20,807 unchanged, layout, keys and registry byte-identical, 5.1 s. The model re-saved by assign is 233 MB vs 245 MB for the fitted one (pickle of a loaded UMAP is smaller), but `transform` output is identical.

## 2026-11-18 — Decisions: name-leak deferred, naming stays manual

- Cluster `c071` is grouped by first name (77 of 83 creators are "Alex*"), because the wiki's bio opening ("Real Name (born …), better known online as …") is a big share of the ~512 tokens the embedding model reads. Only `c071` clearly, `c060` partly. Owner: keep the clustering as is for now; fix later by stripping the opening before embedding — [issue #5](https://github.com/bsaleh524/Youtube-Galaxy-MLOps/issues/5).
- Naming stays manual (naming packs → paste into Gemini → `data/cluster_names.json`). Automatic suggestions via free Workers AI are a later feature — [issue #6](https://github.com/bsaleh524/Youtube-Galaxy-MLOps/issues/6).
