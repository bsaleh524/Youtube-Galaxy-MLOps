import { beforeAll, describe, expect, it } from "vitest";
import { type CentroidsView, type IndexView, parseCentroids, parseIndex, parseMeta, readRecord } from "../src/format";
import { bruteForce, normalize, twoStageSearch } from "../src/search";
import { fixtureBuffer, fixtureJson } from "./helpers";

type Expected = {
  params: { probeMin: number; minCandidates: number; maxProbe: number };
  results: Record<string, [number, number][][]>;
};

let idx: IndexView;
let cents: CentroidsView;
let queries: Float32Array[];
let expected: Expected;

beforeAll(async () => {
  idx = parseIndex(await fixtureBuffer("index.bin"));
  cents = parseCentroids(await fixtureBuffer("centroids.bin"));
  queries = (await fixtureJson<number[][]>("queries.json")).map((q) => Float32Array.from(q));
  expected = await fixtureJson<Expected>("expected.json");
});

describe("twoStageSearch", () => {
  it("matches the Python implementation on every fixture query (k=5 and k=600)", () => {
    for (const k of ["5", "600"]) {
      queries.forEach((q, i) => {
        const got = twoStageSearch(q, cents, idx, { ...expected.params, k: Number(k) });
        const want = expected.results[k][i];
        expect(got.map((h) => h.row)).toEqual(want.map(([r]) => r));
        got.forEach((h, j) => expect(Math.abs(h.score - want[j][1])).toBeLessThan(1e-4));
      });
    }
  });

  it("returns [] for a zero query", () => {
    expect(twoStageSearch(new Float32Array(384), cents, idx)).toEqual([]);
    expect(normalize(new Float32Array(384))).toBeNull();
  });

  it("returns exactly the candidate count when k exceeds it, without padding", () => {
    const hits = twoStageSearch(queries[0], cents, idx, { k: 10_000, probeMin: 1, minCandidates: 1, maxProbe: 1 });
    const sizes = Array.from({ length: idx.k }, (_, c) => idx.offsets[c + 1] - idx.offsets[c]);
    expect(sizes).toContain(hits.length);
    expect(hits.length).toBeGreaterThan(0);
  });

  it("stops at maxProbe even with empty clusters and huge minCandidates", () => {
    const hits = twoStageSearch(queries[3], cents, idx, { k: 10_000, probeMin: 1, minCandidates: 1e9, maxProbe: 12 });
    expect(hits.length).toBe(600);
  });

  it("equals brute force when probing everything", () => {
    for (const q of queries) {
      const a = twoStageSearch(q, cents, idx, { k: 10, probeMin: 12, maxProbe: 12, minCandidates: 600 });
      expect(a.map((h) => h.row)).toEqual(bruteForce(q, idx, 10).map((h) => h.row));
    }
  });

  it("returns both same-titled channels with identical vectors as separate hits", async () => {
    const meta = parseMeta(await fixtureBuffer("meta.bin"));
    const q = new Float32Array(idx.dim);
    for (let d = 0; d < idx.dim; d++) q[d] = (idx.vecs[d] * idx.scales[0]) / 127;
    const hits = twoStageSearch(q, cents, idx, { k: 5 });
    expect(hits.slice(0, 2).map((h) => h.row)).toEqual([0, 1]);
    expect(hits[0].score).toBe(hits[1].score);
    const [a, b] = [readRecord(meta, 0), readRecord(meta, 1)];
    expect(a.title).toBe("Target");
    expect(b.title).toBe("Target");
    expect(a.id).not.toBe(b.id);
  });
});
