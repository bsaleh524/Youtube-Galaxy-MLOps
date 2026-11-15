import type { Env } from "./env";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (req.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, index_version: env.INDEX_VERSION ?? null });
    }
    return json({ error: "not_found" }, 404);
  },
} satisfies ExportedHandler<Env>;
