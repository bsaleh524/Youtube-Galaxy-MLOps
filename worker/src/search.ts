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

// Keeps the best k hits sorted best-first (higher score; equal scores → lower row) in two typed
// arrays, so scoring candidates allocates nothing. Hit objects are built once, for the final k only.
// Allocation-free scoring matters on the Workers free plan: per-candidate objects caused GC pauses
// that pushed the p99 CPU time past the 10 ms limit (docs/NOTES.md, Checkpoint 1).
class TopK {
  private readonly scores: Float64Array;
  private readonly rows: Int32Array;
  private size = 0;
  constructor(private readonly k: number, capacityHint: number) {
    const cap = Math.max(0, Math.min(k, capacityHint));
    this.scores = new Float64Array(cap);
    this.rows = new Int32Array(cap);
  }
  push(row: number, score: number): void {
    const cap = this.scores.length;
    const s = this.scores;
    const r = this.rows;
    let n = this.size;
    if (n === cap) {
      const ws = s[n - 1];
      if (!(score > ws || (score === ws && row < r[n - 1]))) return;
      n--; // drop the current worst
    }
    let lo = 0;
    let hi = n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (s[mid] > score || (s[mid] === score && r[mid] < row)) lo = mid + 1;
      else hi = mid;
    }
    for (let i = n; i > lo; i--) {
      s[i] = s[i - 1];
      r[i] = r[i - 1];
    }
    s[lo] = score;
    r[lo] = row;
    this.size = n + 1;
  }
  get hits(): Hit[] {
    const out: Hit[] = new Array(this.size);
    for (let i = 0; i < this.size; i++) out[i] = { row: this.rows[i], score: this.scores[i] };
    return out;
  }
}

function scoreRange(q: Float64Array, idx: IndexView, start: number, end: number, top: TopK): void {
  const dim = idx.dim;
  const vecs = idx.vecs;
  const scales = idx.scales;
  const dim4 = dim - (dim % 4);
  for (let row = start; row < end; row++) {
    const base = row * dim;
    // Four independent accumulators: fewer dependent adds per iteration, better throughput in V8.
    let a0 = 0;
    let a1 = 0;
    let a2 = 0;
    let a3 = 0;
    let d = 0;
    for (; d < dim4; d += 4) {
      a0 += vecs[base + d] * q[d];
      a1 += vecs[base + d + 1] * q[d + 1];
      a2 += vecs[base + d + 2] * q[d + 2];
      a3 += vecs[base + d + 3] * q[d + 3];
    }
    for (; d < dim; d++) a0 += vecs[base + d] * q[d];
    top.push(row, ((a0 + a1 + a2 + a3) * scales[row]) / 127);
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
  const top = new TopK(o.k, probe.candidates);
  const q64 = Float64Array.from(q); // read once as doubles; avoids float32→double per multiply
  for (const ci of probe.clusters) scoreRange(q64, idx, idx.offsets[ci], idx.offsets[ci + 1], top);
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
  const top = new TopK(k, idx.n);
  scoreRange(Float64Array.from(q), idx, 0, idx.n, top);
  return top.hits;
}
