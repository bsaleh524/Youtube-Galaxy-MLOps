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
