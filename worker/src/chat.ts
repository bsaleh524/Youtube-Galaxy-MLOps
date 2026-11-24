// Search mode of POST /api/chat: name lookup first ("channels like X" → X's own vector), otherwise
// embed the question with Workers AI. Both then run the same two-stage search.
import type { Env } from "./env";
import { readRecord } from "./format";
import type { LoadedIndex } from "./index_loader";
import { creatorVector, findNamedCreator } from "./names";
import { normalize, twoStageSearch } from "./search";

export const EMBED_MODEL = "@cf/baai/bge-small-en-v1.5";
export const QUERY_PREFIX = "Represent this sentence for searching relevant passages: ";
export const RESULTS = 8;

export type Embed = (text: string) => Promise<Float32Array>;

/** Workers AI refused for quota/limit reasons: the chat is "resting" until the quota resets. */
export class AiQuotaError extends Error {}

const QUOTA = /quota|neuron|allocation|rate.?limit|429|3036|4006/i;

export function aiEmbed(env: Env): Embed {
  return async (text) => {
    let out: unknown;
    try {
      out = await env.AI.run(EMBED_MODEL, { text: [QUERY_PREFIX + text], pooling: "cls" });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (QUOTA.test(msg)) throw new AiQuotaError(msg);
      throw err;
    }
    const data = (out as { data?: number[][] } | null)?.data;
    if (!data?.[0]) throw new Error("embedding returned no vector");
    return Float32Array.from(data[0]);
  };
}

export interface ChatHit {
  id: string;
  title: string;
  cluster: unknown;
  score: number;
  url: string;
  snippet: string;
}

export interface ChatOk {
  status: "ok";
  mode: "search";
  kind: "topic" | "similar";
  about: { id: string; title: string } | null;
  results: ChatHit[];
  index_version: string;
}

function hit(loaded: LoadedIndex, row: number, score: number): ChatHit {
  const r = readRecord(loaded.meta, row);
  return { id: r.id, title: r.title, cluster: r.cluster, score: Math.round(score * 1e4) / 1e4, url: r.url, snippet: r.snippet };
}

export async function searchChat(
  loaded: LoadedIndex,
  question: string,
  embed: Embed,
  forceTopic = false,
): Promise<ChatOk> {
  const { centroids, index, manifest } = loaded;
  const named = forceTopic ? null : findNamedCreator(question, loaded.names);
  if (named !== null) {
    const about = readRecord(loaded.meta, named);
    const hits = twoStageSearch(creatorVector(index, named), centroids, index, { k: RESULTS + 1 })
      .filter((h) => h.row !== named)
      .map((h) => hit(loaded, h.row, h.score))
      .filter((h) => h.id !== about.id)
      .slice(0, RESULTS);
    return {
      status: "ok",
      mode: "search",
      kind: "similar",
      about: { id: about.id, title: about.title },
      results: hits,
      index_version: manifest.version,
    };
  }
  const q = normalize(await embed(question));
  if (!q) throw new Error("embedding was a zero vector");
  const results = twoStageSearch(q, centroids, index, { k: RESULTS }).map((h) => hit(loaded, h.row, h.score));
  return { status: "ok", mode: "search", kind: "topic", about: null, results, index_version: manifest.version };
}
