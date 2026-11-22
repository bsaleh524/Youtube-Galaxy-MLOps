// Loading the galaxy's static files: manifest (uncached pointer) → versioned data files.
// Creators are referenced by id everywhere; array positions are only used inside one loaded Galaxy.

export interface Attribution {
  source: string;
  source_url: string;
  license: string;
  license_url?: string;
  note: string;
}

export interface Manifest {
  version: string;
  built_at: string;
  creators: number;
  clusters: number;
  attribution: Attribution;
}

export interface ClusterInfo {
  key: string;
  name: string;
  colour: string;
  size: number;
  leader_id: string | null;
  cx2: number | null;
  cy2: number | null;
  cx3: number | null;
  cy3: number | null;
  cz3: number | null;
}

export interface Detail {
  bio: string;
  source_url: string;
  youtube_url: string | null;
  thumbnail: string | null;
  missing_from_wiki_since?: string;
}

export interface Galaxy {
  version: string;
  ids: string[];
  titles: string[];
  cluster: Uint16Array;
  pos2: Float32Array; // n*2
  pos3: Float32Array; // n*3
  clusters: ClusterInfo[];
  index: Map<string, number>;
}

export interface NodesJson {
  id: string[];
  title: string[];
  cluster: number[];
  x2: number[];
  y2: number[];
  x3: number[];
  y3: number[];
  z3: number[];
}

export class DataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DataError";
  }
}

export function paths(base: string, version: string) {
  const dir = `${base}data/${version}/`;
  return {
    manifest: `${base}manifest.json`,
    nodes: `${dir}nodes.json`,
    clusters: `${dir}clusters.json`,
    neighbors: `${dir}neighbors.json`,
    details: (key: string) => `${dir}details/cluster_${key}.json`,
  };
}

async function getJson<T>(fetchFn: typeof fetch, url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetchFn(url, init);
  } catch (e) {
    throw new DataError(`could not fetch ${url}: ${(e as Error).message}`);
  }
  if (!res.ok) throw new DataError(`could not fetch ${url}: HTTP ${res.status}`);
  try {
    return (await res.json()) as T;
  } catch {
    throw new DataError(`${url} is not valid JSON`);
  }
}

export function loadManifest(fetchFn: typeof fetch, base: string): Promise<Manifest> {
  return getJson<Manifest>(fetchFn, paths(base, "").manifest, { cache: "no-store" });
}

export function toGalaxy(version: string, nodes: NodesJson, clusters: ClusterInfo[]): Galaxy {
  const n = nodes.id.length;
  for (const col of ["title", "cluster", "x2", "y2", "x3", "y3", "z3"] as const) {
    if (nodes[col]?.length !== n) throw new DataError(`nodes.json column "${col}" has the wrong length`);
  }
  const cluster = new Uint16Array(n);
  const pos2 = new Float32Array(n * 2);
  const pos3 = new Float32Array(n * 3);
  const index = new Map<string, number>();
  for (let i = 0; i < n; i++) {
    const c = nodes.cluster[i];
    if (!(c >= 0 && c < clusters.length)) throw new DataError(`creator ${nodes.id[i]} has unknown cluster ${c}`);
    cluster[i] = c;
    pos2[i * 2] = nodes.x2[i];
    pos2[i * 2 + 1] = nodes.y2[i];
    pos3[i * 3] = nodes.x3[i];
    pos3[i * 3 + 1] = nodes.y3[i];
    pos3[i * 3 + 2] = nodes.z3[i];
    index.set(nodes.id[i], i);
  }
  return { version, ids: nodes.id, titles: nodes.title, cluster, pos2, pos3, clusters, index };
}

export async function loadGalaxy(fetchFn: typeof fetch, base: string, manifest: Manifest): Promise<Galaxy> {
  const p = paths(base, manifest.version);
  const [nodes, clusters] = await Promise.all([
    getJson<NodesJson>(fetchFn, p.nodes),
    getJson<ClusterInfo[]>(fetchFn, p.clusters),
  ]);
  return toGalaxy(manifest.version, nodes, clusters);
}

export interface Loader {
  neighbors(): Promise<Record<string, string[]>>;
  details(key: string): Promise<Record<string, Detail>>;
}

/** Memoised lazy loads; a failed load is forgotten so the next call retries. */
export function createLoader(fetchFn: typeof fetch, base: string, version: string): Loader {
  const p = paths(base, version);
  const cache = new Map<string, Promise<unknown>>();
  function once<T>(url: string): Promise<T> {
    let pr = cache.get(url) as Promise<T> | undefined;
    if (!pr) {
      pr = getJson<T>(fetchFn, url);
      cache.set(url, pr);
      pr.catch(() => cache.delete(url));
    }
    return pr;
  }
  return {
    neighbors: () => once(p.neighbors),
    details: (key) => once(p.details(key)),
  };
}
