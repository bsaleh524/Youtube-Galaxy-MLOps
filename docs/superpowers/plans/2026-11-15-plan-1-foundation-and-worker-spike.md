# Plan 1 — Foundation and Worker Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive the old design, set up a fresh repo skeleton that `make setup` builds from a clean clone, and build the Worker spike (binary index, two-stage search in Python + TypeScript, parity script) up to 🛑 Checkpoint 1.

**Architecture:** Python 3.11 `pipeline/` package managed by `uv` (one `pipeline` dependency group). A separate `.venv-airflow` with Airflow installed from its official constraints file. `worker/` is a Wrangler/TypeScript/vitest project and `web/` is a Vite/TypeScript stub. A shared binary index format is written by Python and read by TypeScript, and a cross-language fixture keeps the two search implementations identical.

**Tech Stack:** uv, Python 3.11, numpy, sentence-transformers, pytest, ruff; Node 20+ (local: 24), Wrangler, TypeScript, vitest, Vite; Airflow (version verified in Task 4); MLflow.

**Spec:** `docs/superpowers/specs/2026-11-15-youtube-galaxy-design.md` (it builds on `README.md`, `CLAUDE.md` and `docs/IMPLEMENTATION_PROMPT.md`; read all four).

### Plan series

The spec is delivered as a series of plans, one per milestone. Each later plan is written **after** the previous checkpoint, using the facts that checkpoint produced (for example, Plan 3's Worker loader depends on the index-delivery choice made here).

| Plan | Covers (delivery-order step) | Ends at |
|---|---|---|
| **1 (this)** | Phase 0 scaffold, Phase 1 spike | 🛑 Checkpoint 1 |
| 2 | Phase 2 pipeline: seed, incremental scraper, embed, cluster fit/assign, names/colours, build | 🛑 Checkpoint 2 |
| 3 | Phase 3 site + home page, map-only publish | 🛑 publish checkpoint |
| 4 | Phase 4 Worker `search`, publish chat | 🛑 Checkpoint 3 + deploy checkpoint |
| 5 | Phase 5 eval, MLflow, gate | eval checkpoint |
| 6 | Phase 6 Airflow DAG, `make recluster` | — |
| 7 | `ask` mode | 🛑 ask checkpoint |
| 8 | Phase 8 docs, screenshots, cleanup | done |

## Global Constraints

- $0/month: Cloudflare **free plan** only, no paid service anywhere. If anything needs a paid plan or a payment method, stop and ask the owner.
- Never reintroduce Kubernetes, k3d, Helm, Oracle Cloud, Weaviate, Redis, DuckDB, Kaggle stats, Streamlit, Feast or Terraform outside `archive/`. Never delete `archive/`.
- Don't modify `../Controversy-Early-Warning-System/`. Reading and copying from it are fine.
- Don't touch the `before-superpowers` branch, and don't reuse its code or results.
- Commit after each task and push to `superpowers-rework`. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use `git mv` for tracked files.
- Embedding model `BAAI/bge-small-en-v1.5`, dim **384**, normalised, CLS pooling. Query prefix exactly `"Represent this sentence for searching relevant passages: "`. Passages get no prefix.
- Secrets live only in `.env` (gitignored) and Worker secrets. Never in git, `wrangler.jsonc`/`wrangler.toml` or browser code. Never invent credentials.
- Any outside request uses a generic identity (`galaxy-hobby-scraper/1.0`). Never include the owner's name or email.
- Every external fact relied on (limits, model IDs, parameters, versions) gets verified against official docs and recorded in `docs/NOTES.md` with the source URL and the date (2026-11-15 or the actual day).
- Python 3.11, `uv` for all Python. Airflow never imports torch. Its venv is separate.
- Creators are referenced by stable id (`fandom_{pageid}`), never array position. The index **row** is internal to an index version and maps to an id through meta.

## Review Focus

1. **Non-ASCII titles in meta** (the data has Japanese titles such as `ねくろちゃん -Yamaguro Nekuro-`). Meta offsets must be **byte** offsets into UTF-8, so records decode exactly in both Python and TS. → Task 6 and Task 7 tests use a Japanese + emoji title.
2. **Probing runs out of clusters or hits empty ones.** Small clusters, empty clusters (equal consecutive offsets), or `max_probe` reached before `min_candidates`: search must stop cleanly and still return what it has. → Task 6 and Task 7 tests.
3. **`k` larger than the candidate count** returns all candidates, sorted, with no padding and no crash. → Task 6 and Task 7 tests.
4. **Zero or unnormalised query vector:** queries are normalised first, and an all-zero query returns `[]` instead of NaN scores. → Task 6 and Task 7 tests.
5. **Clean clone without `.env`:** `make setup` and `make test` must work with no `.env` present. The parity script without credentials exits non-zero with a one-line message naming the missing variable, not a stack trace. → Task 2 and Task 9.

---

### Task 1: Clear leftovers and archive the old design

**Files:**
- Delete (ignored, untracked leftovers from the set-aside branch): `pipeline/`, `tests/`, `worker/`, `.venv-airflow/`, `.pytest_cache/`, `archive/quick/`, `archive/serving/`
- Move with `git mv`: `training/` → `archive/training/`, `serving/` → `archive/serving/`, `frontend/` → `archive/frontend/`, `dags/` → `archive/dags/`, `quick/` → `archive/quick/`, `scripts/` → `archive/scripts/`, `scrapers/Dockerfile` → `archive/scrapers/Dockerfile`, `scrapers/fandom/run.sh` → `archive/scrapers/fandom/run.sh`, `Makefile` → `archive/Makefile.old`, `pyproject.toml` → `archive/pyproject.old.toml`
- Create: `archive/README.md`

- [ ] **Step 1: Show the owner the leftover list and wait for an explicit OK.** Run `du -sh pipeline tests worker .venv-airflow .pytest_cache archive/quick archive/serving` and `git status --short --ignored`. Confirm `.env` is **not** in the list. Do not delete until the owner says yes.
- [ ] **Step 2: Delete the confirmed leftovers** (`rm -rf` on exactly those seven paths). Expected: `git status --short --ignored` shows only `.env`, `.venv/`, `.DS_Store` files and `docs/superpowers/` changes.
- [ ] **Step 3: Run the `git mv` moves above.** Create the parent dirs (`archive/scrapers/fandom`) first.
- [ ] **Step 4: Write `archive/README.md`.** List each archived folder (k3d, k8s, learn, training, serving, frontend, dags, quick, scripts, scrapers, Makefile.old, pyproject.old.toml), one line on what it was, and one paragraph on why it was archived (moved from a Kubernetes/Oracle design to local pipeline + static site + free Worker; see README).
- [ ] **Step 5: Verify.** `git status` shows renames only, plus the new README. `git ls-files training serving frontend quick scripts dags` prints nothing.
- [ ] **Step 6: Commit and push.** `git commit -m "archive: move k8s/Oracle-era code into archive/"` then `git push`.

### Task 2: Python project, config files, test harness

**Files:**
- Create: `pyproject.toml`, `pipeline/__init__.py`, `pipeline/config.py`, `tests/__init__.py`, `tests/test_config.py`, `.env.example`, `docs/NOTES.md`
- Modify: `.gitignore`, `uv.lock` (regenerated)

**Interfaces:**
- Produces: `pipeline.config.Settings` (frozen dataclass) and `pipeline.config.load_settings(env_file: Path | None = Path(".env")) -> Settings`. Fields: `embedding_model: str = "BAAI/bge-small-en-v1.5"`, `n_clusters: int = 120`, `query_prefix: str` (the exact prefix from Global Constraints), `data_dir: Path = Path("data")`, `cloudflare_account_id: str | None`, `cloudflare_api_token: str | None`, `mlflow_port: int = 5001`. Reads `.env` if it exists and environment variables override it. A missing file is fine.
- Produces: `pipeline.config.require(settings: Settings, *names: str) -> None`. It raises `SystemExit` with the message `missing required setting: CLOUDFLARE_API_TOKEN (set it in .env)` for the first unset one.

- [ ] **Step 1: Rewrite `pyproject.toml`.** Keep `[project]` (name `youtube-galaxy-mlops`, `requires-python = ">=3.11"`, no runtime deps). Add `[dependency-groups]`:
  - `pipeline`: sentence-transformers, torch, scikit-learn, umap-learn, numpy, pandas, pyarrow, requests, beautifulsoup4, mlflow, paramiko, pyyaml, python-dotenv, tqdm.
  - `dev`: pytest, ruff.

  Add `[tool.uv] default-groups = ["pipeline", "dev"]`, `[tool.pytest.ini_options] testpaths = ["tests"]` and `[tool.ruff] line-length = 100, target-version = "py311"`. Lower-bound pins only.
- [ ] **Step 2: Rewrite `.gitignore`.**
  - Remove: the Terraform, Oracle, Weaviate, feature-store, kubeconfig and Ollama lines.
  - Keep: Python, Jupyter, `.env`/`.env.*`/`!.env.example`, `data/`, `.DS_Store`, `.vscode/`.
  - Add: `.venv*/`, `node_modules/`, `web/dist/`, `worker/.wrangler/`, `worker/assets/*` with `!worker/assets/.gitkeep`, `.pytest_cache/`, `.ruff_cache/`.
- [ ] **Step 3: Write `.env.example`** with exactly the grouped keys and comments from `docs/IMPLEMENTATION_PROMPT.md` § Config. Add `MLFLOW_PORT=5001` under `# Pipeline`, with the comment `# 5000 is taken by macOS AirPlay Receiver`. Then diff the owner's existing `.env` keys against it with `grep -o '^[A-Z_]*=' .env` (names only, never print values) and report missing or extra key names.
- [ ] **Step 4: Write the failing test** `tests/test_config.py`:

```python
def test_defaults_without_env_file(tmp_path, monkeypatch):
    for k in ["EMBEDDING_MODEL", "N_CLUSTERS", "CLOUDFLARE_API_TOKEN", "MLFLOW_PORT"]:
        monkeypatch.delenv(k, raising=False)
    s = load_settings(tmp_path / "missing.env")
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    assert s.n_clusters == 120
    assert s.query_prefix == "Represent this sentence for searching relevant passages: "
    assert s.mlflow_port == 5001
    assert s.cloudflare_api_token is None

def test_env_overrides_file(tmp_path, monkeypatch):
    f = tmp_path / ".env"; f.write_text("N_CLUSTERS=60\n")
    monkeypatch.setenv("N_CLUSTERS", "200")
    assert load_settings(f).n_clusters == 200

def test_require_names_missing_setting(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="missing required setting: CLOUDFLARE_API_TOKEN"):
        require(load_settings(tmp_path / "x.env"), "CLOUDFLARE_API_TOKEN")
```

- [ ] **Step 5: Run it and confirm it fails.** `uv sync` then `uv run pytest tests/test_config.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 6: Implement `pipeline/config.py`.** Use `dotenv_values` for the file, then `os.environ` on top. An empty string counts as unset.
- [ ] **Step 7: Confirm it passes.** `uv run pytest -v && uv run ruff check .`. Expected: all pass, no lint errors.
- [ ] **Step 8: Create `docs/NOTES.md`.** Add sections "Verified external facts" (a table: fact · value · source URL · date checked) and "Decisions" (a dated list). Seed it with one decision: "MLflow on port 5001 because macOS AirPlay Receiver uses 5000."
- [ ] **Step 9: Commit and push.** `chore: python project, config loader, env example`

### Task 3: Node projects — `worker/` and `web/` skeletons

**Files:**
- Create: `worker/package.json`, `worker/tsconfig.json`, `worker/wrangler.jsonc`, `worker/vitest.config.ts`, `worker/src/worker.ts`, `worker/test/health.test.ts`, `worker/assets/.gitkeep`, `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/index.html`, `web/src/main.ts`

**Interfaces:**
- Produces: the Worker's default export `{ fetch(req: Request, env: Env): Promise<Response> }`, with `GET /health` → `200 {"ok": true, "index_version": string | null}`. `Env` lives in `worker/src/env.ts`. In this task it is empty apart from optional `INDEX_VERSION?: string` (bindings are added in Task 8).
- Produces: npm scripts. `worker`: `dev`, `deploy`, `test` (vitest run), `typecheck`. `web`: `dev`, `build`, `test` (`vitest run --passWithNoTests`). Vite `base` reads `process.env.SITE_BASE_PATH ?? "/galaxy/"`.

- [ ] **Step 1: Look up the current Cloudflare-recommended test setup** for Workers + vitest (the `@cloudflare/vitest-pool-workers` package and how its config is written). Record the package versions and the doc URL in `docs/NOTES.md`. Use `wrangler.jsonc` (current default format) with `compatibility_date` = today.
- [ ] **Step 2: Write the failing test** `worker/test/health.test.ts`. A request to `/health` returns 200, and the JSON has `ok === true` and an `index_version` key. Any other path returns 404 JSON `{"error":"not_found"}`.
- [ ] **Step 3: Run it and confirm it fails.** `cd worker && npm install && npm test`. Expected: FAIL.
- [ ] **Step 4: Implement `worker/src/worker.ts`** with the routing above.
- [ ] **Step 5: Confirm it passes.** `npm test && npm run typecheck`. Expected: PASS.
- [ ] **Step 6: Scaffold `web/`.** Vite vanilla-TS: a page titled "YouTube Galaxy" with one line of text. Check `cd web && npm install && npm run build`. Expected: `web/dist/index.html` exists, and its asset URLs start with `/galaxy/`.
- [ ] **Step 7: Commit and push.** `chore: worker and web skeletons`

### Task 4: Airflow venv, MLflow script, Makefile, CI

**Files:**
- Create: `scripts/setup_airflow.sh`, `scripts/start_mlflow.sh`, `scripts/start_airflow.sh`, `Makefile`, `dags/.gitkeep`, `.github/workflows/test.yml`
- Modify: `docs/NOTES.md`

- [ ] **Step 1: Verify the current Airflow stable release** and its install-with-constraints instructions from airflow.apache.org. Choose the newest stable major.minor that supports Python 3.11, and record the version, the constraints URL pattern, how `airflow standalone` works, and the DAG import path for that major version (`airflow.sdk` in 3.x vs `airflow.decorators` in 2.x) in `NOTES.md`.
- [ ] **Step 2: Write `scripts/setup_airflow.sh`.** Use `set -euo pipefail`. It creates `.venv-airflow` with `uv venv --python 3.11 .venv-airflow`, then installs `apache-airflow==$AIRFLOW_VERSION` with `uv pip install --python .venv-airflow ... --constraint <constraints-$AIRFLOW_VERSION/constraints-3.11.txt>`. The version is pinned at the top of the script. It is idempotent: if the venv already has that version, it skips.
- [ ] **Step 3: Write `scripts/start_airflow.sh`.** Export `AIRFLOW_HOME=$PWD/data/airflow`, `AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags` and `AIRFLOW__CORE__LOAD_EXAMPLES=False`, then exec `.venv-airflow/bin/airflow standalone`.
- [ ] **Step 4: Write `scripts/start_mlflow.sh`.** Create `data/mlflow/artifacts`, then exec `uv run mlflow server --backend-store-uri sqlite:///data/mlflow/mlflow.db --default-artifact-root ./data/mlflow/artifacts --host 127.0.0.1 --port ${MLFLOW_PORT:-5001}`.
- [ ] **Step 5: Write the `Makefile`** with only the targets that work now:
  - `setup`: `uv sync`, `npm install` in `web/` and `worker/`, then `scripts/setup_airflow.sh`.
  - `mlflow`, `airflow`, `web-dev`, `web-build`, `worker-dev`, `worker-deploy`.
  - `test`: `uv run pytest`, `uv run ruff check .`, `npm test` in `worker/` and `web/`.
  - `clean`: removes `web/dist`, `worker/.wrangler` and caches, **never** `data/` or `.env`.

  Add a comment that pipeline targets (`scrape`, `embed`, `cluster`, `build`, `eval`, `gate`, `publish`, `pipeline`, `recluster`, `rollback`) are added by later plans.
- [ ] **Step 6: Write `.github/workflows/test.yml`.** Trigger on push and pull_request. One job, ubuntu-latest:
  - checkout, `astral-sh/setup-uv`, Node 20 setup
  - `uv sync --only-group ci`, then `uv run --only-group ci pytest` and `uv run --only-group ci ruff check .`
  - `npm ci && npm test` in `worker/`

  First add a `ci` dependency group to `pyproject.toml`: `[numpy, pyyaml, requests, python-dotenv, pytest, ruff]`. This keeps torch out of CI. **Rule for all plans:** modules import torch, sentence-transformers, umap or mlflow lazily inside functions, so tests of pure logic run in CI. No secrets.
- [ ] **Step 7: Verify from a clean clone.** `git clone . ../galaxy-clone-check && cd ../galaxy-clone-check && make setup && make test`. Expected: setup finishes (Airflow install may take minutes) and all tests pass. Then `rm -rf ../galaxy-clone-check`. Also run `make airflow` in the real repo for ~60s: the UI answers on :8080 and shows zero DAGs. Stop it.
- [ ] **Step 8: Commit and push.** `chore: airflow venv, mlflow script, makefile, CI`. After the push, confirm the GitHub Actions run is green with `gh run list --branch superpowers-rework --limit 1`.

### Task 5: Verify Cloudflare free-plan facts and choose index delivery

Research only, no code. The output is `docs/NOTES.md` entries. Each one gets its source URL and date.

- [ ] **Step 1: Workers Free limits.** Record CPU time per request, requests per day, script size (compressed and uncompressed), memory per isolate, and subrequests per request.
- [ ] **Step 2: Static assets.** Check whether a Worker can read its own static assets from code (an `ASSETS` binding `fetch`), the per-file size limit, the file-count limit, whether asset requests count against free limits, and how to make the Worker run first (`run_worker_first` or the current equivalent).
- [ ] **Step 3: KV.** Record the maximum value size, free reads/day, writes/day and storage.
- [ ] **Step 4: R2.** Check whether enabling R2 requires a payment method on file. If yes, record "skipped: requires payment method".
- [ ] **Step 5: Workers AI.**
  - The exact model ID for bge-small-en-v1.5 and its input schema: does it have a `pooling` parameter, which values it accepts, and what the default is?
  - Free Neurons/day and the Neuron cost of one bge-small embedding.
  - Current small instruct LLM IDs (3B–8B), their Neuron cost per typical chat (~2K input / 400 output tokens), any license-acceptance step, and any announced deprecations.
  - The REST endpoint format for running a model with an API token (used by Task 9).
- [ ] **Step 6: Rate limiting.** Check whether the free plan has a Workers Rate Limiting binding, and what its limits are.
- [ ] **Step 7: CPU measurement.** Find the exact way to read per-request CPU time on a deployed Worker: whether `wrangler tail --format json` includes `cpuTime` per event, or the dashboard metrics view, or Workers Observability/logs. Record the method.
- [ ] **Step 8: Decide index delivery.** Follow the preference order in `IMPLEMENTATION_PROMPT.md` Phase 1.1: static assets → KV → R2 → bundled. Record the winner and why under "Decisions". If static assets win, the Worker loads `index.bin`, `centroids.bin`, `meta.bin` and `index_manifest.json` from `worker/assets/` through the assets binding. **If no option fits the free plan, stop and tell the owner.**
- [ ] **Step 9: Commit and push.** `docs: verified cloudflare free-plan facts and index delivery decision`

### Task 6: Binary index format, synthetic data and two-stage search (Python)

**Files:**
- Create: `pipeline/index_format.py`, `pipeline/search.py`, `pipeline/synthetic.py`, `tests/test_index_format.py`, `tests/test_search.py`

**Format (both languages implement exactly this; little-endian throughout):**
- `index.bin`:
  - 8-byte magic `b"GXIDX1\0\0"`
  - `uint32 n, uint32 dim, uint32 k`
  - `uint32 offsets[k+1]`: row ranges per cluster; rows are ordered by cluster
  - `float32 scales[n]`
  - `int8 vecs[n*dim]`

  The header is 20 bytes and the offsets are 4-byte, so `scales` starts 4-aligned.
- Quantisation is per row: `s = max(|v|)`; `q = clip(round(v / s * 127), -127, 127)`. Approximate cosine = `(s / 127) * Σ q_i * query_i`, with the query as float32 and normalised.
- `centroids.bin`: magic `b"GXCEN1\0\0"`, `uint32 k, uint32 dim`, `float32 data[k*dim]` (L2-normalised).
- `meta.bin`: magic `b"GXMETA1\0"`, `uint32 n`, `uint32 byte_offsets[n+1]`, then a UTF-8 blob. Record `i` = `blob[byte_offsets[i]:byte_offsets[i+1]]`, a compact JSON object `{"id","title","cluster","url","snippet"}`. Records are in index-row order.
- `index_manifest.json`: `{"version": str, "n": int, "dim": int, "k": int, "model": str}`.

**Search algorithm (both languages):**
1. Normalise the query. If its norm is 0, return `[]`.
2. Score all `k` centroids. Order the clusters by score (descending), with cluster id ascending to break ties.
3. Take clusters in that order. Stop once `probed >= probe_min and candidates >= min_candidates`, or when `probed == max_probe`, or when there are no clusters left.
4. Score every member row of the probed clusters.
5. Return the top `k` as `(row, score)`, sorted by score descending, then row ascending.

Defaults: `k=10, probe_min=3, min_candidates=1500, max_probe=12`.

**Interfaces:**
- Produces:
  - `pipeline.index_format`:
    - `@dataclass IndexData(q: np.ndarray[int8,(n,dim)], scales: np.ndarray[float32,(n,)], offsets: np.ndarray[uint32,(k+1,)])`
    - `quantize_rows(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]`
    - `write_index(path: Path, data: IndexData) -> None`
    - `read_index(path: Path) -> IndexData`
    - `write_centroids(path, c: np.ndarray) -> None`
    - `read_centroids(path) -> np.ndarray`
    - `write_meta(path, records: list[dict]) -> None`
    - `read_meta_record(blob: bytes, i: int) -> dict`
  - `pipeline.search`:
    - `two_stage_search(query: np.ndarray, centroids: np.ndarray, index: IndexData, k=10, probe_min=3, min_candidates=1500, max_probe=12) -> list[tuple[int, float]]`
    - `brute_force_search(query: np.ndarray, index: IndexData, k=10) -> list[tuple[int, float]]` (same quantised scoring, all rows)
  - `pipeline.synthetic`:
    - `make_synthetic(n: int, dim: int, k: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]`, returning (vectors ordered by cluster, offsets, centroids, records)
    - CLI `python -m pipeline.synthetic --out DIR [--n 20800 --dim 384 --k 120 --seed 0]` writes the four index files
    - CLI `python -m pipeline.synthetic --fixture DIR` writes a small cross-language fixture: n=600, dim=384, k=12, seed=1, two clusters forced empty. It writes:
      - `index.bin`, `centroids.bin`, `meta.bin`
      - `index_manifest.json` with version `"fixture-1"`
      - `queries.json` (20 seeded unit queries)
      - `expected.json` (`{"params": {"probeMin": 2, "minCandidates": 150, "maxProbe": 5}, "results": {"5": [...], "600": [...]}}` from `two_stage_search`)
      - `meta_utf8.bin` (the two records from `test_meta_utf8_byte_offsets`) and `meta_utf8.json` (those records as plain JSON)

- [ ] **Step 1: Write the failing tests.** `tests/test_index_format.py`:

```python
def test_roundtrip_index(tmp_path):
    v, offsets, cents, recs = make_synthetic(n=200, dim=16, k=5, seed=0)
    q, s = quantize_rows(v)
    write_index(tmp_path / "index.bin", IndexData(q, s, offsets))
    d = read_index(tmp_path / "index.bin")
    assert np.array_equal(d.q, q) and np.allclose(d.scales, s) and np.array_equal(d.offsets, offsets)

def test_quantization_cosine_error_small():
    v, *_ = make_synthetic(n=500, dim=384, k=10, seed=0)
    q, s = quantize_rows(v)
    approx = (q.astype(np.float32) * (s / 127)[:, None])
    assert np.max(np.abs(np.sum(approx * v, 1) - 1.0)) < 0.01

def test_meta_utf8_byte_offsets(tmp_path):
    recs = [{"id": "fandom_1", "title": "ねくろちゃん -Yamaguro Nekuro-", "cluster": 0, "url": "u", "snippet": "🎮 ok"},
            {"id": "fandom_2", "title": "Plain", "cluster": 1, "url": "u2", "snippet": "x"}]
    write_meta(tmp_path / "meta.bin", recs)
    blob = (tmp_path / "meta.bin").read_bytes()
    assert read_meta_record(blob, 0) == recs[0] and read_meta_record(blob, 1) == recs[1]
```

`tests/test_search.py`:

```python
def test_two_stage_matches_brute_force_when_probing_everything(): ...
    # max_probe=k, min_candidates=n → identical rows to brute_force_search
def test_high_agreement_on_synthetic(): ...
    # n=5000, dim=384, k=40, 50 queries from noisy members: mean overlap@10 with brute force >= 0.9
def test_empty_clusters_and_max_probe_stop():
    # offsets with two empty clusters; max_probe=2, min_candidates huge → returns <= members of 2 clusters, no error
def test_k_larger_than_candidates_returns_all_sorted(): ...
def test_zero_query_returns_empty(): assert two_stage_search(np.zeros(16, np.float32), cents, idx) == []
def test_unnormalized_query_same_as_normalized(): ...
def test_results_sorted_score_desc_row_asc(): ...
```

- [ ] **Step 2: Run them and confirm they fail.** `uv run pytest tests/test_index_format.py tests/test_search.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement `pipeline/index_format.py`.** Use `struct` for the headers and `np.frombuffer`/`tofile` for the arrays.
- [ ] **Step 4: Implement `pipeline/synthetic.py`.** Pick k random unit centres, and give each cluster a random size so they sum to `n` (a lognormal draw, re-normalised). Members are centre + Gaussian noise (σ=0.06 per dim, ~1.2 norm), then normalised. Centroids are the normalised member means. Records get ids `syn_{i}`, titles `Synthetic {i}`, `url` `https://example.invalid/{i}` and a 40-char snippet. For `--fixture`, force clusters 3 and 7 to size 0.
- [ ] **Step 5: Implement `pipeline/search.py`** per the algorithm above. Use `np.argpartition` for top-k, then the stable sort by (−score, row).
- [ ] **Step 6: Confirm they pass.** `uv run pytest -v`. Expected: all pass.
- [ ] **Step 7: Write the fixture.** `uv run python -m pipeline.synthetic --fixture worker/test/fixtures`. The files are small (~250 KB), so commit them. Write the full-size spike data to `data/spike/` with `uv run python -m pipeline.synthetic --out data/spike`, then report the file sizes (expected `index.bin` ≈ 8.1 MB).
- [ ] **Step 8: Commit and push.** `feat(pipeline): binary index format, synthetic data, two-stage search`

### Task 7: Two-stage search in TypeScript

**Files:**
- Create: `worker/src/format.ts`, `worker/src/search.ts`, `worker/test/search.test.ts`, `worker/test/format.test.ts`, `worker/test/fixtures/*` (from Task 6)

**Interfaces:**
- Consumes: the format and algorithm defined in Task 6, plus `worker/test/fixtures/{index.bin,centroids.bin,meta.bin,queries.json,expected.json}`. `queries.json` is `number[][]`. `expected.json` is `{ "params": {...}, "results": { "<k>": [[row, score], ...][] } }`.
- Produces:
  - `format.ts`:
    - `parseIndex(buf: ArrayBuffer): IndexView` where `IndexView = {n, dim, k, offsets: Uint32Array, scales: Float32Array, vecs: Int8Array}`. These are typed-array views over `buf`, never copies.
    - `parseCentroids(buf: ArrayBuffer): CentroidsView` where `CentroidsView = {k, dim, data: Float32Array}`
    - `parseMeta(buf: ArrayBuffer): MetaView`
    - `readRecord(meta: MetaView, row: number): MetaRecord` where `MetaRecord = {id: string, title: string, cluster: number, url: string, snippet: string}`. It decodes only that record's bytes with `TextDecoder`.
    - All parsers throw `Error("bad magic: <name>")` on a wrong magic.
  - `search.ts`:
    - `normalize(v: Float32Array): Float32Array | null` (null for a zero vector)
    - `twoStageSearch(query: Float32Array, c: CentroidsView, idx: IndexView, opts?: Partial<SearchOpts>): Hit[]` where `SearchOpts = {k: 10, probeMin: 3, minCandidates: 1500, maxProbe: 12}` and `Hit = {row: number, score: number}`
    - `bruteForce(query: Float32Array, idx: IndexView, k: number): Hit[]`

- [ ] **Step 1: Write the failing tests.**
  - `format.test.ts`:
    - The fixture's index parses with `n=600, dim=384, k=12`, and `offsets[12] === 600`.
    - Bad magic throws.
    - `readRecord` on `meta_utf8.bin` returns exactly the records in `meta_utf8.json`, including the Japanese + emoji title.
  - `search.test.ts`:
    - For every fixture query and each k in {5, 600}, `twoStageSearch` with the fixture params returns the same rows in the same order as `expected.json`, with `|score - expected| < 1e-4`. This is the cross-language parity check.
    - A zero query returns `[]`.
    - `k=600` returns exactly the candidate count with no padding.
    - Probing everything equals `bruteForce`.
- [ ] **Step 2: Run them and confirm they fail.** `cd worker && npm test`. Expected: FAIL.
- [ ] **Step 3: Implement `format.ts` and `search.ts`.**
  - The inner loop is a plain `for` over `Int8Array`, accumulating into a JS number, then times `scales[row] / 127`.
  - Top-k uses a fixed-size min-heap or insertion into a sorted array of length k. No `Array.sort` over all candidates.
  - No `JSON.parse` on anything except a single decoded record.
- [ ] **Step 4: Confirm they pass.** `npm test && npm run typecheck`. Expected: PASS.
- [ ] **Step 5: Add a local benchmark** `worker/bench/search.bench.ts` (vitest bench). It loads `../data/spike/*` if present, otherwise skips. Use 200 random normalised queries and report mean/p95 ms for `twoStageSearch` and `bruteForce`. Add `"bench": "vitest bench --run"` to package.json. Run it and record the numbers in `NOTES.md`, labelled **local Node, not the Workers runtime**.
- [ ] **Step 6: Commit and push.** `feat(worker): binary index reader and two-stage search with cross-language fixture`

### Task 8: Spike Worker endpoints for deployed measurement

**Files:**
- Modify: `worker/src/worker.ts`, `worker/src/env.ts`, `worker/wrangler.jsonc`
- Create: `worker/src/index_loader.ts`, `worker/test/spike.test.ts`, `scripts/spike_load.sh`

**Interfaces:**
- Consumes: the delivery decision from Task 5 (assumed here: static assets + an `ASSETS` binding, Worker runs first). Uses `parseIndex`, `parseCentroids`, `parseMeta`, `readRecord`, `twoStageSearch` and `normalize` from Task 7.
- Produces:
  - `index_loader.ts`: `getIndex(env: Env): Promise<LoadedIndex>`, where `LoadedIndex = {manifest, index: IndexView, centroids: CentroidsView, meta: MetaView}`. It is cached in a module-level variable, so only the first request in an isolate loads it.
  - `GET /health` now returns `index_version` from `manifest.version`.
  - `GET /spike/search?seed=<int>`: builds a deterministic pseudo-random normalised query from the seed (mulberry32), runs `twoStageSearch`, decodes the top-10 records and returns `{hits: [{id, title, score}], probed, candidates}`. This isolates search CPU with no AI call.
  - `GET /spike/embed-search?q=<text>`: embeds `query_prefix + q` with Workers AI (model ID and pooling from Task 5, `pooling: "cls"` if supported), normalises, searches and returns the same shape. It needs an `AI` binding in `wrangler.jsonc`.
  - **Both `/spike/*` routes are removed in Plan 4.**

- [ ] **Step 1: Write the failing tests** `worker/test/spike.test.ts`, using the fixture files as assets in the vitest pool config:
  - `/spike/search?seed=1` returns 200 with 10 hits sorted by score descending.
  - Two calls to `getIndex` return the same object (cache).
  - `/health` returns the fixture manifest version.
  - A missing `seed` returns 400 `{"error":"bad_request"}`.
- [ ] **Step 2: Run them and confirm they fail.** `npm test`. Expected: FAIL.
- [ ] **Step 3: Implement the loader and routes.** Add the `assets` (directory `./assets`, binding `ASSETS`) and `ai` (binding `AI`) config to `wrangler.jsonc` in the current format verified in Task 5.
- [ ] **Step 4: Confirm they pass.** `npm test && npm run typecheck`.
- [ ] **Step 5: Write `scripts/spike_load.sh WORKER_URL [N=300]`.** It runs one warm-up request, then N sequential `/spike/search?seed=$i` requests with curl, and prints client-side latency p50/p95. It also prints the instructions for reading the server-side CPU time with the method recorded in Task 5 Step 7.
- [ ] **Step 6: Copy the spike data into place** (`cp data/spike/* worker/assets/`; these are gitignored). Run `cd worker && npx wrangler dev` and `curl localhost:8787/spike/search?seed=1`. Expected: 10 hits.
- [ ] **Step 7: Commit and push.** `feat(worker): spike endpoints and cached index loader`

### Task 9: Embedding parity script

**Files:**
- Create: `pipeline/parity_check.py`, `pipeline/workers_ai.py`, `tests/test_parity.py`, `pipeline/parity_samples.yaml`

**Interfaces:**
- Consumes: `load_settings` and `require` (Task 2), plus the Workers AI REST endpoint, model ID and pooling parameter (Task 5).
- Produces:
  - `pipeline.workers_ai.embed_remote(texts: list[str], settings: Settings, pooling: str = "cls") -> np.ndarray` (float32, normalised, shape (len, 384)). It uses `requests` with header `User-Agent: galaxy-hobby-scraper/1.0` and the API token. It batches requests per the API's documented max batch size.
  - `pipeline.parity_check.cosine_rows(a: np.ndarray, b: np.ndarray) -> np.ndarray`
  - `pipeline.parity_check.main(argv=None) -> int`. CLI: `python -m pipeline.parity_check [--pooling cls|mean]`. It embeds ~20 passages (no prefix) and ~10 queries (with the prefix) locally with `SentenceTransformer(model, device=auto).encode(normalize_embeddings=True)` and remotely, then prints a per-item cosine table plus the min and mean. It exits 0 if min ≥ 0.99, 1 otherwise, and 2 for missing settings via `require`.
  - `parity_samples.yaml` holds 20 passages drawn from the seed JSON's first 20 records (`f"{title} - {description[:2000]}"`, copied at authoring time) and 10 handwritten queries ("minecraft parkour youtubers", "japanese vtuber", "true crime commentary", …).

- [ ] **Step 1: Write the failing tests** `tests/test_parity.py`:
  - `cosine_rows` on identical rows gives 1.0, and on orthogonal rows gives 0.0.
  - `main([])` with no `CLOUDFLARE_*` env returns exit code 2 and prints `missing required setting: CLOUDFLARE_ACCOUNT_ID` (use `monkeypatch` and `capsys`; no network).
  - `embed_remote` builds the right URL and JSON body: monkeypatch `requests.post` and assert the URL contains the account id and model id, the body has `"pooling": "cls"`, and the token is in the `Authorization` header, not the URL.
- [ ] **Step 2: Run them and confirm they fail.** `uv run pytest tests/test_parity.py -v`.
- [ ] **Step 3: Implement** `workers_ai.py` and `parity_check.py`. Pick the device in this order: CUDA, MPS, CPU.
- [ ] **Step 4: Confirm they pass.** `uv run pytest -v`.
- [ ] **Step 5: Commit and push.** `feat(pipeline): workers ai embedding parity check`

### Task 10: 🛑 Checkpoint 1 — hand over to the owner

- [ ] **Step 1: Run `make test`.** Report the pass/fail counts honestly.
- [ ] **Step 2: Give the owner the exact steps.**
  1. Create a free Cloudflare account if needed.
  2. Run `cd worker && npx wrangler login`.
  3. Copy the Account ID from the dashboard into `.env` as `CLOUDFLARE_ACCOUNT_ID`.
  4. Create an API token with the "Workers AI" permission (the exact template name is recorded in Task 5) and put it in `.env` as `CLOUDFLARE_API_TOKEN`.
  5. Accept any LLM license noted in Task 5.
- [ ] **Step 3: After the owner confirms,** run:
  - `cp data/spike/* worker/assets/ && cd worker && npx wrangler deploy`
  - `scripts/spike_load.sh <url> 300`, then read the CPU time with the Task 5 method
  - `curl "<url>/spike/embed-search?q=minecraft%20parkour"`
  - `uv run python -m pipeline.parity_check`. If it fails with cls pooling, also run `--pooling mean` and report both.
- [ ] **Step 4: Report to the owner in plain language.**
  - The chosen index delivery, and why.
  - Warm CPU p50/p95 versus the 10 ms budget, and cold-start behaviour separately.
  - Parity min/mean cosine versus 0.99.
  - The chosen LLM model and its Neuron cost, with the implied daily answer budget.
  - Any fallback needed.

  **If CPU doesn't fit the free plan, or parity < 0.99, stop and present options. Don't switch to a paid plan or a vector DB.**
- [ ] **Step 5: Record all measured numbers in `docs/NOTES.md`, then commit and push** (`docs: checkpoint 1 measurements`).
- [ ] **Step 6: Write Plan 2** (`docs/superpowers/plans/YYYY-MM-DD-plan-2-pipeline.md`) using these facts, and ask the owner to review it.
