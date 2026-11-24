// Test/dev path: loads the search index from the Worker's static assets once per isolate (module-level cache),
// so only a cold start pays for fetching and parsing ~11 MB. Parsing is zero-copy typed-array views.
import type { Env } from "./env";
import {
  type CentroidsView,
  type IndexView,
  type MetaView,
  parseCentroids,
  parseIndex,
  parseMeta,
} from "./format";
import { buildNameIndex } from "./names";

export interface IndexManifest {
  version: string;
  n: number;
  dim: number;
  k: number;
  model: string;
  topic_words?: string[]; // folded words in >= 5% of bios; never treated as creator names
}

export interface LoadedIndex {
  manifest: IndexManifest;
  index: IndexView;
  centroids: CentroidsView;
  meta: MetaView;
  names: Map<string, number>; // folded title -> row (src/names.ts)
}

let cached: Promise<LoadedIndex> | null = null;

// The four files must come from the same build; a mixed set would return wrong titles silently.
export function validateLoaded<T extends Omit<LoadedIndex, "names">>(l: T): T {
  const { manifest: m, index: i, centroids: c, meta } = l;
  const checks: [string, number, string, number][] = [
    ["manifest.n", m.n, "index.n", i.n],
    ["manifest.dim", m.dim, "index.dim", i.dim],
    ["manifest.k", m.k, "index.k", i.k],
    ["meta.n", meta.n, "index.n", i.n],
    ["centroids.k", c.k, "index.k", i.k],
    ["centroids.dim", c.dim, "index.dim", i.dim],
    ["index.offsets[k]", i.offsets[i.k], "index.n", i.n],
  ];
  for (const [a, av, b, bv] of checks) {
    if (av !== bv) throw new Error(`index files disagree: ${a} ${av} != ${b} ${bv}`);
  }
  return l;
}

async function asset(env: Env, name: string): Promise<Response> {
  if (!env.ASSETS) throw new Error("no ASSETS binding (production bundles the index; see src/main.ts)");
  const res = await env.ASSETS.fetch(`https://assets.local/${name}`);
  if (!res.ok) throw new Error(`asset ${name}: HTTP ${res.status}`);
  return res;
}

async function load(env: Env): Promise<LoadedIndex> {
  const [manifest, index, centroids, meta] = await Promise.all([
    asset(env, "index_manifest.json").then((r) => r.json() as Promise<IndexManifest>),
    asset(env, "index.bin").then((r) => r.arrayBuffer()),
    asset(env, "centroids.bin").then((r) => r.arrayBuffer()),
    asset(env, "meta.bin").then((r) => r.arrayBuffer()),
  ]);
  return assemble(manifest, index, centroids, meta);
}

/** Parse, cross-check and add the name index. Shared by the test loader and src/main.ts. */
export function assemble(
  manifest: IndexManifest,
  index: ArrayBuffer,
  centroids: ArrayBuffer,
  meta: ArrayBuffer,
): LoadedIndex {
  const parts = validateLoaded({
    manifest,
    index: parseIndex(index),
    centroids: parseCentroids(centroids),
    meta: parseMeta(meta),
  });
  return { ...parts, names: buildNameIndex(parts.meta, new Set(manifest.topic_words ?? [])) };
}

export function getIndex(env: Env): Promise<LoadedIndex> {
  if (!cached) {
    cached = load(env).catch((err) => {
      cached = null; // don't cache failures
      throw err;
    });
  }
  return cached;
}
