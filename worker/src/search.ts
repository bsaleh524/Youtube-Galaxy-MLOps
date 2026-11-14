// Two-stage cosine search: score the query against cluster centroids, then scan only the members of
// the nearest clusters. Mirror of pipeline/index_format.py (probe_clusters, two_stage_search).

import type { LoadedIndex } from "./indexFormat";

export interface SearchParams {
  k: number;
  minProbe: number; // always scan at least this many clusters
  maxProbe: number; // never scan more than this many clusters
  minCandidates: number; // keep adding clusters until this many rows (after minProbe)
  maxCandidates: number; // stop before a cluster would push past this (after minProbe)
}

export const DEFAULT_PARAMS: SearchParams = {
  k: 10,
  minProbe: 3,
  maxProbe: 12,
  minCandidates: 1500,
  maxCandidates: 5000,
};

export interface Hit {
  row: number;
  score: number;
}

export function probeClusters(idx: LoadedIndex, q: Float32Array, p: SearchParams): number[] {
  const { nClusters, dim, centroids, offsets } = idx;
  const cs = new Float64Array(nClusters);
  for (let c = 0; c < nClusters; c++) {
    let s = 0;
    const base = c * dim;
    for (let j = 0; j < dim; j++) s += centroids[base + j] * q[j];
    cs[c] = s;
  }
  const order = Array.from({ length: nClusters }, (_, c) => c);
  order.sort((a, b) => cs[b] - cs[a] || a - b);

  const chosen: number[] = [];
  let cand = 0;
  for (const c of order) {
    if (chosen.length >= p.maxProbe) break;
    if (chosen.length >= p.minProbe && cand >= p.minCandidates) break;
    const size = offsets[c + 1] - offsets[c];
    if (chosen.length >= p.minProbe && cand + size > p.maxCandidates) break;
    chosen.push(c);
    cand += size;
  }
  return chosen;
}

/** Dot product of int8 row `row` with the float query, times the row's scale. */
function rowScore(data: Int8Array, scales: Float32Array, row: number, dim: number, q: Float32Array): number {
  const base = row * dim;
  let s0 = 0, s1 = 0, s2 = 0, s3 = 0;
  let j = 0;
  for (; j + 3 < dim; j += 4) {
    s0 += data[base + j] * q[j];
    s1 += data[base + j + 1] * q[j + 1];
    s2 += data[base + j + 2] * q[j + 2];
    s3 += data[base + j + 3] * q[j + 3];
  }
  for (; j < dim; j++) s0 += data[base + j] * q[j];
  return (s0 + s1 + s2 + s3) * scales[row];
}

/** Insert into a best-first top-k list (k is small). Ties keep the lower row first. */
function pushTopK(top: Hit[], k: number, row: number, score: number): void {
  if (top.length === k) {
    const last = top[k - 1];
    if (score < last.score || (score === last.score && row > last.row)) return;
    top.pop();
  }
  let i = top.length;
  while (i > 0 && (top[i - 1].score < score || (top[i - 1].score === score && top[i - 1].row > row))) i--;
  top.splice(i, 0, { row, score });
}

function scanRows(idx: LoadedIndex, q: Float32Array, start: number, end: number, top: Hit[], k: number): void {
  for (let r = start; r < end; r++) pushTopK(top, k, r, rowScore(idx.data, idx.scales, r, idx.dim, q));
}

export function twoStageSearch(idx: LoadedIndex, q: Float32Array, p: SearchParams = DEFAULT_PARAMS): Hit[] {
  const top: Hit[] = [];
  for (const c of probeClusters(idx, q, p)) scanRows(idx, q, idx.offsets[c], idx.offsets[c + 1], top, p.k);
  return top;
}

export function bruteForceSearch(idx: LoadedIndex, q: Float32Array, k: number): Hit[] {
  const top: Hit[] = [];
  scanRows(idx, q, 0, idx.n, top, k);
  return top;
}

export function l2normalize(v: ArrayLike<number>): Float32Array {
  let s = 0;
  for (let i = 0; i < v.length; i++) s += v[i] * v[i];
  const inv = s > 0 ? 1 / Math.sqrt(s) : 0;
  const out = new Float32Array(v.length);
  for (let i = 0; i < v.length; i++) out[i] = v[i] * inv;
  return out;
}
