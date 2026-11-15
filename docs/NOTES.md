# Notes: verified facts and decisions

Every external fact the build relies on is listed here with its source and the date it was checked. Free-tier numbers and model IDs change, so re-check anything older than a few months before relying on it.

## Verified external facts

| Fact | Value | Source | Checked |
|---|---|---|---|
| Workers test setup | `vitest@^4.1` + `@cloudflare/vitest-plugin` (installed 1.8.2) via `cloudflareTest()` in `vitest.config.ts`; tests import `exports`/`env` from `cloudflare:workers`. Wrangler 4.162.0. npm needs `install-scripts approve esbuild workerd` (recorded in `worker/package.json` `allowScripts`). | https://developers.cloudflare.com/workers/testing/vitest-integration/write-your-first-test/ | 2026-11-15 |

## Decisions

- 2026-11-15 — MLflow runs on port **5001**, because macOS AirPlay Receiver uses 5000.
