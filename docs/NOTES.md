# Notes: verified facts and decisions

Every external fact the design depends on, with source and date checked. Free-tier numbers and model IDs
change; re-check before relying on anything older than a few months.

## Verified facts

| Date | Fact | Source |
|---|---|---|
| 2026-11-13 | Apache Airflow stable is **3.4.0** (2.11.x is deprecated); requires Python `>=3.11,!=3.15`. Constraints file `constraints-3.4.0/constraints-3.11.txt` exists. | https://pypi.org/project/apache-airflow/ , https://raw.githubusercontent.com/apache/airflow/constraints-3.4.0/constraints-3.11.txt |
| 2026-11-13 | Airflow 3 task-authoring API is `airflow.sdk` (`dag`, `task`, `Param`); verified importable in `.venv-airflow`. | local check |
| 2026-11-13 | Workers Free: **10 ms CPU/request**, 128 MB memory/isolate, 100,000 requests/day, 50 subrequests/request, 1 s startup time. Network/KV/fetch wait does not count toward CPU time. | https://developers.cloudflare.com/workers/platform/limits/ |
| 2026-11-13 | Worker script size: **64 MiB uncompressed on both Free and Paid**; no compressed-size limit ("only the uncompressed bundle size counts"). Supersedes the older 1 MB/3 MB compressed figures. | https://developers.cloudflare.com/workers/platform/limits/ |
| 2026-11-13 | Workers static assets: 25 MiB per file, 20,000 files per Worker version. | https://developers.cloudflare.com/workers/platform/limits/ |
| 2026-11-13 | Workers AI `@cf/baai/bge-small-en-v1.5`: 384-dim, max 512 input tokens, `pooling` param `mean` (default) or `cls`; the two are **not compatible**. We must pass `pooling: "cls"` to match sentence-transformers. | https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/ |

| 2026-11-13 | Workers static assets: Worker reads them with `env.ASSETS.fetch()`; `assets.run_worker_first: true` makes the Worker handle every request (so the index files are not publicly served). | https://developers.cloudflare.com/workers/static-assets/binding/ |
| 2026-11-13 | KV Free: 25 MiB/value, 100,000 reads/day, 1,000 writes/day, 1 GB storage. (Not needed; static assets won.) | https://developers.cloudflare.com/kv/platform/limits/ |
| 2026-11-13 | R2 free tier: 10 GB-month, 1M Class A / 10M Class B ops, free egress. Pricing page does not say whether a payment method is needed. (Not needed; static assets won.) | https://developers.cloudflare.com/r2/pricing/ |
| 2026-11-13 | Workers AI Free: **10,000 Neurons/day**, resets 00:00 UTC; over the limit, requests **fail with an error** (no billing on Free). bge-small: 1,841 Neurons per M input tokens (a ~20-token query is about 0.04 Neurons). | https://developers.cloudflare.com/workers-ai/platform/pricing/ |
| 2026-11-13 | **Planned deprecation 2026-11-20** for `@cf/meta/llama-3.2-3b-instruct`, `@cf/meta/llama-3.1-8b-instruct-fp8`, `@cf/qwen/qwen3-30b-a3b-fp8` (pages list it). Do not use them. | model pages under https://developers.cloudflare.com/workers-ai/models/ |
| 2026-11-13 | LLM candidates with **no deprecation date listed**: `@cf/google/gemma-4-26b-a4b-it` (MoE, 4B active, 256K ctx, $0.10/$0.30 per M in/out) and `@cf/ibm-granite/granite-4.0-h-micro` (131K ctx, $0.017/$0.112 per M). No licence-acceptance ("agree") step mentioned on either page. | https://developers.cloudflare.com/workers-ai/models/gemma-4-26b-a4b-it/ , https://developers.cloudflare.com/workers-ai/models/granite-4.0-h-micro/ |
| 2026-11-13 | Local `BAAI/bge-small-en-v1.5` in sentence-transformers 6.0.0 uses `pooling_mode: cls` + Normalize, max_seq_length 512. | local check |
| 2026-11-13 | Wrangler 4.x requires Node >= 22.12. Pinned Node 24 in `.nvmrc`. Named exports in the Worker entry module are treated as entrypoints (non-handler exports crash workerd), so helpers live in separate modules. AI binding needs Cloudflare auth even under `wrangler dev`. | `npm view wrangler engines`, local run |

## Phase 1 spike results

**Index delivery: Workers static assets** (preference (a)). Files: `index.bin` 8.07 MB, `meta.bin` 10.5 MB
(400-char bios), `centroids.bin` 0.18 MB, all well under the 25 MiB/file asset limit. Loaded once per isolate
via `env.ASSETS.fetch()` into a module-level promise; ~19 MB resident against the 128 MB isolate limit.
KV/R2/bundling not needed.

**Search CPU (local V8 benchmark, `npm --prefix worker run bench`, synthetic 20,800x384, 120 clusters, Apple
Silicon):** two-stage p50 0.68 ms, p95 0.77 ms, p99 0.85 ms (~1,590 candidates p50, max ~1,970);
brute force p50 7.6 ms, p95 7.9 ms. Cloudflare edge CPUs may be slower than an M-series laptop, so the
deployed number is what counts. *Deployed free-plan measurement: pending (CHECKPOINT 1).*

**Ask-mode Neuron estimate** (~1,300 input + 400 output tokens, Neurons = USD / $0.011 per 1,000):
gemma-4-26b-a4b-it ~23 Neurons/answer (~430 answers/day); granite-4.0-h-micro ~6 Neurons/answer (~1,600/day).

## Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-11-13 | Airflow 3.4.0 in `.venv-airflow`, `airflow standalone`, `AIRFLOW_HOME=.airflow/` (gitignored), DAGs read from `./dags`. | Current stable; constraints-file install keeps it isolated from torch/mlflow pins. |
| 2026-11-13 | MLflow server defaults to port **5001**, not 5000. | macOS AirPlay Receiver binds :5000 by default. |
| 2026-11-13 | `pyproject.toml` uses `[tool.uv] package = false`; modules run in place via `python -m pipeline.<step>`. | Simplest; nothing is distributed. |
| 2026-11-13 | Old `scrapers/Dockerfile` and `scrapers/fandom/run.sh` archived too (they uploaded to Oracle). | Not in the prompt's list, but Oracle/k8s-specific; the scraper is re-copied fresh in Phase 2. |
| 2026-11-13 | Worker index delivered as **static assets** with `run_worker_first: true`. | First preference, fits limits, zero setup, versioned with each deploy. |
| 2026-11-13 | Per-row int8 scale (not one global scale). | Cosine with the float vector stays > 0.999; costs 4 B/row. |
| 2026-11-13 | Probe rule: >= 3 clusters, keep adding until >= 1,500 candidates, cap 12 clusters / 5,000 candidates. | Tunable via `SearchParams`; brute-force agreement measured by the gate. |
