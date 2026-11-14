// Phase 1 spike Worker: loads the index from static assets once per isolate and runs two-stage search.
// Production routes (/api/chat with search + ask, CORS, rate limits) are built on this in Phase 4.

import { parseIndex, readMeta, type LoadedIndex } from "./indexFormat";
import { embedQuery } from "./embed";
import { bruteForceSearch, DEFAULT_PARAMS, l2normalize, twoStageSearch } from "./search";

interface Env {
  ASSETS: Fetcher;
  AI: Ai;
  SPIKE_ENDPOINTS?: string;
}

interface IndexState {
  idx: LoadedIndex;
  version: string;
}

// Module-level cache: only a cold isolate pays for fetching and wrapping the index.
let indexPromise: Promise<IndexState> | null = null;
let loadedAt = 0;

async function asset(env: Env, path: string): Promise<Response> {
  const res = await env.ASSETS.fetch(new Request(`https://assets.local/${path}`));
  if (!res.ok) throw new Error(`asset ${path}: HTTP ${res.status}`);
  return res;
}

function loadIndex(env: Env): Promise<IndexState> {
  if (!indexPromise) {
    indexPromise = (async () => {
      const [ib, cb, mb, man] = await Promise.all([
        asset(env, "index.bin").then((r) => r.arrayBuffer()),
        asset(env, "centroids.bin").then((r) => r.arrayBuffer()),
        asset(env, "meta.bin").then((r) => r.arrayBuffer()),
        asset(env, "index_manifest.json").then((r) => r.json<{ version: string }>()),
      ]);
      loadedAt = Date.now();
      return { idx: parseIndex(ib, cb, mb), version: man.version };
    })().catch((e) => {
      indexPromise = null; // retry on the next request
      throw e;
    });
  }
  return indexPromise;
}

/** Deterministic pseudo-random unit query (mulberry32) so CPU tests need no AI call. */
function randomQuery(seed: number, dim: number): Float32Array {
  let t = seed >>> 0;
  const rnd = () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296 - 0.5;
  };
  return l2normalize(Array.from({ length: dim }, rnd));
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const cold = indexPromise === null;

    if (url.pathname === "/health") {
      const { idx, version } = await loadIndex(env);
      return json({ status: "ok", version, n: idx.n, cold, loadedAt });
    }

    if (env.SPIKE_ENDPOINTS === "1" && url.pathname === "/spike/search") {
      // Pure search CPU, no AI call: ?seed=N&mode=two|brute
      const { idx } = await loadIndex(env);
      const q = randomQuery(Number(url.searchParams.get("seed") ?? 1), idx.dim);
      const hits =
        url.searchParams.get("mode") === "brute" ? bruteForceSearch(idx, q, 10) : twoStageSearch(idx, q);
      return json({ cold, top: hits.slice(0, 3) });
    }

    if (url.pathname === "/api/chat" && req.method === "POST") {
      const body = (await req.json().catch(() => null)) as { question?: string } | null;
      const question = body?.question?.trim();
      if (!question || question.length > 300) return json({ error: "question must be 1-300 chars" }, 400);
      const [{ idx }, q] = await Promise.all([loadIndex(env), embedQuery(env.AI, question)]);
      const results = twoStageSearch(idx, q, DEFAULT_PARAMS).map(({ row, score }) => {
        const m = readMeta(idx, row);
        return { id: m.id, title: m.title, cluster: m.cluster, score, url: m.url, snippet: m.bio };
      });
      return json({ mode: "search", cold, results });
    }

    return json({ error: "not found" }, 404);
  },
} satisfies ExportedHandler<Env>;
