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

## Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-11-13 | Airflow 3.4.0 in `.venv-airflow`, `airflow standalone`, `AIRFLOW_HOME=.airflow/` (gitignored), DAGs read from `./dags`. | Current stable; constraints-file install keeps it isolated from torch/mlflow pins. |
| 2026-11-13 | MLflow server defaults to port **5001**, not 5000. | macOS AirPlay Receiver binds :5000 by default. |
| 2026-11-13 | `pyproject.toml` uses `[tool.uv] package = false`; modules run in place via `python -m pipeline.<step>`. | Simplest; nothing is distributed. |
| 2026-11-13 | Old `scrapers/Dockerfile` and `scrapers/fandom/run.sh` archived too (they uploaded to Oracle). | Not in the prompt's list, but Oracle/k8s-specific; the scraper is re-copied fresh in Phase 2. |
