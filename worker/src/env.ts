// Bindings and vars available to the Worker.
export interface Env {
  ASSETS?: Fetcher; // tests only (wrangler.test.jsonc); production bundles the index (src/main.ts)
  AI: Ai; // Workers AI (query embeddings)
  ALLOWED_ORIGINS?: string; // comma-separated CORS allow-list (wrangler.jsonc vars, worker/.dev.vars)
  PER_IP?: RateLimit; // rate limit per client IP (wrangler.jsonc ratelimits); absent → no limit
  GLOBAL?: RateLimit; // one shared key for all clients (per Cloudflare location)
}
