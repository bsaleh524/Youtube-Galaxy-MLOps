// HTTP helpers for the chat API: JSON responses, the CORS allow-list, and request validation.

export const MAX_QUESTION = 300;

export type ChatMode = "search" | "ask";
export type ParsedChat =
  | { ok: true; question: string; mode: ChatMode }
  | { ok: false; error: "empty" | "too_long" | "bad_mode" };

export function json(body: unknown, status = 200, headers: HeadersInit = {}): Response {
  const h = new Headers(headers);
  h.set("content-type", "application/json; charset=utf-8");
  return new Response(JSON.stringify(body), { status, headers: h });
}

/** "a, b,," → {"a", "b"}. Configured in wrangler.jsonc vars (and worker/.dev.vars locally). */
export function parseOrigins(csv: string | undefined): Set<string> {
  return new Set(
    (csv ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
  );
}

export function corsHeaders(origin: string): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

/** The request's Origin if it is on the allow-list, else null (a missing Origin is not allowed). */
export function allowedOrigin(req: Request, allowed: Set<string>): string | null {
  const origin = req.headers.get("Origin");
  return origin && allowed.has(origin) ? origin : null;
}

export function parseChatRequest(body: unknown): ParsedChat {
  const b = (body && typeof body === "object" ? body : {}) as { question?: unknown; mode?: unknown };
  const question = typeof b.question === "string" ? b.question.trim() : "";
  if (!question) return { ok: false, error: "empty" };
  if (question.length > MAX_QUESTION) return { ok: false, error: "too_long" };
  const mode = b.mode ?? "search";
  if (mode !== "search" && mode !== "ask") return { ok: false, error: "bad_mode" };
  return { ok: true, question, mode };
}
