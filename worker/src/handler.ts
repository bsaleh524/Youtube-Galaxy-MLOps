// Routes: GET /health, POST|OPTIONS /api/chat. The response contract is in
// docs/superpowers/plans/2026-11-24-plan-4-chat-search.md (Global Constraints).
import { AiQuotaError, aiEmbed, type Embed, searchChat } from "./chat";
import type { Env } from "./env";
import { allowedOrigin, corsHeaders, json, parseChatRequest, parseOrigins } from "./http";
import type { LoadedIndex } from "./index_loader";
import { WindowLimiter } from "./limiter";

type IndexSource = (env: Env) => Promise<LoadedIndex>;

export interface HandlerDeps {
  embed?: (env: Env) => Embed; // tests inject a fake; production uses Workers AI
}

async function underLimit(limiter: RateLimit | undefined, key: string): Promise<boolean> {
  if (!limiter) return true;
  try {
    return (await limiter.limit({ key })).success;
  } catch (err) {
    console.error("rate limiter failed; allowing", err instanceof Error ? err.message : err);
    return true;
  }
}

async function chat(
  req: Request,
  env: Env,
  getIndex: IndexSource,
  makeEmbed: (env: Env) => Embed,
  local: WindowLimiter,
) {
  const origin = allowedOrigin(req, parseOrigins(env.ALLOWED_ORIGINS));
  if (req.method !== "POST" && req.method !== "OPTIONS") {
    return json({ status: "method_not_allowed" }, 405, { Allow: "POST, OPTIONS" });
  }
  if (!origin) return json({ status: "forbidden" }, 403);
  const cors = corsHeaders(origin);
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

  const ip = req.headers.get("CF-Connecting-IP") ?? "unknown";
  if (!(await underLimit(env.PER_IP, ip)) || !(await underLimit(env.GLOBAL, "all")) || !local.allow(ip)) {
    return json({ status: "rate_limited", retry_after: 60 }, 429, { ...cors, "Retry-After": "60" });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return json({ status: "bad_request", error: "bad_json" }, 400, cors);
  }
  const parsed = parseChatRequest(body);
  if (!parsed.ok) return json({ status: "bad_request", error: parsed.error }, 400, cors);
  if (parsed.mode === "ask") return json({ status: "unavailable" }, 501, cors);

  const forceTopic = (body as { force_topic?: unknown }).force_topic === true;
  try {
    const out = await searchChat(await getIndex(env), parsed.question, makeEmbed(env), forceTopic);
    return json(out, 200, cors);
  } catch (err) {
    // Log the reason only, never the question.
    console.error("chat search failed", err instanceof Error ? err.message : err);
    if (err instanceof AiQuotaError) return json({ status: "resting" }, 503, cors);
    return json({ status: "error" }, 502, cors);
  }
}

// The routes are the same in every build; only where the index comes from differs
// (bundled data modules in production, static assets in tests).
export function createHandler(getIndex: IndexSource, deps: HandlerDeps = {}): ExportedHandler<Env> {
  const makeEmbed = deps.embed ?? aiEmbed;
  const local = new WindowLimiter(10, 60_000); // same as PER_IP in wrangler.jsonc
  return {
    async fetch(req: Request, env: Env): Promise<Response> {
      const url = new URL(req.url);
      if (url.pathname === "/api/chat") return chat(req, env, getIndex, makeEmbed, local);
      if (req.method === "GET" && url.pathname === "/health") {
        let version: string | null = null;
        try {
          version = (await getIndex(env)).manifest.version;
        } catch {
          version = null;
        }
        return json({ ok: true, index_version: version });
      }
      return json({ error: "not_found" }, 404);
    },
  };
}
