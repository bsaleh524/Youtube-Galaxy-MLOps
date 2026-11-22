# Plan 3 — Static Site, Home Page and Map-Only Publish

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the galaxy website and the spookypharaoh.com home page, then publish the map (no chat yet) to Hostinger. Stop at 🛑 Checkpoint 3a so the owner can review the site and approve the real upload.

**Architecture:**
- **Website (`web/`):** Vite + TypeScript + deck.gl, no framework.
  - It reads one Plan 2 build (`data/artifacts/galaxy/<version>/`) as static JSON.
  - Pure logic goes in small modules tested with vitest: data loading, colours, view fitting, search, URL hash.
  - The DOM pieces (detail panel, legend, footer) are tested with happy-dom.
  - The deck.gl map is a thin wrapper, checked by eye.
- **Publishing:** one Python module, `pipeline/publish.py`.
  - It lays out the exact Hostinger folder tree and writes it through a `Remote` interface.
  - `LocalRemote` writes to a local folder, so the same code stages the site for local preview.
  - `SftpRemote` writes to Hostinger.

**Tech Stack:**
- Website: TypeScript, Vite, `@deck.gl/core` + `@deck.gl/layers` (9.4.x on 2026-11-19; pin whatever `npm install` resolves and record it), vitest, happy-dom.
- Publishing: Python 3.11, paramiko (already in the `pipeline` group), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-15-youtube-galaxy-design.md`.
- Delivery steps 4–5 and the sections "Site structure", "Thumbnails" and "Chat in the first release" apply.
- They **override** Phases 3 and 7 of `docs/IMPLEMENTATION_PROMPT.md` wherever the two differ.
- Plan 2 (`docs/superpowers/plans/2026-11-17-plan-2-pipeline.md`) produces the files this plan reads.

## Owner decisions this plan follows (2026-11-19, Checkpoint 2)

- **Placeholder names go live.** The 49 keyword names (e.g. "music · songs · artists") ship in the first publish. This replaces the spec's "First publish: every cluster has a real name". Proper names come with issues #5 and #6.
- **Issue #5 comes after this plan,** before the site goes public. Nothing here may assume that cluster count, names or colours stay fixed. Read them from `clusters.json` every time.
- **k = 120.** The current build is `20261118-171847-c390a7b8`.

**Builder's calls in this plan (owner may override at the checkpoint):**
- **Chat widget moves to Plan 4.** The spec puts a hidden widget in Phase 3. Plan 4 defines the production `/api/chat` contract, and a map-only publish would not show the widget anyway. So this plan only reserves an empty `<aside id="chat-slot" hidden>`.
- **Home page:** plain static files in `web/home/` (no build step). It is published to the root folder.
- **Shareable links:** `#/creator/<id>` and `#/cluster/<key>`. The spec's first audience is "something fun to share".

## Facts carried in (docs/NOTES.md, Plan 2)

- **Build files:**
  - `manifest.json`: `version, built_at, creators, clusters, embedding_model, metrics, attribution, inputs, files`.
  - `nodes.json`: columnar `{id, title, cluster, x2, y2, x3, y3, z3}`. `cluster` is the position in `clusters.json`.
  - `neighbors.json`: `{id: [10 ids]}`.
  - `clusters.json`: `[{key, name, colour, size, leader_id, cx2, cy2, cx3, cy3, cz3}]`.
  - `details/cluster_<key>.json`: `{id: {bio, source_url, youtube_url, thumbnail}}`.
  - `worker/…`: **never uploaded to Hostinger.**
- **Sizes (raw / gzip):**
  - `nodes.json`: 1.38 / 0.49 MB.
  - `neighbors.json`: 3.69 / 0.81 MB.
  - `clusters.json`: 20 KB.
  - `details/`: 16 MB in 120 files (~130 KB each).
- **Loading strategy:** the first paint needs only manifest + clusters + nodes (~0.5 MB gzip). Neighbours load in the background after first paint. Details load per cluster when a creator in that cluster is opened.
- **Thumbnails** are `static.wikia.nocookie.net` URLs. They load only in the detail panel, lazily, with `referrerpolicy="no-referrer"` and a text fallback.
- **Same-title pair:** `TARGET` `fandom_449281` and `Target` `fandom_372805`. A duplicate placeholder name also exists ("games · game · gaming" ×2), so names are never used as keys.
- **Existing scaffolding:**
  - `web/` has a Vite skeleton (`base: process.env.SITE_BASE_PATH ?? "/galaxy/"`) and `npm test` = `vitest run --passWithNoTests`.
  - `.env.example` has `HOSTINGER_*`, `SITE_BASE_PATH=/galaxy/` and `SITE_ORIGIN=https://spookypharaoh.com`.
  - `pipeline/config.py` `Settings` does **not** read the Hostinger variables yet.

## Global Constraints

Plans 1–2's constraints still apply:
- $0, no paid services.
- Commit **and push** after every task to `superpowers-rework`, with small commits. Stage specific paths only, never `data/`, `.env`, `node_modules/`, `web/dist/` or `web/.devdata/`.
- Verify external facts (LiteSpeed `.htaccess` support, Hostinger SFTP host/port, Fandom licence version) against official docs or the live page. Record each in `docs/NOTES.md` with URL and date.
- Tests never touch the network or Hostinger.

New for this plan:
- **Hostinger is static-only.** Only HTML, CSS, JS, JSON, images and `.htaccess` go there.
- **Folder ownership:**
  - The galaxy publish writes only inside `HOSTINGER_REMOTE_DIR` (`public_html/galaxy`).
  - The home publish writes only the files it owns, directly inside `HOSTINGER_HOME_DIR` (`public_html`). It never writes into subfolders and never writes a root `.htaccess`.
- **`manifest.json` is the pointer and is uploaded last.** Everything else lives under versioned paths (`data/<version>/…`, Vite's hashed `assets/…`).
- **Ids, not positions.** All lookups go through `id → index` maps. URL hashes carry ids and cluster keys, never array indices.
- **Never put wiki text into `innerHTML`.** Use `textContent` and attribute setters. Bios are untrusted.
- **Attribution on every galaxy page:**
  - Credit "YouTube Wiki (Fandom)".
  - State the CC BY-SA licence with a link to the licence.
  - Link each creator's source page in the detail panel.
- **Secrets never printed.** Dry-run and logs never show the SFTP password or key contents. The website never contains any secret.
- **Host keys are checked.** `SftpRemote` uses the user's `known_hosts` and refuses unknown hosts (no `AutoAddPolicy`).
- **Look:** dark "galaxy" theme with CSS custom properties.
  - 16 px side gutters, no horizontal scroll at 360 px width.
  - Visible keyboard focus.
  - `prefers-reduced-motion` disables camera transitions.

## Hostinger layout produced by this plan

```
public_html/                      # HOSTINGER_HOME_DIR — home publish touches only these files:
  index.html, home.css            #   from web/home/
  galaxy/                         # HOSTINGER_REMOTE_DIR — galaxy publish touches only this folder:
    index.html, .htaccess         #   from web/dist (built with SITE_BASE_PATH=/galaxy/)
    assets/<hashed>.js|css        #   from web/dist/assets
    data/<version>/nodes.json, neighbors.json, clusters.json, details/cluster_<key>.json
    manifest.json                 #   copy of data/<version>'s build manifest; uploaded LAST
```

Local mirrors of the same tree:
- `data/stage/public_html/` (`make stage`, served by `make preview`).
- `web/.devdata/` (data part only, served by `make web-dev`).

## Review Focus

1. **A visitor whose page loaded before a publish.**
   - Their old JS asks for the old version's files, which must still exist.
   - Publishing keeps the 3 newest data versions and never deletes the one the live manifest points to.
   - `manifest.json` and `index.html` are never cached.
   - → Task 7 test `test_prune_keeps_three_and_live`; Task 6 `.htaccess` test.
2. **An upload that dies halfway.** A failed upload stops immediately and never uploads `manifest.json`, so the live site stays on the old version. A re-run picks up where it left off. → Task 1 test `test_execute_stops_before_manifest_on_failure`.
3. **Hostinger's default placeholder page.** `public_html/default.php` or `index.php` would shadow the new `index.html`, and the home publish must never touch `galaxy/` or other folders. → Task 7 tests `test_home_plan_touches_only_own_files` and `test_preflight_warns_on_placeholder_index`.
4. **Same-title creators** (`TARGET` / `Target`).
   - Search lists both, each with its cluster name.
   - Picking either opens that id.
   - A `#/creator/<id>` link opens the right one.
   - → Task 4 tests `same-title creators both match` and the hash round-trip.
5. **Missing or broken detail data:**
   - a thumbnail that 404s or is hotlink-blocked → text card;
   - a details file that fails to load → panel still shows title, cluster and neighbours, plus "Details couldn't load" and a Retry button;
   - a `null` `youtube_url` → no YouTube link;
   - a bio containing HTML → shown as text.
   - → Task 5 tests.

---

### Task 1: Publish layout and local staging

**Files:**
- Create: `pipeline/publish.py`
- Create: `tests/test_publish.py`
- Modify: `pipeline/build_artifacts.py` (attribution `license_url`; pass through `missing_from_wiki_since`)
- Modify: `tests/test_build_artifacts.py`
- Modify: `pipeline/config.py`, `tests/test_config.py`, `.env.example` (Hostinger and site settings)
- Modify: `web/vite.config.ts`
- Modify: `.gitignore` (add `web/.devdata/`)
- Modify: `Makefile` (`web-data`, `stage`)
- Modify: `docs/NOTES.md`

**Interfaces:**
- Consumes: a build dir from `pipeline.build_artifacts` (Plan 2).
- Produces:
  - **`Settings` gains** `hostinger_sftp_host`, `hostinger_sftp_port: int | None`, `hostinger_sftp_user`, `hostinger_sftp_password`, `hostinger_sftp_key_path`, `hostinger_remote_dir = "public_html/galaxy"`, `hostinger_home_dir = "public_html"`, `site_base_path = "/galaxy/"`, `site_origin = "https://spookypharaoh.com"`, mapped to the matching env names. Add `HOSTINGER_HOME_DIR=public_html` to `.env.example`.
  - `galaxy_files(build_dir: Path, dist_dir: Path | None) -> list[tuple[str, Path]]`. Pairs are (remote path relative to the galaxy dir, local file), **in upload order**:
    1. `data/<version>/**`;
    2. then (if `dist_dir`) `assets/**`, `.htaccess`, `index.html`;
    3. **`manifest.json` last**.

    `worker/` is excluded. `dist_dir=None` means data only.
  - `home_files(home_dir: Path) -> list[tuple[str, Path]]`: top-level files of `web/home/` only, sorted.
  - `class Remote(Protocol)`: `exists(path) -> bool`, `size(path) -> int | None`, `listdir(path) -> list[str]`, `makedirs(path)`, `put(local: Path, path: str)` (atomic: upload to `path + ".tmp"`, then rename), `rmtree(path)`, `read_text(path) -> str | None`.
  - `LocalRemote(root: Path)`.
  - `@dataclass Action(op: Literal["put", "skip", "rmtree"], path: str, local: Path | None, reason: str)`.
  - `plan_uploads(files, remote, base: str, always: set[str]) -> list[Action]`. It skips a file when the remote has the same size, except paths in `always`. For the galaxy, `always = {"manifest.json", "index.html", ".htaccess"}`.
  - `execute(actions, remote, log=print) -> None`. Runs in order, stops at the first exception, and re-raises.
  - `newest_build(artifacts: Path) -> Path`.
  - CLI: `python -m pipeline.publish galaxy|home|all [--to-dir DIR] [--data-only] [--version V] [--dry-run]`.

- [x] **Step 1: Write the failing tests** in `tests/test_publish.py`. Build a tiny fake build dir (manifest with `version`, `nodes.json`, `clusters.json`, `neighbors.json`, `details/cluster_c001.json`, `worker/index.bin`) and a fake dist (`index.html`, `.htaccess`, `assets/app-1a2b.js`):
  - `test_galaxy_files_order`: the last item is `("manifest.json", <build>/manifest.json)`; `index.html` comes after every `assets/` path; every data path starts with `data/<version>/`; no path contains `worker`.
  - `test_galaxy_files_data_only`: with `dist_dir=None`, no `assets/`, `index.html` or `.htaccess`; manifest is still last.
  - `test_plan_skips_same_size_except_always`: with a `LocalRemote` already holding an identical `data/<v>/nodes.json` and `manifest.json`, nodes → `skip` and manifest → `put`.
  - `test_execute_stops_before_manifest_on_failure`: a `LocalRemote` subclass raising `OSError` on its 2nd `put`. `execute` raises, `manifest.json` does not exist in the remote, and no `*.tmp` file is left behind.
  - `test_stage_cli_writes_mirror`: `main(["galaxy", "--to-dir", tmp, "--version", v])` with patched artifact/dist paths creates `tmp/manifest.json` byte-equal to the build's manifest.
  - In `tests/test_build_artifacts.py`:
    - `test_details_pass_through_missing_flag`: a record with `missing_from_wiki_since: "2026-12-01"` keeps that key in its details entry; records without it have no such key.
    - `test_attribution_has_license_url`.
  - In `tests/test_config.py`: Hostinger env values are read; port is cast to int; blank values become `None`; defaults match the list above.
- [x] **Step 2: Run** `uv run pytest tests/test_publish.py tests/test_build_artifacts.py tests/test_config.py -q`. Expected: FAIL (no module / missing keys).
- [x] **Step 3: Verify the licence.**
  - Open one creator page on youtube.fandom.com in a browser (a single page view, not a scrape) and read the footer licence line.
  - Set `ATTRIBUTION["license"]` to the exact name (e.g. "CC BY-SA 3.0") and add `license_url` (the Creative Commons deed it links to).
  - Record both in NOTES with the URL and date.
- [x] **Step 4: Implement.**
  - `build_artifacts.py`: add `missing_from_wiki_since` to a details entry only when the record has it.
  - `publish.py`:
    - Implement the interfaces above. CLI defaults: build = `newest_build(data/artifacts/galaxy)`; dist = `web/dist`; home = `web/home`.
    - `--to-dir DIR` uses `LocalRemote(DIR)`. Galaxy goes to `DIR/<basename of HOSTINGER_REMOTE_DIR>` when the target is `all`, and to `DIR` itself when the target is `galaxy`.
    - `--dry-run` prints one line per action (`put   data/…  (1.4 MB)` / `skip …`) and writes nothing.
  - `web/vite.config.ts`: `defineConfig(({ command }) => ({ base: …, publicDir: command === "serve" ? ".devdata" : "public" }))`. Dev serves staged data; builds never copy data into `dist`.
  - `Makefile`:
    - `web-data: ## copy the newest build's site data into web/.devdata for make web-dev` → `$(PY) pipeline.publish galaxy --data-only --to-dir web/.devdata`.
    - `stage: ## mirror the Hostinger tree into data/stage/public_html` → `$(PY) pipeline.publish all --to-dir data/stage/public_html`.
- [x] **Step 5: Run** `uv run pytest -q && uv run ruff check .`. Expected: all pass. Then run `make build && make web-data` and check that `web/.devdata/manifest.json` names the new version.
- [x] **Step 6: Commit and push** (`feat(publish): site layout, local staging and licence attribution`).

### Task 2: Web data loading

**Files:**
- Create: `web/src/config.ts`, `web/src/data.ts`, `web/test/data.test.ts`
- Modify: `web/package.json` (add `happy-dom`; scripts `typecheck: tsc --noEmit`)
- Modify: `web/tsconfig.json` (include `test`)
- Modify: `.github/workflows/test.yml` (new `Web` step: `npm ci`, `npm test`, `npm run build`)

**Interfaces:**
- Produces (`data.ts`):
  - **Types:**
    - `Manifest {version; built_at; creators; clusters; attribution: {source; source_url; license; license_url?; note}}`.
    - `ClusterInfo {key; name; colour; size; leader_id: string | null; cx2; cy2; cx3; cy3; cz3: number | null}`.
    - `Detail {bio; source_url; youtube_url: string | null; thumbnail: string | null; missing_from_wiki_since?: string}`.
    - `Galaxy {version; ids: string[]; titles: string[]; cluster: Uint16Array; pos2: Float32Array /*n*2*/; pos3: Float32Array /*n*3*/; clusters: ClusterInfo[]; index: Map<string, number>}`.
  - **Paths and errors:**
    - `paths(base: string, version: string) -> {manifest, nodes, clusters, neighbors, details(key: string)}`. Everything except `manifest` is under `${base}data/${version}/`.
    - `class DataError extends Error`.
  - **Loaders:**
    - `loadManifest(fetchFn: typeof fetch, base: string): Promise<Manifest>`: requests with `{cache: "no-store"}`.
    - `toGalaxy(version, nodes, clusters): Galaxy`.
    - `loadGalaxy(fetchFn, base, manifest): Promise<Galaxy>`.
    - `createLoader(fetchFn, base, version) -> {neighbors(): Promise<Record<string, string[]>>; details(key): Promise<Record<string, Detail>>}`. Both are memoised; a rejected promise is dropped from the cache, so a retry refetches.
  - `config.ts`: `BASE = import.meta.env.BASE_URL`.

- [x] **Step 1: Write the failing tests** in `web/test/data.test.ts`, using a fake `fetchFn` that serves an in-memory map of URL → JSON and records calls:
  - `paths("/galaxy/", "v1").nodes === "/galaxy/data/v1/nodes.json"`, and `.manifest === "/galaxy/manifest.json"`.
  - `loadManifest` passes `cache: "no-store"`. A 404 rejects with `DataError` whose message contains `manifest.json`.
  - `toGalaxy` with 3 nodes: `pos2` equals `[x0, y0, x1, y1, x2, y2]` as a `Float32Array`; `index.get(id1) === 1`; `cluster` is a `Uint16Array`.
  - `toGalaxy` throws `DataError` when a column has a different length, or when a `cluster` value is ≥ `clusters.length`.
  - `createLoader(...).details("c001")` called twice → one fetch. After a failed first call, a second call fetches again.
- [x] **Step 2: Run** `cd web && npm install -D happy-dom && npm test`. Expected: FAIL.
- [x] **Step 3: Implement `web/src/data.ts` and `web/src/config.ts`** to the interfaces above.
- [x] **Step 4: Run** `npm test && npm run typecheck`. Expected: PASS.
- [x] **Step 5: Add the CI web step and commit and push** (`feat(web): data loading`).

### Task 3: The map

**Files:**
- Create: `web/src/colour.ts`, `web/src/view.ts`, `web/src/map.ts`
- Create: `web/test/colour.test.ts`, `web/test/view.test.ts`
- Modify: `web/package.json` (`@deck.gl/core`, `@deck.gl/layers`)
- Modify: `web/src/main.ts`, `web/index.html`
- Create: `web/src/style.css`

**Interfaces:**
- Consumes: `Galaxy` (Task 2).
- Produces:
  - **`colour.ts`:**
    - `hexToRgb(hex: string): [number, number, number]`.
    - `DIM_ALPHA = 40`.
    - `fillColours(g: Galaxy, focus: Focus | null, out?: Uint8Array): Uint8Array`, where `Focus = {cluster: number; keep?: number[]}`. Returns n×4 RGBA. With no focus, every alpha is 255. With a focus, members of `cluster` and indices in `keep` get 255 and everything else gets `DIM_ALPHA`.
  - **`view.ts`:**
    - `bounds(pos: Float32Array, dims: 2 | 3): {min: number[]; max: number[]}`.
    - `fitView(b, width, height, pad = 0.9): {target: [number, number, number]; zoom: number}`, where zoom = `log2(pad · min(width / spanX, height / spanY))` and target is the box centre (z = 0 for 2D).
  - **`map.ts`:**
    - `createMap(parent: HTMLElement, g: Galaxy, h: {onHover(i: number | null, x: number, y: number): void; onClick(i: number | null): void}) -> GalaxyMap`.
    - `GalaxyMap` methods: `setMode("2d" | "3d")`, `setFocus(f: Focus | null)`, `setLinks(from: number | null, to: number[])`, `flyTo(i: number)`, `flyToPoint(xy: number[])`, `setPerformance(on: boolean)`, `destroy()`.

- [x] **Step 1: Write the failing tests:**
  - `hexToRgb("#f10080")` → `[241, 0, 128]`.
  - `fillColours`:
    - no focus → all alpha 255, RGB from each node's cluster colour;
    - focus `{cluster: 1}` → members 255, others 40;
    - `keep: [0]` with node 0 in cluster 0 → node 0 is 255;
    - passing `out` reuses that buffer (`===`).
  - `fitView`: bounds (0,0)–(10,10) in 1000×1000 → zoom `log2(90)`, target `[5, 5, 0]`. A 3D box gives a z-centred target.
- [x] **Step 2: Run** `npm test`. Expected: FAIL.
- [x] **Step 3: Implement `colour.ts` and `view.ts`.** Run `npm test`. Expected: PASS.
- [x] **Step 4: Implement `map.ts`** with deck.gl `Deck`:
  - **Points:** one `ScatterplotLayer` over **binary attributes**: `data: {length: n, attributes: {getPosition: {value: pos2|pos3, size: 2|3}, getFillColor: {value: colours, size: 4, normalized: true}}}`.
  - **Sizes:** `radiusUnits: "pixels"`, radius 2.5 (1.5 in performance mode). `pickable: true`, `autoHighlight: true`.
  - **Views:** 2D uses `OrthographicView` (default); 3D uses `OrbitView`. Initial views come from `fitView`.
  - **Neighbour lines:** a `LineLayer` drawn only when `setLinks` has a source and performance mode is off.
  - **Transitions:** `flyTo` uses a 600 ms view-state transition, or none when `matchMedia("(prefers-reduced-motion: reduce)")` matches or performance mode is on.
  - **Performance mode:** also sets `useDevicePixels: false`.
  - `main.ts`: load manifest → galaxy, mount the map, and show a hover tooltip (title + cluster name, positioned at x/y). Show a full-page message on `DataError` ("The map couldn't load. Try refreshing.").
- [x] **Step 5: Check by eye.** Run `make web-data && make web-dev` and open `http://localhost:5173/galaxy/` (use the browser tool if available, otherwise ask the owner). Expected:
  - all ~20.8K coloured points;
  - smooth pan and zoom;
  - 2D↔3D toggle works;
  - hover shows the title.

  Record JS bundle size from `npm run build` (raw/gzip) in NOTES.
- [x] **Step 6: Commit and push** (`feat(web): deck.gl map with 2D/3D`).

### Task 4: Search, legend and shareable links

**Files:**
- Create: `web/src/search.ts`, `web/src/hash.ts`, `web/src/ui/search-box.ts`, `web/src/ui/legend.ts`
- Create: `web/test/search.test.ts`, `web/test/hash.test.ts`, `web/test/legend.test.ts`
- Modify: `web/src/main.ts`, `web/src/style.css`

**Interfaces:**
- Consumes: `Galaxy`, `GalaxyMap` (Tasks 2–3).
- Produces:
  - **`search.ts`:**
    - `fold(s: string): string`: NFKD, strip combining marks, lowercase, runs of non-alphanumerics → one space, trimmed.
    - `makeSearch(titles: string[]) -> (query: string, limit?: number) => number[]`. Folded titles are precomputed once. Ranking: exact match → prefix → word-prefix → substring; ties by shorter title, then index. Default `limit = 10`. An empty or whitespace query gives `[]`.
  - **`hash.ts`:** `parseHash(h: string): {creator?: string; cluster?: string}` and `formatHash(s): string`. Formats are `#/creator/<id>` and `#/cluster/<key>`; anything else → `{}`.
  - **UI:**
    - `mountSearchBox(el, g, search, onPick(i))`: an ARIA combobox. Arrow keys move, Enter picks, Escape closes. Each option shows title + cluster name.
    - `renderLegend(el, clusters, titleOf(id) -> string | undefined, onPick(c: number))`: rows sorted by size descending, each a `<button>` with a colour swatch, name, size and leader title, plus a filter input.

- [x] **Step 1: Write the failing tests:**
  - **search:**
    - `fold("Pokémon  Go!") === "pokemon go"`.
    - `same-title creators both match`: titles `["Target", "TARGET", "Target3DGaming"]`, query "target" → first two results are `{0, 1}` in any order, then 2.
    - Prefix beats substring: query "mark" over `["LS Mark", "Markiplier"]` → Markiplier first.
    - `limit` is respected. `""` → `[]`.
    - A 20,000-title synthetic list answers a query in under 50 ms.
  - **hash:**
    - `parseHash("#/creator/fandom_449281")` → `{creator: "fandom_449281"}`.
    - `#/cluster/c071` → `{cluster: "c071"}`.
    - `#/creator/` and `#foo` → `{}`.
    - The `formatHash` round-trip holds.
  - **legend** (happy-dom):
    - 3 clusters render as 3 buttons in size order.
    - Typing "mine" in the filter leaves only names containing "mine" (case-insensitive).
    - Clicking a row calls `onPick` with that cluster's **position in `clusters`**, not its rank in the sorted list.
- [x] **Step 2: Run** `npm test`. Expected: FAIL.
- [x] **Step 3: Implement** the modules and wire them in `main.ts`:
  - **Picking a creator:** `flyTo`, `setFocus({cluster, keep: neighbours})`, `setLinks`, open the panel (Task 5), and set `#/creator/<id>`.
  - **Picking a cluster:** `flyToPoint` to its `cx2/cy2` (or the 3D centre in 3D mode), `setFocus({cluster})`, and set `#/cluster/<key>`.
  - **Clearing:** a click on empty map or Escape clears focus and the hash.
  - **On load and on `hashchange`:** apply the hash. Unknown ids or keys are ignored silently.
  - **Neighbours:** load in the background after first paint (`requestIdleCallback`, falling back to `setTimeout(…, 500)`).
- [x] **Step 4: Run** `npm test && npm run typecheck`. Expected: PASS. Then check by eye that searching "target" shows both, each with its cluster.
- [x] **Step 5: Commit and push** (`feat(web): search, legend and shareable links`).

### Task 5: Detail panel, footer, toggles and layout

**Files:**
- Create: `web/src/ui/detail.ts`, `web/src/ui/footer.ts`, `web/src/ui/toggles.ts`
- Create: `web/test/detail.test.ts`, `web/test/footer.test.ts`
- Modify: `web/src/main.ts`, `web/src/style.css`, `web/index.html`

**Interfaces:**
- Consumes: `Detail`, `Manifest`, `createLoader` (Task 2); selection wiring (Task 4).
- Produces:
  - `renderDetail(el, v: DetailView)`, where `DetailView = {title; cluster: {name; colour}; detail: Detail | null | "loading" | "error"; neighbours: {id; title}[] | null; onSelect(id); onRetry(); onClose()}`.
  - `renderFooter(el, m: Manifest)`.
  - `mountToggles(el, s: {mode: "2d" | "3d"; performance: boolean}, onChange)`. Settings persist in `localStorage` key `galaxy.settings`; every read and write is wrapped in try/catch.

- [x] **Step 1: Write the failing tests** (happy-dom):
  - **Source link:** text "Read on the YouTube Wiki", `href = source_url`, `target="_blank"`, `rel="noopener noreferrer"`.
  - **YouTube link:** present for a non-null `youtube_url`, absent for `null`.
  - **Thumbnail:**
    - The `img` has `loading="lazy"`, `referrerpolicy="no-referrer"` and `alt=""`.
    - Dispatching `error` on it removes the `img` and adds class `no-thumb` to the card.
    - A `null` thumbnail renders no `img`.
  - **Untrusted bio:** `bio: "<img src=x onerror=alert(1)>"` → the panel has no `img` from the bio, and the text appears literally.
  - **Vanished page:** `missing_from_wiki_since: "2026-12-01"` → the text "No longer on the wiki (since 2026-12-01)".
  - **Load states:**
    - `detail: "error"` → "Details couldn't load" plus a Retry button calling `onRetry`. Title, cluster and neighbours still render.
    - `"loading"` → a loading line.
  - **Neighbours:** neighbour buttons call `onSelect(id)`. `neighbours: null` → "Loading similar creators…".
  - **Footer:**
    - contains "YouTube Wiki (Fandom)" linking `source_url`, and the licence name linking `license_url`;
    - contains "Last updated 18 Nov 2026" for `built_at: "2026-11-18T17:18:50+00:00"` (format `d MMM yyyy`, `en-GB`, UTC);
    - shows the creator count.
- [x] **Step 2: Run** `npm test`. Expected: FAIL.
- [x] **Step 3: Implement** the modules and the page layout:
  - **Layout:**
    - Header: title, search box, toggles.
    - The map fills the viewport.
    - The legend is a collapsible side panel (a bottom sheet under 700 px width).
    - The detail panel is on the right (a bottom sheet on phones).
    - The footer is always reachable.
    - `<aside id="chat-slot" hidden>` is reserved for Plan 4.
  - **Detail data:** comes from `loader.details(cluster key)`. Retry calls it again.
  - **Toggles:**
    - 2D/3D calls `map.setMode`.
    - Performance mode calls `map.setPerformance`, which also stops the neighbour lines.
- [x] **Step 4: Run** `npm test && npm run typecheck && npm run build`. Expected: PASS. Then check by eye at 360 px and desktop widths:
  - no horizontal scroll;
  - Tab reaches every control with a visible focus ring;
  - the panel opens and closes;
  - a broken thumbnail falls back to the text card.
- [x] **Step 5: Commit and push** (`feat(web): detail panel, attribution footer, toggles`).

### Task 6: Home page, cache rules and preview

**Files:**
- Create: `web/home/index.html`, `web/home/home.css`
- Create: `web/public/.htaccess`
- Create: `tests/test_site_files.py`
- Modify: `Makefile` (`web-build` sets `SITE_BASE_PATH`; new `preview`)
- Modify: `docs/NOTES.md`

**Interfaces:**
- Consumes: `home_files`, `galaxy_files`, `stage` (Task 1).
- Produces:
  - `web/public/.htaccess` (copied into `dist` by Vite).
  - `make preview`: `make stage`, then `python3 -m http.server 8080 --bind 0.0.0.0 -d data/stage/public_html`. It prints the LAN URL for a phone check.

- [x] **Step 1: Verify** in Hostinger and LiteSpeed docs that `.htaccess` `mod_headers` / `mod_expires` / `mod_deflate` directives work on Hostinger shared hosting. Record the URL and date in NOTES. If they don't, keep the file and note what's ignored.
- [x] **Step 2: Write the failing tests** in `tests/test_site_files.py`:
  - **`test_htaccess_cache_rules`:**
    - `web/public/.htaccess` gives `.js|.css|.json` `max-age=31536000, immutable`;
    - a **later** `<FilesMatch "^(index\.html|manifest\.json)$">` section sets `no-cache` (order matters, so assert the index of one section is greater than the other);
    - gzip/deflate is enabled for json/js/css/html.
  - **`test_home_links_galaxy`:** `web/home/index.html` contains `href="/galaxy/"`, links `home.css`, has a viewport meta, and references no remote scripts.
  - **`test_home_plan_has_no_htaccess_or_dirs`:** `home_files(web/home)` paths contain no `/` and no `.htaccess`.
- [x] **Step 3: Run** `uv run pytest tests/test_site_files.py -q`. Expected: FAIL.
- [x] **Step 4: Implement the home page** and the `.htaccess`.
  - **Home page** (static, same dark palette as the galaxy):
    - heading "SpookyPharaoh";
    - the line "Silly things I build for fun.";
    - one card "YouTube Galaxy: explore 20,000+ YouTube creators on a map", linking to `/galaxy/`;
    - a footer.

    The owner may change the copy at the checkpoint.
  - **Makefile:** `web-build: ## build the galaxy site into web/dist` runs `cd web && SITE_BASE_PATH=$${SITE_BASE_PATH:-/galaxy/} npm run build`.
- [x] **Step 5: Run** `uv run pytest -q && make web-build && make preview`. Check by eye:
  - `http://localhost:8080/` shows the home page;
  - its card opens `/galaxy/`;
  - the map loads from the staged tree.
- [x] **Step 6: Commit and push** (`feat(site): home page, cache rules and local preview`).

### Task 7: SFTP publish, preflight, prune and rollback

**Files:**
- Modify: `pipeline/publish.py`, `tests/test_publish.py`
- Modify: `Makefile` (`publish-dry`, `publish`, `rollback`)
- Create: `docs/DEPLOY.md`
- Modify: `README.md` (commands)

**Interfaces:**
- Consumes: Task 1's `Settings` fields, `Remote`, `plan_uploads`, `execute`, `galaxy_files`, `home_files`.
- Produces:
  - **`SftpRemote(settings)`:**
    - is a context manager;
    - imports paramiko lazily;
    - uses `load_system_host_keys()` plus `RejectPolicy`;
    - authenticates with the key if `key_path` is set, otherwise the password;
    - implements atomic `put` with `posix_rename`, falling back to `remove` + `rename` when the server lacks the extension.
  - **`preflight(settings, build_dir, dist_dir, remote) -> list[str]`** returns error strings; an empty list means OK. It checks that:
    - `site_base_path.strip("/") == basename(hostinger_remote_dir)`;
    - `dist/index.html` references `{site_base_path}assets/`;
    - `hostinger_home_dir == dirname(hostinger_remote_dir)`;
    - every non-`worker/` file listed in the build manifest's `files` exists.

    It also returns warnings, prefixed `"warning: "`, when the remote home dir contains `default.php` or `index.php`.
  - **`prune_plan(remote, galaxy_dir, live_version, keep=3) -> list[Action]`:** `rmtree` actions for `data/<v>` dirs beyond the `keep` newest (by name), never `live_version`.
  - **`live_version(remote, galaxy_dir) -> str | None`:** reads the remote `manifest.json`.
  - **`verify(url: str, version: str, fetch=urllib) -> bool`:** GETs `{site_origin}{site_base_path}manifest.json?t=<unix>` with User-Agent `galaxy-publish/1.0`.
  - **CLI additions:**
    - without `--to-dir`, the target is Hostinger;
    - `rollback VERSION`;
    - galaxy publish sequence: preflight → plan uploads → execute → verify → prune.

- [x] **Step 1: Write the failing tests** (all with `LocalRemote` or fakes; no paramiko import):
  - `test_preflight_base_path_mismatch`: `SITE_BASE_PATH=/map/` with `public_html/galaxy` → one error mentioning both.
  - `test_preflight_dist_built_with_wrong_base`: `dist/index.html` referencing `/assets/` → error.
  - `test_preflight_warns_on_placeholder_index`: the remote home dir holds `default.php` → a `warning:` entry.
  - `test_home_plan_touches_only_own_files`: a remote with `galaxy/manifest.json`, `music/x.html` and `.htaccess` before a home publish → afterwards those three are byte-identical, and the only changed paths are `index.html` and `home.css`.
  - `test_prune_keeps_three_and_live`: versions `v1`…`v5` with the live manifest pointing at `v1` → prune removes `v2` only.
  - `test_rollback_requires_remote_version`: rolling back to a version missing remotely → exits non-zero and uploads nothing. A present version → only `manifest.json` changes, and its `version` equals the target.
  - `test_dry_run_never_prints_secrets`: settings with password `"s3cret-pw"` → captured stdout and stderr do not contain it.
  - `test_verify`: a fake fetch returning `{"version": "v2"}` → `verify(..., "v2")` is True and `"v1"` is False. The request URL has a `t=` query and the generic User-Agent.
- [x] **Step 2: Run** `uv run pytest tests/test_publish.py -q`. Expected: FAIL.
- [x] **Step 3: Implement** the interfaces above.
  - **Errors:** a preflight error exits 1 before connecting for uploads (listing the remote dir for warnings is allowed). Warnings print and continue.
  - **Makefile:**
    - `publish-dry: ## show exactly what a publish would upload (connects read-only)` runs `$(PY) pipeline.publish all --dry-run`.
    - `publish: ## upload home + galaxy to Hostinger (manifest last), verify, prune` runs `$(PY) pipeline.publish all`.
    - `rollback: ## point the live site at an older data version: make rollback VERSION=…` runs `$(PY) pipeline.publish rollback $(VERSION)`.
- [x] **Step 4: Run** `uv run pytest -q && uv run ruff check .`. Expected: PASS.
- [x] **Step 5: Write `docs/DEPLOY.md` (Hostinger part only; Cloudflare comes in Plan 4):**
  - **Credentials:** where to find SFTP host, port and user in hPanel (verify against Hostinger's help page and record the URL), and enabling SSH/SFTP access.
  - **Host key:** accepting it once with `ssh -p <port> <user>@<host>`.
  - **`.env` values.**
  - **Before publishing:** `make build web-build stage preview` for the local check, then `make publish-dry`.
  - **Publishing:** `make publish`, and how to verify (open the site, check `manifest.json` version).
  - **Rollback:** `make rollback VERSION=…`.
  - **Placeholder page:** removing Hostinger's default page if preflight warns about it (the owner does this by hand in hPanel's file manager).
  - **Files to delete:** this lists local leftovers in `docs/TO_DELETE.md`.
- [x] **Step 6: Commit and push** (`feat(publish): SFTP upload, preflight, prune, rollback, DEPLOY.md`).

### Task 8: 🛑 Checkpoint 3a — review and first publish (map only)

- [x] **Step 1: Fresh build.** Run `make pipeline FORCE=1 && make web-build && make stage`. Record the version, site upload size and JS bundle size.
- [ ] **Step 2: Owner reviews locally** with `make preview`, on a laptop and on a phone over the LAN URL. Checklist to send:
  - map colours and readability;
  - 2D/3D;
  - search ("target", "markiplier");
  - legend;
  - detail panel and thumbnails;
  - shareable link;
  - performance mode;
  - footer attribution;
  - home page copy.

  Fix what they flag (one commit per fix) before going on.
- [ ] **Step 3: Owner fills in `.env`** with the Hostinger values and accepts the host key, following `docs/DEPLOY.md`. Claude cannot do this step.
- [ ] **Step 4: Run** `make publish-dry`. Show the owner the full action list and any preflight warnings (e.g. Hostinger's `default.php`).
- [ ] **Step 5: Real upload only on the owner's explicit "go".**
  - Run `make publish`.
  - Confirm that `https://spookypharaoh.com/` and `https://spookypharaoh.com/galaxy/` load, and that `manifest.json` reports the new version.
  - Record the result in NOTES.
- [ ] **Step 6: Report** in plain language:
  - what is live;
  - sizes and first-load size;
  - anything that differed from this plan;
  - local files now safe to delete (added to `docs/TO_DELETE.md`);
  - next steps: issue #5 before going public (per the owner), then Plan 4 (Worker search + chat widget).

  Tick the steps in this plan, update NOTES and memory, then commit and push.
