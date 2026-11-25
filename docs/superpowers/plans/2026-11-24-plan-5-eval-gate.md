# Plan 5: Evaluation, MLflow, Quality Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every build is scored on an eval set (recall@8, MRR, brute-force agreement, silhouette, creator count), logged to MLflow, and must pass a gate before `make publish` will upload it. The live build is tagged `champion` in MLflow.

**Architecture:**
- `pipeline/evaluate.py` scores a **finished build directory** with the same code path as the Worker:
  - the Python mirrors of the name lookup and two-stage search;
  - the int8 index;
  - local query embedding with the bge query prefix.
- It writes `data/runs/eval-<version>/report.json` (plus `.md`) and logs a run to MLflow.
- `pipeline/gate.py` compares the report with the thresholds in `eval/gate.yaml` and with the `champion` run's metrics. It writes `gate.json` beside the report.
- `pipeline/publish.py all` refuses to upload a build without a passing `gate.json`, and moves the `champion` alias after a verified publish.

**Order change from the work order** (which lists cluster → evaluate → gate → build): here it is build → evaluate → gate → publish. Evaluation scores the built int8 index, exactly what the Worker serves. The gate still runs before anything is published, which is the point of it.

**Tech Stack:** Python 3.11 (numpy, scikit-learn, sentence-transformers, MLflow 3.15 with a sqlite store, pyyaml), TypeScript (vitest) for the shared name fixture.

**Spec:**
- `docs/IMPLEMENTATION_PROMPT.md` § Phase 5;
- `docs/superpowers/specs/2026-11-15-youtube-galaxy-design.md` (step 8, plain-language checkpoint rule);
- `README.md` § Quality gate.

**Branch:** `plan-5-eval-gate` (cut from `main` after PR #10). Merge into `main` via PR when the owner approves.

## Global Constraints

- **Embedding model:** `BAAI/bge-small-en-v1.5`, CLS pooling, normalised. Queries get the prefix `"Represent this sentence for searching relevant passages: "` (`pipeline.config.QUERY_PREFIX`); passages get none.
- **Mirror the Worker exactly:**
  - search params k=8, `probe_min=3`, `min_candidates=1500`, `max_probe=12`;
  - for "similar to" queries, k=9 with the named creator dropped;
  - names are excluded if they are topic words, taken from `index_manifest.json` `topic_words`.
- **Eval set:** `eval/questions.yaml`, about 30 entries `{question, expected: [ids or titles], notes, status}`.
  - Every drafted entry has `status: draft`.
  - Only `status: approved` entries count toward the gated recall/MRR. Drafts are reported but never gate.
- **MLflow:**
  - store at `sqlite:///<data_dir>/mlflow/mlflow.db`, the same DB `make mlflow` serves;
  - experiment `galaxy-refresh`, created with `artifact_location` = `<data_dir>/mlflow/artifacts` (absolute), never `./mlruns`;
  - registered model `galaxy`, alias `champion`; use aliases, never stages;
  - `mlflow` is imported lazily inside functions. Tests that need it use `pytest.importorskip("mlflow")`, because the CI group has no mlflow.
- **Gate checks (all must pass):**
  - silhouette ≥ `silhouette_floor`, where the floor is the measured baseline minus a margin. **Never 0.40.**
  - approved recall@8 ≥ champion's approved recall@8 − `recall_tolerance`.
  - creators ≥ `count_ratio` × champion's creators, and creators > 0.
  - brute-force agreement ≥ `agreement_min`.
  - Failure exits 1, publishes nothing, and prints a plain-language reason per failed check.
- Eval outputs go under `data/runs/`, **never inside the build dir** (everything in the build dir except `worker/` is uploaded to Hostinger).
- No paid services. Stage specific paths only, never `data/`. Commit and push to `plan-5-eval-gate` after each commit.
- Plain-language explanations of recall@k, MRR and brute-force agreement are required at the checkpoint.

## Review Focus

1. **An `expected` title that doesn't exist, or matches two creators.** Unknown titles are listed in the report and dropped from that question (a question with none left is skipped). A duplicate title counts if any creator with that title appears. Never a crash. *(Task 2 test.)*
2. **No champion yet (first gated publish), or a champion run whose metrics lack approved recall.** The recall and count checks pass with the reason "no previous publish to compare with". *(Task 5 test.)*
3. **Zero approved questions.** Recall/MRR are `null`, not a divide-by-zero, and the gate marks the recall check "skipped (no approved questions)". *(Tasks 2 and 5 tests.)*
4. **A stale or wrong `gate.json`:**
   - a different version, `passed: false`, or a missing file each make `publish all` refuse before connecting;
   - `--no-gate` overrides with a loud warning;
   - `--to-dir` and `rollback` never need a gate. *(Task 6 test.)*
5. **Python and TypeScript folding differ on non-ASCII titles** (accents, CJK, emoji, "ß"). The shared fixture includes such cases and both suites run it. *(Task 1 test.)*

---

### Task 1: Python name lookup mirror + shared cross-language fixture

**Files:**
- Create: `pipeline/name_lookup.py`, `tests/test_name_lookup.py`, `worker/test/fixtures/name_cases.json`
- Modify: `worker/src/names.ts` (extract `nameIndexFromTitles`), `worker/test/names.test.ts`

**Interfaces:**
- Produces (Python):
  ```
  CUES: list[list[str]]
  FILLER: frozenset[str]
  fold_name(s: str) -> str
  build_name_index(titles: list[str], topic_words: set[str] = frozenset()) -> dict[str, int]
  find_named_creator(question: str, names: dict[str, int]) -> int | None
  ```
  The same rules as `worker/src/names.ts`: fold = NFKD, drop combining marks, lowercase, and each run of characters that aren't letters/numbers becomes one space, then strip. Titles under 3 folded characters are skipped, the lowest row wins, and topic words are excluded.
- Produces (TS): `nameIndexFromTitles(titles: string[], topicWords?: Set<string>): Map<string, number>`. `buildNameIndex(meta, topicWords)` becomes a wrapper around it.
- Produces the fixture `name_cases.json`: `{ "titles": [...], "topic_words": [...], "cases": [{ "question": str, "row": int | null }] }`.

- [ ] **Step 1: Write `name_cases.json`.** About 12 titles, including:
  - "Markiplier", "Mark Rober", "Vsauce", "Minecraft" (a topic word), "Café Crème", "Straße TV";
  - a CJK title "東海オンエア", "😀 Emoji Guy", a duplicate "Vsauce" at a higher row, and "TJ" (under 3 characters).

  About 15 cases covering:
  - whole-title, each cue, trailing filler, the topic word → null;
  - accent folding ("cafe creme"), "strasse tv" → null (NFKD keeps ß, so no match, documented in `notes`), "like 東海オンエア";
  - emoji stripped ("like emoji guy"), the duplicate → lowest row, "like tj" → null, empty → null.
- [ ] **Step 2: Write failing tests.**
  - `tests/test_name_lookup.py::test_shared_fixture` loads the JSON and asserts `find_named_creator(q, build_name_index(titles, set(topic_words))) == row` for every case.
  - Also add `test_fold_name` (`fold_name("  Café—Crème! ") == "cafe creme"`).
  - In `worker/test/names.test.ts`, add `it("matches the shared Python fixture")`, which reads `fixtures/name_cases.json` (same fixture helper as `search.test.ts`) and checks `findNamedCreator(q, nameIndexFromTitles(titles, new Set(topic_words))) === row`.
- [ ] **Step 3: Run both and watch them fail.**
  - `uv run pytest tests/test_name_lookup.py -q` → FAIL, ModuleNotFoundError.
  - `cd worker && npx vitest run test/names.test.ts` → FAIL, `nameIndexFromTitles` is not exported.
- [ ] **Step 4: Implement** `pipeline/name_lookup.py`, using `unicodedata.normalize("NFKD")` and dropping chars whose `unicodedata.category` starts with "M". The rest-of-character test is `category[0] in "LN"`. Then extract `nameIndexFromTitles` in `names.ts`.
- [ ] **Step 5: Run both suites.** Expected: PASS. If a case differs between the languages, fix the mirror (not the fixture) unless the TS behaviour is the bug, and ledger it.
- [ ] **Step 6: Commit** — `feat: Python mirror of the Worker name lookup, shared fixture`.

### Task 2: Eval set loading and metric functions

**Files:**
- Create: `pipeline/evalset.py`, `tests/test_evalset.py`

**Interfaces:**
- Produces:
  ```
  @dataclass Question(question: str, expected_ids: list[str], status: str, notes: str, unknown: list[str])
  load_questions(path: Path, ids: list[str], titles: list[str]) -> list[Question]
  recall_at_k(got_ids: list[str], expected: list[str], k: int = 8) -> float
  reciprocal_rank(got_ids: list[str], expected: list[str], k: int = 8) -> float
  overlap(a: list[int], b: list[int]) -> float
  summarize(per_question: list[dict]) -> dict
  ```
- **Expected entries:**
  - An entry starting with `fandom_` is an id.
  - Anything else is a title matched with `fold_name`. Every creator with that folded title is accepted, so duplicates expand to several ids.
  - Unknown entries go to `unknown`.
- `status` must be `draft` or `approved`, or loading raises `ValueError` naming the question.
- `overlap` = |a∩b| / max(len(b), 1).
- `summarize` returns:
  ```
  {"approved": {"n", "recall_at_8", "mrr"}, "all": {"n", "recall_at_8", "mrr"}, "agreement": mean overlap}
  ```
  with `null` means when n == 0.

- [ ] **Step 1: Write failing tests.**
  - `test_recall_and_rr` with exact values: expected {a,b}, got [x,a,y] → recall 0.5, RR 1/2; nothing found → 0, 0.
  - `test_load_resolves_titles_ids_unknown_and_duplicates`: write a tiny yaml in `tmp_path`.
  - `test_bad_status_raises`.
  - `test_question_with_no_known_expected_is_kept_but_flagged`: `expected_ids == []`, and `unknown` is filled.
  - `test_summarize_zero_approved_is_null`.
  - `test_overlap`.
- [ ] **Step 2: Run** `uv run pytest tests/test_evalset.py -q`. Expected: FAIL (no module).
- [ ] **Step 3: Implement** `pipeline/evalset.py` with `yaml.safe_load`. Questions with empty `expected_ids` are excluded from recall/MRR means but still listed in the report.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** — `feat: eval set loader and recall/MRR/agreement metrics`.

### Task 3: `pipeline/evaluate.py`: score a build

**Files:**
- Create: `pipeline/evaluate.py`, `tests/test_evaluate.py`
- Modify: `Makefile` (target `eval`)

**Interfaces:**
- Consumes:
  - `name_lookup.*` (Task 1) and `evalset.*` (Task 2);
  - `pipeline.search.two_stage_search` / `brute_force_search`;
  - `pipeline.index_format.read_index` / `read_centroids` / `read_meta_record`;
  - `clusterlib.silhouette_cosine(X, labels, sample=10000, seed=42)`.
- Produces:
  ```
  load_build(build_dir: Path) -> Build   # dataclass: version, index, centroids, ids, titles, topic_words, manifest
  answer(build, question: str, encode) -> tuple[str, list[int], list[int]]   # (kind "similar"|"topic", two-stage rows k=8, brute rows k=8)
  evaluate(build_dir: Path, questions_path: Path, encode) -> dict   # the report
  write_report(report: dict, runs_dir: Path) -> Path   # data/runs/eval-<version>/report.json + report.md
  main(argv) -> int     # --build DIR (default newest), --questions (default eval/questions.yaml), --no-mlflow
  ```
- **`encode(texts: list[str]) -> np.ndarray`** is injected; the CLI uses `embed.SentenceTransformerEncoder(settings.embedding_model, 32)` and calls it with `[QUERY_PREFIX + q]`.
- **`answer`** mirrors `worker/src/chat.ts` `searchChat`: if a name matches, the query is the dequantised, normalised creator row with k=9 and the named row dropped (applied to both two-stage and brute force); otherwise the embedded query with k=8.
- **Report keys:**
  - `version`, `creators`, `silhouette`;
  - `search_params`, `questions_sha256`;
  - `summary` (from `summarize`);
  - `per_question` `[{question, status, kind, expected, unknown, got: [ids], recall_at_8, rr, agreement}]`.
- **Silhouette** is computed on the build's dequantised int8 vectors. Labels come from the `index.offsets` cluster ranges, using `silhouette_cosine` defaults, so assign-mode drift is caught and the number is reproducible from the build alone.

- [ ] **Step 1: Write failing tests** against a tiny build written in `tmp_path` with `index_format` writers:
  - 3 clusters × 4 rows, dim 8;
  - meta records with ids and titles, `index_manifest.json` with `topic_words: ["music"]`, and `manifest.json`;
  - a fake `encode` that maps known strings to chosen vectors.

  Tests:
  - `test_answer_named_creator_uses_its_vector_and_drops_itself`;
  - `test_answer_topic_uses_prefixed_query` (the fake asserts it received `QUERY_PREFIX + q`);
  - `test_evaluate_report_shape_and_values` (exact recall for a hand-checked question, `creators == 12`, `0 <= agreement <= 1`, silhouette is a float);
  - `test_write_report_outside_build_dir`.
- [ ] **Step 2: Run** `uv run pytest tests/test_evaluate.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** The `report.md` is a short human table: one row per question with ✓/✗, plus the summary numbers.
- [ ] **Step 4: Run.** Expected: PASS. Then run `make test`; expected: all green.
- [ ] **Step 5: Makefile** `eval:  ## score the newest build on eval/questions.yaml, log to MLflow (BUILD=dir, NO_MLFLOW=1)`.
- [ ] **Step 6: Commit** — `feat: evaluate a build with the Worker's search path`.

### Task 4: MLflow tracking + `champion` alias

**Files:**
- Create: `pipeline/tracking.py`, `tests/test_tracking.py`
- Modify: `pipeline/evaluate.py` (log unless `--no-mlflow`)

**Interfaces:**
- Produces:
  ```
  EXPERIMENT = "galaxy-refresh"; MODEL = "galaxy"; ALIAS = "champion"
  tracking_uri(data_dir: Path) -> str            # sqlite:///<abs>/mlflow/mlflow.db
  log_eval(report: dict, build_dir: Path, data_dir: Path) -> str   # run_id
  set_champion(data_dir: Path, version: str) -> str | None          # model version number, None if no eval run
  champion(data_dir: Path) -> dict | None   # {"version", "run_id", "metrics": {...}} or None
  ```
- **`log_eval`:**
  - one run named after the version, tag `galaxy.version`;
  - params: version, k, search params, `questions_sha256`, counts;
  - metrics: `recall_at_8_approved`, `mrr_approved`, `recall_at_8_all`, `mrr_all`, `agreement`, `silhouette`, `creators` (null metrics are skipped);
  - artifacts: `report.json`, `report.md`, plus the build's `manifest.json` and `worker/index_manifest.json` under `bundle/`.
- **`set_champion`:**
  - finds the newest run tagged with that version;
  - creates registered model `galaxy` if missing;
  - `create_model_version(source=f"{run.info.artifact_uri}/bundle", run_id=...)`;
  - `set_registered_model_alias`.
- **`champion`** returns `None` when the model or alias doesn't exist.

- [ ] **Step 1: Write failing tests** (`pytest.importorskip("mlflow")`, with `data_dir=tmp_path`):
  - `test_log_then_champion_roundtrip`: log v1, `set_champion(v1)`, then `champion()["version"] == "v1"` and its metrics include `recall_at_8_approved`.
  - `test_champion_none_when_unset`.
  - `test_set_champion_moves_alias`: v1 then v2 → `champion` is v2.
  - `test_artifacts_land_under_data_dir`: no `mlruns/` in cwd; files exist under `tmp_path/mlflow/artifacts`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Create the experiment with `artifact_location=str((data_dir/"mlflow"/"artifacts").resolve())` when missing. Silence MLflow's INFO logging in the CLI.
- [ ] **Step 4: Run.** Expected: PASS (each test a few seconds). Then run `make test`.
- [ ] **Step 5: Commit** — `feat: log eval runs to MLflow and track the champion build`.

### Task 5: `pipeline/gate.py`

**Files:**
- Create: `pipeline/gate.py`, `tests/test_gate.py`, `eval/gate.yaml`
- Modify: `Makefile` (target `gate`)

**Interfaces:**
- Produces:
  ```
  @dataclass GateConfig(silhouette_floor: float, recall_tolerance: float, count_ratio: float, agreement_min: float)
  load_config(path: Path) -> GateConfig      # every key required; ValueError naming a missing key
  check(report: dict, previous: dict | None, cfg: GateConfig) -> dict
      # {"version", "passed": bool, "checks": [{"name", "passed", "value", "threshold", "reason"}]}
  write_gate(result: dict, runs_dir: Path) -> Path   # data/runs/eval-<version>/gate.json
  read_gate(runs_dir: Path, version: str) -> dict | None
  main(argv) -> int    # --version (default newest build), --config eval/gate.yaml; prints each check; exit 0/1
  ```
- `previous` is `tracking.champion(...)` or `None`.
- **Check names:** `silhouette`, `recall`, `creators`, `agreement`.
- **Reasons are plain sentences.** For example: "Silhouette 0.021 is below the floor 0.024: clusters got blurrier than the baseline run."
- **Edge cases:**
  - `previous is None` → recall and creators pass with "no previous publish to compare with".
  - No approved questions, or the champion lacks `recall_at_8_approved` → recall passes as "skipped (…)".
  - creators == 0 → fail.
  - Silhouette `None` → fail.
- `eval/gate.yaml` starts with **proposed** values and a comment "proposed — confirmed at Checkpoint 4": `silhouette_floor: 0.0`, `recall_tolerance: 0.05`, `count_ratio: 0.9`, `agreement_min: 0.9`. Task 6 replaces the floor and agreement with measured values.

- [ ] **Step 1: Write failing tests:**
  - `test_all_pass`;
  - one test per failing check, asserting exact `passed` and that the reason mentions the number;
  - `test_no_previous_publish`, `test_no_approved_questions_skips_recall`, `test_zero_creators_fails`;
  - `test_missing_config_key`;
  - `test_main_exit_code_and_gate_file` (monkeypatch `tracking.champion` to `None`; report written to `tmp_path`).
- [ ] **Step 2: Run** `uv run pytest tests/test_gate.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS. Then run `make test`.
- [ ] **Step 5: Makefile** `gate:  ## pass/fail the newest build's eval report against eval/gate.yaml and the champion`.
- [ ] **Step 6: Commit** — `feat: quality gate with plain-language reasons`.

### Task 6: Eval questions, baseline, 🛑 Checkpoint 4, then wire the gate into publish

**Files:**
- Create: `eval/questions.yaml`
- Modify:
  - `eval/gate.yaml`;
  - `pipeline/publish.py` (gate check + champion);
  - `pipeline/run.py` (steps become embed → cluster → build → evaluate → gate);
  - `Makefile` (`champion`, `pipeline` help);
  - `tests/test_publish.py`, `tests/test_run.py`;
  - `README.md`, `docs/DEPLOY.md`, `docs/NOTES.md`.

**Interfaces:**
- Consumes Tasks 3–5.
- `publish.py` adds:
  ```
  gate_ok(settings, version: str) -> tuple[bool, str]
  ```
  - `all` (not `--to-dir`) calls it before connecting and refuses (exit 1, message) unless it passes or `--no-gate` is given.
  - After the live check passes, it calls `tracking.set_champion(settings.data_dir, version)`. A failure there only warns.
- `python -m pipeline.tracking champion --version V` is the CLI for marking an already-live build (`make champion VERSION=...`).

- [ ] **Step 1: Draft `eval/questions.yaml`**, about 30 entries, all `status: draft`, from the real build:
  - about 12 topic queries (science explainers, cooking, minecraft speedruns, true crime, ASMR, car reviews, …);
  - about 10 "creators like X" questions;
  - about 4 name-only questions;
  - about 4 tricky ones (a topic word, an accented name).

  Each `expected` lists 2–5 creators chosen from knowledge of the genre, **checked to exist** in the build (`unknown` must be empty). `notes` says why. Do not copy the current search results into `expected`; that would make the eval circular.
- [ ] **Step 2: Baseline.** Run `make eval` on the live build `20261124-053913-640c47c5` and record:
  - silhouette (from int8);
  - agreement;
  - recall/MRR over all drafts;
  - the misses.
- [ ] **Step 3: 🛑 Checkpoint 4. Ask the owner to:**
  1. Review `eval/questions.yaml`: fix the `expected` lists, and set `status: approved` on the ones they agree with.
  2. Read a plain-language explanation of recall@8, MRR, brute-force agreement and the int8 silhouette, with the baseline numbers.
  3. Confirm the thresholds:
     - `silhouette_floor` = baseline − 0.005;
     - `agreement_min` = baseline agreement − 0.05, rounded down to 0.05;
     - `recall_tolerance` 0.05, `count_ratio` 0.9.

  Write the approved values into `eval/gate.yaml`.
- [ ] **Step 4: Failing tests for the wiring:**
  - `test_publish_all_refuses_without_gate`, `test_publish_all_refuses_stale_or_failed_gate`;
  - `test_publish_all_no_gate_flag_warns_and_continues`;
  - `test_to_dir_and_rollback_skip_gate`;
  - `test_champion_set_after_verified_publish` (fake tracking);
  - `test_champion_failure_only_warns`;
  - `test_run_steps_include_evaluate_and_gate`.
- [ ] **Step 5: Run.** Expected: FAIL. **Implement**, run again. Expected: PASS; `make test` green.
- [ ] **Step 6: Bootstrap the champion.**
  - `make eval` (logs the live build to MLflow), `make gate`, `make champion VERSION=20261124-053913-640c47c5`.
  - Show `make mlflow` (UI on :5001) and that the alias is set.
  - `make publish-dry` must now report the gate as passed.
- [ ] **Step 7: Docs.**
  - README § Quality gate: real thresholds, the commands, what each number means.
  - DEPLOY: gate before publish, `--no-gate`, champion.
  - NOTES: baseline numbers and the owner's choices.
  - Update the Makefile header comment.
- [ ] **Step 8: Commit** in small pieces (questions, gate.yaml, publish wiring, run wiring, docs), pushing after each.

No real publish is needed in this plan: the live build doesn't change. A publish happens only on the owner's go.
