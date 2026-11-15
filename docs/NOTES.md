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

## Decisions

- 2026-11-15 — MLflow runs on port **5001**, because macOS AirPlay Receiver uses 5000.
