// Bindings and vars available to the Worker.
export interface Env {
  ASSETS?: Fetcher; // tests only (wrangler.test.jsonc); production bundles the index (src/main.ts)
  AI: Ai; // Workers AI (query embeddings)
}
