import type { Env } from "./env";
import { readRecord } from "./format";
import { getIndex, type LoadedIndex } from "./index_loader";
import { twoStageSearchWithProbe } from "./search";

const EMBED_MODEL = "@cf/baai/bge-small-en-v1.5";
const QUERY_PREFIX = "Represent this sentence for searching relevant passages: ";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

// Deterministic PRNG so a seed always produces the same synthetic query.
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Returns the top-10 records plus how many clusters and candidates the search looked at.
function searchAndDescribe(loaded: LoadedIndex, query: Float32Array) {
  const { index, centroids, meta } = loaded;
  const { hits, probe } = twoStageSearchWithProbe(query, centroids, index, { k: 10 });
  return {
    hits: hits.map((h) => {
      const r = readRecord(meta, h.row);
      return { id: r.id, title: r.title, score: h.score };
    }),
    probed: probe.clusters.length,
    candidates: probe.candidates,
  };
}

async function spikeSearch(url: URL, env: Env): Promise<Response> {
  const raw = url.searchParams.get("seed");
  if (!raw || !/^\d+$/.test(raw)) return json({ error: "bad_request" }, 400);
  const loaded = await getIndex(env);
  const rand = mulberry32(Number(raw));
  const query = Float32Array.from({ length: loaded.index.dim }, () => rand() * 2 - 1);
  return json(searchAndDescribe(loaded, query));
}

async function spikeEmbedSearch(url: URL, env: Env): Promise<Response> {
  const text = (url.searchParams.get("q") ?? "").trim();
  if (!text || text.length > 300) return json({ error: "bad_request" }, 400);
  const [loaded, embedded] = await Promise.all([
    getIndex(env),
    env.AI.run(EMBED_MODEL, { text: [QUERY_PREFIX + text], pooling: "cls" }),
  ]);
  const data = (embedded as { data?: number[][] }).data;
  if (!data?.[0]) return json({ error: "embed_failed" }, 502);
  return json(searchAndDescribe(loaded, Float32Array.from(data[0])));
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (req.method === "GET") {
      if (url.pathname === "/health") {
        let version: string | null = null;
        try {
          version = (await getIndex(env)).manifest.version;
        } catch {
          version = null;
        }
        return json({ ok: true, index_version: version });
      }
      // Spike-only routes; removed in Plan 4.
      if (url.pathname === "/spike/search") return spikeSearch(url, env);
      if (url.pathname === "/spike/embed-search") return spikeEmbedSearch(url, env);
    }
    return json({ error: "not_found" }, 404);
  },
} satisfies ExportedHandler<Env>;
