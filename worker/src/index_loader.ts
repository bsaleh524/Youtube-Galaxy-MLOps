// Loads the search index from the Worker's static assets once per isolate (module-level cache),
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

export interface IndexManifest {
  version: string;
  n: number;
  dim: number;
  k: number;
  model: string;
}

export interface LoadedIndex {
  manifest: IndexManifest;
  index: IndexView;
  centroids: CentroidsView;
  meta: MetaView;
}

let cached: Promise<LoadedIndex> | null = null;

async function asset(env: Env, name: string): Promise<Response> {
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
  return {
    manifest,
    index: parseIndex(index),
    centroids: parseCentroids(centroids),
    meta: parseMeta(meta),
  };
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
