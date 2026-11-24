# Plan 4 — Chat search (Worker `search` mode + chat panel + publish) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Visitors type a question in a chat panel on the map and get the most relevant creators back. The Worker finds them by meaning, or by name for "channels like X". Clicking one flies the map to that creator. Everything ships to Cloudflare and Hostinger.

**Architecture:**
- **Worker.** The Plan 1 spike Worker (`worker/`) becomes production.
  - `POST /api/chat` checks the origin, the rate limit and the input.
  - A name lookup runs first. If the question names a creator after a cue word ("like X"), the search uses that creator's own stored vector. Otherwise the question is embedded through Workers AI.
  - The existing two-stage search runs on the bundled index.
  - `mode: "ask"` answers "not available yet".
- **Site.** The site turns the panel on only when the galaxy `manifest.json` carries a `chat.url`. A map-only build keeps working unchanged.
- **Publishing.** `pipeline/publish.py` gains a `worker` target that:
  1. copies the build's index into `worker/assets/`;
  2. runs `wrangler deploy`;
  3. checks `/health` reports the same version.

  `publish all` runs it first whenever `WORKER_URL` is set.

**Tech Stack:**
- Worker: TypeScript, Cloudflare Workers (free plan), Workers AI `@cf/baai/bge-small-en-v1.5`, the Rate Limiting binding, wrangler 4, vitest + `@cloudflare/vitest-plugin`.
- Site: Vite + TypeScript, vitest + happy-dom.
- Pipeline: Python 3.11, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-youtube-galaxy-design.md`. Delivery order steps 6 and 7, and "Chat in the first release". It applies the work order's `docs/IMPLEMENTATION_PROMPT.md` § Phase 4, minus `ask`.

**Owner decisions (2026-11-24):**
1. The panel is a collapsible side panel (a bottom sheet on phones), and clicking a result flies to the creator and opens its card.
2. A question that names a creator returns that creator's neighbours, under a header "Creators similar to X".
3. One plan covers both steps, with a hard stop before the real deploy.

## Global Constraints

- **No paid services.** Cloudflare free plan only. If something needs a paid plan, stop and ask.
- **Hostinger is static-only.** Nothing runs there.
- **Embedding model and query settings.** `@cf/baai/bge-small-en-v1.5`, `pooling: "cls"`. The query prefix is `"Represent this sentence for searching relevant passages: "` (as in the spike and `pipeline/config.py`). Normalise the vector before searching.
- **Input limit.** At most 300 characters after trimming. Empty means 400.
- **CORS.** Allow only `https://spookypharaoh.com` and `https://www.spookypharaoh.com`.
  - Local dev adds `http://localhost:5173` and `http://localhost:8080` through `worker/.dev.vars`, which must be gitignored.
  - `POST /api/chat` with a missing or other `Origin` gets 403.
  - `GET /health` is open.
- **Rate limits.** Use the free-plan Rate Limiting binding: 10 requests / 60 s per IP (key `CF-Connecting-IP`), plus a global key at 300 / 60 s. This global limit stands in for the spec's "global daily soft cap": the Workers AI free daily quota is the hard cap. When the binding is missing (tests, older wrangler), skip the limit.
- **Workers AI quota or limit errors** → `503 {status: "resting"}`. Name-lookup searches must keep working while resting, because they don't call AI.
- **`ask`.** `mode: "ask"` → `501 {status: "unavailable"}`.
- **Secrets.** None are needed. `WORKER_URL`, `SITE_ORIGIN` and the origin allow-list are not secret: allowed origins go in `wrangler.jsonc` `vars`. Never put the user's name or email in any request or config.
- **Spike routes.** Remove `/spike/*` and their tests (Plan 1 promised this).
- **Ids.** Creators are referenced by stable id. The Worker returns ids, and the site maps id → position with `g.index`.
- **Attribution.** Each result links its Fandom page (`url`). The attribution footer already exists.
- **Commits.** Small commits, push to `superpowers-rework` after each. Stage specific paths only, never `data/`, `.env`, `worker/assets/*.bin` or `worker/.dev.vars`.
- **Publishing.** No real deploy or upload without the owner's explicit go (Task 7).
- **Response contract.** Every task uses exactly this:
  ```
  POST /api/chat   body {question: string, mode?: "search" | "ask"}   (mode defaults to "search")
  200 {status:"ok", mode:"search", kind:"topic"|"similar", about:{id,title}|null,
       results:[{id,title,cluster,score,url,snippet}], index_version}
  400 {status:"bad_request", error:"empty"|"too_long"|"bad_json"|"bad_mode"}
  403 {status:"forbidden"}        429 {status:"rate_limited", retry_after:60}
  501 {status:"unavailable"}      503 {status:"resting"}      502 {status:"error"}
  OPTIONS /api/chat → 204 with CORS headers (allowed origin) or 403
  ```
  - `results` holds at most 8 entries, best first.
  - `score` is rounded to 4 decimals.
  - `cluster` is the cluster **name** string (that is what `meta.bin` stores).
  - In `similar` mode the named creator is excluded from `results`.

## Review Focus

1. **A name inside an ordinary topic question.** "videos like minecraft speedruns" must not silently turn into "similar to a creator called Minecraft". After the cue, the title must run to the end of the question; only the filler words in `FILLER` may follow it. Tested in Task 2.
2. **Duplicate titles (Target / TARGET).** The name lookup must pick deterministically: the lowest row. It must never crash, and must return that creator's id. Tested in Task 2.
3. **Workers AI throws or returns no vector.** Quota-style errors give `resting`; anything else gives `error`. Neither returns 500. A name-lookup question still answers. Tested in Task 3.
4. **The panel when the Worker is down or slow.** The browser call times out after 10 s and shows "Search is unavailable right now". The map keeps working, and a later question retries. Tested in Task 5.
5. **A mismatched Worker and site.** A Worker index whose version differs from the site's data would return ids the site doesn't know. The panel skips unknown ids and doesn't break. `publish worker` refuses to report success unless `/health` shows the build version. Tested in Tasks 4 and 5.

---

### Task 1: Worker HTTP basics — CORS, origin check, input validation

**Files:**
- Create: `worker/src/http.ts`
- Test: `worker/test/http.test.ts`

**Interfaces:**
- Produces:
  - `json(body: unknown, status?: number, headers?: HeadersInit): Response`
  - `parseOrigins(csv: string | undefined): Set<string>`
  - `corsHeaders(origin: string): Record<string, string>`. Allow-Origin is the origin itself; Allow-Methods `POST, OPTIONS`; Allow-Headers `content-type`; Max-Age `86400`; `Vary: Origin`.
  - `allowedOrigin(req: Request, allowed: Set<string>): string | null`
  - `parseChatRequest(body: unknown): {ok: true, question: string, mode: "search" | "ask"} | {ok: false, error: "empty" | "too_long" | "bad_mode"}`
  - `MAX_QUESTION = 300`.

- [ ] **Step 1: Write failing tests** in `worker/test/http.test.ts`:
  - `parseOrigins` splits on commas, trims, drops empties. `parseOrigins(undefined)` is an empty set.
  - `allowedOrigin` returns the origin for an allowed `Origin` header, and `null` for a missing one or a different one (e.g. `https://evil.example`).
  - `corsHeaders("https://spookypharaoh.com")` has exactly the headers listed in Interfaces.
  - `parseChatRequest`:
    - `{question:"  cooking  "}` → `{ok:true, question:"cooking", mode:"search"}`;
    - mode `"ask"` passes through;
    - `{question:""}` or whitespace only → `empty`;
    - 301 characters → `too_long`, and exactly 300 is ok;
    - `{question: 5}` or `null` → `empty`;
    - `{question:"x", mode:"chat"}` → `bad_mode`.
- [ ] **Step 2:** Run `cd worker && npx vitest run test/http.test.ts`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `worker/src/http.ts`. Move the `json` helper here from `handler.ts`. For `parseChatRequest`, count string length after `trim()`.
- [ ] **Step 4:** Run `cd worker && npx vitest run test/http.test.ts && npm run typecheck`. Expected: PASS.
- [ ] **Step 5:** Commit `worker/src/http.ts worker/test/http.test.ts` with the message "feat(worker): CORS allow-list and chat input validation", then push.

### Task 2: Worker name lookup and creator vectors

**Files:**
- Create: `worker/src/names.ts`
- Test: `worker/test/names.test.ts` (build a small `MetaView` and `IndexView` in the test with a local helper `makeMeta(records)` that encodes the same layout `parseMeta` reads; no fixture files)

**Interfaces:**
- Consumes: `MetaView`, `readRecord`, `IndexView` from `src/format.ts`; `normalize` from `src/search.ts`.
- Produces:
  - `foldName(s: string): string`. Byte-for-byte the same rules as `web/src/search.ts` `fold`: NFKD, strip marks, lowercase, non-letter/digit runs → one space, trim.
  - `buildNameIndex(meta: MetaView): Map<string, number>`. Folded title → lowest row. Titles that fold to fewer than 3 characters are skipped.
  - `findNamedCreator(question: string, names: Map<string, number>): number | null`
  - `creatorVector(index: IndexView, row: number): Float32Array`. Int8 × the row's scale, normalised.
  - `CUES`: the cue phrases, matched as whole folded words: `like`, `similar to`, `such as`, `alternatives to`, `alternative to`, `resembling`, `than`.
  - `FILLER`: words allowed after a title: `videos`, `video`, `content`, `channel`, `channels`, `stuff`, `please`, `youtube`, `on`.

- [ ] **Step 1: Write failing tests:**
  - **`foldName`:** `"Café  Ñandú!"` → `"cafe nandu"`; `"ねくろちゃん -Yamaguro Nekuro-"` keeps the kana and gives `"ねくろちゃん yamaguro nekuro"`.
  - **Whole question:** `findNamedCreator("Markiplier", names)` and `"markiplier?"` match the Markiplier row.
  - **Cue at the start:** `"channels like Markiplier"`, `"YouTubers similar to Mark Rober"` and `"more like dream"` match.
  - **Longest match wins:** with titles "Mark" and "Mark Rober", `"like mark rober videos"` → the Mark Rober row. Filler words after a title are allowed.
  - **No cue, no match:** `"minecraft speedruns"` → `null` even if a creator titled "Minecraft" exists. Only a whole-question match or a cue triggers.
  - **The title must end the question:** `"videos like minecraft speedruns"` → `null` even with a creator titled "Minecraft". "speedruns" is not filler, so this stays a topic search.
  - **Short titles:** titles shorter than 3 folded characters never match ("like ab" → `null`).
  - **Duplicates:** with two records titled "Target"/"TARGET" at rows 2 and 3, `buildNameIndex` maps `"target"` → 2.
  - **`creatorVector`:** returns a unit-length vector whose cosine with the original float row is > 0.99 (build the row by quantising a known vector in the test).
- [ ] **Step 2:** Run `cd worker && npx vitest run test/names.test.ts`. Expected: FAIL.
- [ ] **Step 3:** Implement `worker/src/names.ts`.
  - Matching: fold the question, split it into words, and drop trailing `FILLER` words. If the whole remainder is a key, return it. Otherwise, at each position just after a cue (cues are matched as word sequences), return the row if the words from there to the end form a key. When several cues match, the earliest cue wins.
  - `buildNameIndex` decodes every record once with `readRecord`. That costs ~20k `JSON.parse` calls, done at isolate startup (Task 3).
- [ ] **Step 4:** Run `cd worker && npx vitest run test/names.test.ts && npm run typecheck`. Expected: PASS.
- [ ] **Step 5:** Commit with the message "feat(worker): creator name lookup and stored creator vectors", then push.

### Task 3: `/api/chat` handler, rate limits, resting, spike removal

**Files:**
- Create: `worker/src/chat.ts`
- Modify:
  - `worker/src/handler.ts`: route table, injected deps; remove the spike routes and `mulberry32`.
  - `worker/src/env.ts`: add `ALLOWED_ORIGINS?: string`, `PER_IP?: RateLimit`, `GLOBAL?: RateLimit`.
  - `worker/src/index_loader.ts`: `LoadedIndex` gains `names: Map<string, number>`, built in `validateLoaded`'s callers.
  - `worker/src/main.ts`: build `names` at startup; warm up through `searchChat`.
  - `worker/wrangler.jsonc`: add `vars.ALLOWED_ORIGINS` and the two `ratelimits` bindings.
  - `worker/wrangler.test.jsonc`: add `vars.ALLOWED_ORIGINS: "https://spookypharaoh.com"`.
  - `.gitignore`: add `worker/.dev.vars`.
- Delete: `worker/test/spike.test.ts` (its `/health` and `getIndex` cache cases move to `worker/test/health.test.ts` if not already there).
- Create: `worker/.dev.vars.example`, holding `ALLOWED_ORIGINS=https://spookypharaoh.com,http://localhost:5173,http://localhost:8080`.
- Test: `worker/test/chat.test.ts`

**Interfaces:**
- Consumes: Task 1's `json`, `allowedOrigin`, `corsHeaders`, `parseOrigins`, `parseChatRequest`; Task 2's `findNamedCreator`, `creatorVector`; `twoStageSearch` and `normalize` from `src/search.ts`; `readRecord`.
- Produces:
  - `type Embed = (text: string) => Promise<Float32Array>`
  - `class AiQuotaError extends Error`
  - `aiEmbed(env: Env): Embed`. Calls `env.AI.run(EMBED_MODEL, {text: [QUERY_PREFIX + text], pooling: "cls"})`. It throws `AiQuotaError` when the error message or code matches `/quota|neuron|allocation|rate.?limit|429|3036|4006/i`, and a plain `Error` when no vector comes back.
  - `searchChat(loaded: LoadedIndex, question: string, embed: Embed): Promise<ChatOk>`. `ChatOk` is the 200 body type from the response contract.
  - `createHandler(getIndex: IndexSource, deps?: {embed?: (env: Env) => Embed}): ExportedHandler<Env>`

- [ ] **Step 1: Write failing tests** in `worker/test/chat.test.ts`.
  - **Setup:** use `createHandler(getIndex, {embed: () => fakeEmbed})` and call `.fetch(new Request(...), env)` directly. `env` comes from `cloudflare:workers`, with `ALLOWED_ORIGINS` set. `fakeEmbed` returns `creatorVector` of a fixture row, or throws as needed.
  - **Topic question:** POST `{question:"anything"}` with an allowed Origin → 200.
    - `kind:"topic"`, `about:null`;
    - ≤ 8 results sorted by score;
    - each result has `id`, `title`, `cluster`, `url`, `snippet`, and a `score` with ≤ 4 decimals;
    - `index_version:"fixture-1"`;
    - the response carries `Access-Control-Allow-Origin` = that origin.
  - **Results match a direct search:** they equal `twoStageSearch(fakeVector, …, {k: 8})` mapped through `readRecord`. This proves it is the same search.
  - **Name question:** `{question:"creators like Synthetic 7"}` → `kind:"similar"`, `about:{id: <row of "Synthetic 7">'s id, title:"Synthetic 7"}`. The results don't contain that id, and `fakeEmbed` was **not** called.
  - **Ask mode:** `mode:"ask"` → 501 `{status:"unavailable"}`.
  - **Bad input:**
    - bad JSON → 400 `bad_json`;
    - empty → 400 `empty`;
    - 301 chars → 400 `too_long`;
    - `mode:"x"` → 400 `bad_mode`.
  - **Origin:** no Origin or `https://evil.example` → 403 `{status:"forbidden"}`. OPTIONS with an allowed origin → 204 with the CORS headers; with a bad origin → 403.
  - **AI failures:**
    - `fakeEmbed` throwing `AiQuotaError` → 503 `{status:"resting"}`;
    - throwing `Error` → 502 `{status:"error"}`;
    - a name question while `fakeEmbed` throws `AiQuotaError` → still 200 `similar`.
  - **Rate limits:** `env.PER_IP` stub `{limit: async () => ({success:false})}` → 429 `{status:"rate_limited", retry_after:60}`; the same for `GLOBAL`. When neither binding is set, there is no limit.
  - **Other routes:**
    - `GET /spike/search?seed=1` → 404 (spike removed);
    - `GET /health` → `{ok:true, index_version:"fixture-1"}`;
    - unknown path → 404;
    - `GET /api/chat` → 405.
- [ ] **Step 2:** Run `cd worker && npm test`. Expected: the new tests FAIL. The old spike tests are deleted in this task.
- [ ] **Step 3: Verify the Rate Limiting binding before wiring it.** Check Cloudflare's current docs for the "Rate Limiting" Workers binding: its availability on the free plan, and the wrangler config key (`ratelimits` with `name`, `namespace_id`, `simple: {limit, period}`, where period is 10 or 60).
  - If it is free and the installed wrangler accepts the key, use it.
  - If not, implement the same `RateLimit`-shaped interface in-isolate (a per-key fixed 60 s window in a `Map`, capped at 10k keys) and ledger the ruling.
- [ ] **Step 4: Implement.**
  - **Request order:** route → method → origin check (POST and OPTIONS) → rate limits (POST) → parse JSON → `parseChatRequest` → `ask` → `searchChat`.
  - **`searchChat`:** name lookup first. If it matches a row: use `creatorVector`, search k = 9, drop that row and any result with the same id, and keep 8. Otherwise: `embed`, `normalize` (null → `Error`), search k = 8.
  - **Error mapping:** catch `AiQuotaError` → 503; other errors → 502. Log both with `console.error` (only the error message, never the question).
  - **Startup:** `main.ts` builds `names` once at startup. `index_loader.ts`'s `load` builds it too, for the test path.
  - **`wrangler.jsonc`:**
    ```jsonc
    "vars": { "ALLOWED_ORIGINS": "https://spookypharaoh.com,https://www.spookypharaoh.com" },
    "ratelimits": [
      { "name": "PER_IP", "namespace_id": "4101", "simple": { "limit": 10, "period": 60 } },
      { "name": "GLOBAL", "namespace_id": "4102", "simple": { "limit": 300, "period": 60 } }
    ]
    ```
  - **Types:** regenerate `worker-configuration.d.ts` with `npx wrangler types` if the binding types change.
- [ ] **Step 5:** Run `cd worker && npm test && npm run typecheck`. Expected: all PASS, with no spike tests left. Also run `npm run bench` and note the search p50/p99 in the commit message. Expected: same order as the Plan 1 bench (~2 ms).
- [ ] **Step 6:** Commit the worker source, the tests, `wrangler*.jsonc`, `.dev.vars.example`, `.gitignore` and `worker-configuration.d.ts` if changed, with the message "feat(worker): /api/chat search mode with name lookup, CORS, rate limits; drop spike routes", then push.

### Task 4: Pipeline — chat URL in the manifest, `publish worker`

**Files:**
- Modify:
  - `pipeline/config.py`: `worker_url: str | None = None` read from `WORKER_URL`, with a trailing `/` stripped.
  - `pipeline/build_artifacts.py`: when `settings.worker_url` is set, `manifest.json` gains `"chat": {"url": "<WORKER_URL>/api/chat"}`; otherwise there is no `chat` key.
  - `pipeline/publish.py`: new target `worker`; `all` runs `worker` first when `worker_url` is set.
  - `Makefile`: `publish-chat` (Worker only) and `chat-dev`.
- Test: `tests/test_publish.py`, `tests/test_build_artifacts.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `publish.stage_worker(build_dir: Path, assets_dir: Path) -> list[str]`. It copies `worker/{index.bin,centroids.bin,meta.bin,index_manifest.json}` from the build into `worker/assets/`, then returns the copied names. It raises `FileNotFoundError` naming the missing file.
  - `publish.deploy_worker(worker_dir: Path, run=subprocess.run) -> None`. Runs `npx wrangler deploy` in `worker_dir` and raises `RuntimeError` on a non-zero exit.
  - `publish.verify_worker(url: str, version: str, fetch=_http_get, tries=6, wait=5.0, sleep=time.sleep) -> bool`. Calls `GET {url}/health` until `index_version == version`.
  - The CLI: `python -m pipeline.publish worker [--version V] [--dry-run]`.

- [ ] **Step 1: Write failing tests:**
  - `load_settings` with `WORKER_URL=https://x.workers.dev/` gives `worker_url == "https://x.workers.dev"`. Unset gives `None`.
  - `build(...)` with a settings/`worker_url` argument writes `manifest["chat"] == {"url": "https://x.workers.dev/api/chat"}`. Without one, there is no `chat` key. Thread `chat_url: str | None` into `build()` as a parameter, so the test needs no env.
  - `stage_worker` copies the four files byte-identical and overwrites stale ones. With a missing `meta.bin` it raises an error naming it.
  - `deploy_worker` with a fake `run`:
    - it is called with `["npx", "wrangler", "deploy"]` and `cwd=worker_dir`;
    - a non-zero return code raises `RuntimeError`.
  - `verify_worker`:
    - true when the fake fetch eventually returns the version;
    - false after `tries` attempts of a wrong version, with `sleep` called `tries-1` times;
    - fetch exceptions count as a failed try.
  - `main(["worker", "--dry-run"])` prints the four files it would stage and the deploy command, and runs nothing.
  - `main(["worker", "--stage-only"])` stages the files and never calls `deploy_worker`.
  - When `worker_url` is set, `main(["all", ...])` calls the worker steps before the Hostinger upload (monkeypatch both and record the order). Without `worker_url`, `all` doesn't touch the Worker.
  - A failed `verify_worker` makes `all` stop before uploading to Hostinger, with exit code 1.
- [ ] **Step 2:** Run `uv run pytest tests/test_publish.py tests/test_build_artifacts.py tests/test_config.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement.
  - **`worker` target:** `stage_worker(newest or --version build)` → `deploy_worker` → `verify_worker(settings.worker_url, version)`. Without `WORKER_URL`, it deploys, prints "Set WORKER_URL in .env to the URL wrangler printed, then re-run", and returns 0. This is the first deploy.
  - **`all`:** worker (when `worker_url` is set), then galaxy, then home.
  - **Makefile:**
    ```make
    publish-chat: ## deploy only the Worker with the newest build's index, then check /health
    	$(PY) pipeline.publish worker
    chat-dev:     ## local Worker on :8787 with the newest build's index (Workers AI runs remotely)
    	$(PY) pipeline.publish worker --stage-only && cd worker && npx wrangler dev --port 8787
    ```
    Add `--stage-only` (stage, no deploy) and add both targets to `.PHONY`.
- [ ] **Step 4:** Run `uv run pytest -q && uv run ruff check pipeline tests`. Expected: all PASS.
- [ ] **Step 5:** Commit with the message "feat(publish): Worker-first deploy with /health check; chat URL in the manifest", then push.

### Task 5: Site — chat client and side panel

**Files:**
- Create: `web/src/chat.ts`, `web/src/ui/chat-panel.ts`
- Modify:
  - `web/src/data.ts`: `Manifest` gains `chat?: {url: string}`.
  - `web/src/main.ts`: mount the panel when there is a chat URL.
  - `web/src/style.css`: `.chat` panel styles.
  - `web/index.html`: `#chat-slot` gets `class="chat"` and `aria-label="Ask about creators"`.
- Test: `web/test/chat.test.ts`, `web/test/chat-panel.test.ts`

**Interfaces:**
- Consumes: the Task 3 response contract; `Galaxy` (`g.index`, `g.titles`, `g.clusters`, `g.cluster`); `selectCreator(app, i)`.
- Produces:
  - `chatUrl(manifest: Manifest): string | null`. `import.meta.env.VITE_CHAT_URL` wins, then `manifest.chat?.url`, then `null`.
  - `askChat(fetchFn: typeof fetch, url: string, question: string, timeoutMs = 10000): Promise<ChatResult>`. `ChatResult` is the contract's bodies as a union on `status`, plus `{status: "offline"}` for network errors, timeouts or non-JSON replies.
  - `mountChatPanel(el: HTMLElement, g: Galaxy, ask: (q: string) => Promise<ChatResult>, onPick: (i: number) => void): {open(): void; close(): void}`

- [ ] **Step 1: Write failing tests.**

  **`chat.test.ts`**, using the `fakeFetch` helper (extend it with a status/delay option if needed):
  - `askChat` POSTs JSON `{question}` with `content-type: application/json` and returns the parsed body for 200, 400, 429, 501 and 503.
  - A thrown fetch → `offline`; a non-JSON body → `offline`; no reply within `timeoutMs` (fake timers) → `offline`, with the fetch aborted.
  - `chatUrl` prefers the env, then the manifest, then `null`.

  **`chat-panel.test.ts`** (happy-dom):
  - Submitting the form calls `ask` with the trimmed text, and shows "Searching…" while pending.
  - **`ok` + `topic`:** one button per result that `g.index` knows (an unknown id is skipped). Each shows the title, the cluster name with its colour swatch (looked up via `g.clusters[g.cluster[i]]`) and the snippet. Clicking one calls `onPick(i)`.
  - **`ok` + `similar`:** the header reads exactly `Creators similar to <title>`, and the header title is a button that calls `onPick` for `about.id`.
  - **Empty results:** "No matching creators found."
  - **Status messages:**
    - `resting`: "Search is resting for today (free quota used up). Try again tomorrow, or search by name above."
    - `rate_limited`: "Too many questions at once. Wait a minute and try again."
    - `offline` / `error`: "Search is unavailable right now."
    - `bad_request` `too_long`: "Keep it under 300 characters."
    - `unavailable`: "Answers are coming soon."
  - **Input rules:** submitting empty text doesn't call `ask`; the input has `maxlength="300"`.
  - **Hint (owner addition, 2026-11-24):** before any question, the results region shows exactly `Try a topic (science explainers) or "channels like Vsauce". Search finds creators by what their wiki pages say; it can't rank creators or answer who likes whom.` The hint goes away once a question is asked.
  - **Overlapping questions:** a second question while the first is pending: only the latest result is shown (stale responses are ignored).
  - **Close:** the close button hides the panel, and `open()` shows it again with the last results intact.
- [ ] **Step 2:** Run `cd web && npx vitest run test/chat.test.ts test/chat-panel.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - **Panel content:**
    - a header: "Ask the galaxy", plus a close button;
    - a form with an input (placeholder "e.g. science explainers, or channels like Vsauce") and an "Ask" button;
    - an `aria-live="polite"` results region;
    - a small footer "Results by meaning, from YouTube Wiki text."
  - **`main.ts`:**
    - when `chatUrl(manifest)` is non-null, mount on `#chat-slot`, un-hide it, and add an "Ask" toggle button to `#toggles` (the same pattern as the Clusters button, with `aria-controls="chat-slot"`);
    - start open on wide screens and closed on phones;
    - `onPick(i)` calls `selectCreator(app, i)` (which flies to the creator), and on phones (`max-width: 699px`) also closes the panel;
    - with no chat URL, nothing changes (the slot stays hidden).
  - **CSS:**
    - `.chat` uses the same right-column geometry as `.detail` (right gutter, full height, 340px) at `z-index: 2`;
    - `.detail` stays `z-index: 3`, so an open card covers the chat, and closing the card reveals the results again;
    - on phones it is a bottom sheet like `.legend`, at `max-height: 55%`;
    - `.chat.closed { display: none; }`.
- [ ] **Step 4:** Run `cd web && npm test && npm run typecheck`. Expected: all PASS, with the existing tests unchanged.
- [ ] **Step 5:** Commit with the message "feat(web): chat side panel — meaning search and 'similar to' results that fly to creators", then push.

### Task 6: Local demo and docs — 🛑 Checkpoint 3

**Files:**
- Modify:
  - `docs/DEPLOY.md`: a new "Cloudflare Worker (chat)" section:
    - one-time `npx wrangler login`;
    - the first `make publish-chat`;
    - copying the printed `*.workers.dev` URL into `.env` as `WORKER_URL`;
    - then `make build` and `make publish`;
    - what `resting` means;
    - how to roll back the Worker (`npx wrangler rollback` in `worker/`).
  - `README.md`: the command list (`chat-dev`, `publish-chat` no longer marked planned) and a "Rerunning things" line: after any `make build`, `make publish` also redeploys the Worker when `WORKER_URL` is set.
  - `docs/NOTES.md`: a Plan 4 section with the bench numbers.
  - `scripts/spike_load.sh` → `git mv` to `scripts/chat_load.sh`. It now POSTs `{question:"channels like <title>"}` from a list of 20 known titles. These are name lookups, so they use no Workers AI quota. It sets an `Origin: https://spookypharaoh.com` header. Usage: `scripts/chat_load.sh WORKER_URL [N=300]`.

- [ ] **Step 1:** Write the docs and script changes above. Then run `bash -n scripts/chat_load.sh`. Expected: no output.
- [ ] **Step 2: Local end to end.**
  1. `cp worker/.dev.vars.example worker/.dev.vars`
  2. `make chat-dev` (terminal 1)
  3. `make web-data && VITE_CHAT_URL=http://localhost:8787/api/chat make web-dev` (terminal 2)

  Then, with curl and the browser:
  - `curl -s -X POST localhost:8787/api/chat -H 'Origin: http://localhost:5173' -H 'content-type: application/json' -d '{"question":"science explainers"}'` → `status: ok`, `kind: topic`, 8 results;
  - `{"question":"channels like Markiplier"}` → `kind: similar`, `about.title: "Markiplier"`;
  - without the Origin header → 403.
- [ ] **Step 3:** Run `make test` (pytest, worker and web suites). Expected: all PASS. Commit with the message "docs: Cloudflare Worker deploy, chat dev, chat load script", then push.
- [ ] **Step 4: 🛑 Checkpoint 3. Stop.** Ask the owner to try the local demo (the commands from Step 2) and confirm the look and feel. Give them five questions to try:
  - "science explainers"
  - "channels like Markiplier"
  - "minecraft speedruns"
  - "cooking"
  - "creators like Vsauce"

  Apply any look-and-feel changes they ask for (TDD for behaviour changes) before Task 7.

### Task 7: Deploy and publish chat — 🛑 owner's go required

- [ ] **Step 1: 🛑 Ask for the go.** Show `make publish-dry` and `uv run python -m pipeline.publish worker --dry-run`. Do nothing further until the owner says go.
- [ ] **Step 2: First deploy.**
  1. Run `make publish-chat`. It deploys and prints the `workers.dev` URL; check it with `curl $URL/health`.
  2. Ask the owner to put that URL in `.env` as `WORKER_URL`. Claude does not edit `.env`.
  3. Run `make build`, then `make publish`. `publish all` redeploys the Worker with the same version, verifies `/health`, then uploads the site.

  Expected:
  - `/health` reports the new build version;
  - the live manifest reports the same version and contains `chat.url`.
- [ ] **Step 3: Live check.** On https://spookypharaoh.com/galaxy/, ask the five Checkpoint 3 questions and screenshot the panel. Then `curl` the Worker from a disallowed origin (expect 403), and send 12 quick requests from one IP (expect a 429 by the 11th).
- [ ] **Step 4: Issue #1 re-measure.** Run `scripts/chat_load.sh $WORKER_URL 300`, then `uv run python scripts/worker_cpu.py --since <start>` once analytics catch up.
  - Record p50/p90/p99 CPU in `docs/NOTES.md`.
  - Comment the numbers on issue #1. Close it only if p99 ≤ 10 ms; otherwise leave it open with the new numbers.
  - Commit `docs/NOTES.md`, then push.
- [ ] **Step 5:** Update the memory notes and README status. In the final message, list the rulings, the deferred minors, and the next step: Plan 5, which covers the eval set, MLflow and the quality gate, including a Python mirror of the name lookup for eval parity.
