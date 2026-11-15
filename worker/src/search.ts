// Two-stage search: centroids → members of the nearest clusters. Mirrors pipeline/search.py exactly.
import type { CentroidsView, IndexView } from "./format";

export interface SearchOpts {
  k: number;
  probeMin: number;
  minCandidates: number;
  maxProbe: number;
}

export interface Hit {
  row: number;
  score: number;
}

export const DEFAULT_OPTS: SearchOpts = { k: 10, probeMin: 3, minCandidates: 1500, maxProbe: 12 };

export function normalize(v: Float32Array): Float32Array | null {
  let sum = 0;
  for (let i = 0; i < v.length; i++) sum += v[i] * v[i];
  const norm = Math.sqrt(sum);
  if (norm === 0 || !Number.isFinite(norm)) return null;
  const out = new Float32Array(v.length);
  for (let i = 0; i < v.length; i++) out[i] = v[i] / norm;
  return out;
}

// Higher score first; equal scores → lower row first.
function better(a: Hit, b: Hit): boolean {
  return a.score > b.score || (a.score === b.score && a.row < b.row);
}

// Keeps the best k hits in a sorted array; O(candidates * log k) compares + small shifts.
class TopK {
  readonly hits: Hit[] = [];
  constructor(private readonly k: number) {}
  push(h: Hit): void {
    const hits = this.hits;
    if (hits.length === this.k && !better(h, hits[hits.length - 1])) return;
    let lo = 0;
    let hi = hits.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (better(hits[mid], h)) lo = mid + 1;
      else hi = mid;
    }
    hits.splice(lo, 0, h);
    if (hits.length > this.k) hits.pop();
  }
}

function scoreRange(q: Float32Array, idx: IndexView, start: number, end: number, top: TopK): void {
  const dim = idx.dim;
  const vecs = idx.vecs;
  for (let row = start; row < end; row++) {
    let dot = 0;
    const base = row * dim;
    for (let d = 0; d < dim; d++) dot += vecs[base + d] * q[d];
    top.push({ row, score: (dot * idx.scales[row]) / 127 });
  }
}

export interface Probe {
  clusters: number[]; // probed cluster ids, best first
  candidates: number; // total member rows scored
}

// Picks which clusters to score: nearest centroids first (ties → lower id), until
// probed >= probeMin and candidates >= minCandidates, or maxProbe is reached.
export function probeClusters(q: Float32Array, c: CentroidsView, idx: IndexView, opts: SearchOpts): Probe {
  const cscores = new Float64Array(c.k);
  for (let ci = 0; ci < c.k; ci++) {
    let dot = 0;
    const base = ci * c.dim;
    for (let d = 0; d < c.dim; d++) dot += c.data[base + d] * q[d];
    cscores[ci] = dot;
  }
  const order = Array.from({ length: c.k }, (_, i) => i).sort(
    (a, b) => cscores[b] - cscores[a] || a - b,
  );
  const clusters: number[] = [];
  let candidates = 0;
  for (const ci of order) {
    const probed = clusters.length;
    if (probed >= opts.maxProbe || (probed >= opts.probeMin && candidates >= opts.minCandidates)) break;
    clusters.push(ci);
    candidates += idx.offsets[ci + 1] - idx.offsets[ci];
  }
  return { clusters, candidates };
}

export function twoStageSearchWithProbe(
  query: Float32Array,
  c: CentroidsView,
  idx: IndexView,
  opts: Partial<SearchOpts> = {},
): { hits: Hit[]; probe: Probe } {
  const o = { ...DEFAULT_OPTS, ...opts };
  const q = normalize(query);
  if (!q || o.k <= 0) return { hits: [], probe: { clusters: [], candidates: 0 } };
  const probe = probeClusters(q, c, idx, o);
  const top = new TopK(o.k);
  for (const ci of probe.clusters) scoreRange(q, idx, idx.offsets[ci], idx.offsets[ci + 1], top);
  return { hits: top.hits, probe };
}

export function twoStageSearch(
  query: Float32Array,
  c: CentroidsView,
  idx: IndexView,
  opts: Partial<SearchOpts> = {},
): Hit[] {
  return twoStageSearchWithProbe(query, c, idx, opts).hits;
}

export function bruteForce(query: Float32Array, idx: IndexView, k: number): Hit[] {
  const q = normalize(query);
  if (!q || k <= 0) return [];
  const top = new TopK(k);
  scoreRange(q, idx, 0, idx.n, top);
  return top.hits;
}
