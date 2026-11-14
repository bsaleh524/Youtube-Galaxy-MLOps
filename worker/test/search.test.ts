// Cross-language check: the fixture and expected results are written by tests/test_index_format.py.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseIndex, readMeta } from "../src/indexFormat";
import { bruteForceSearch, probeClusters, twoStageSearch, type SearchParams } from "../src/search";

const dir = join(__dirname, "fixtures");
const load = (f: string): ArrayBuffer => {
  const b = readFileSync(join(dir, f));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer; // fresh, 0-offset buffer
};
const idx = parseIndex(load("index.bin"), load("centroids.bin"), load("meta.bin"));
const expected = JSON.parse(readFileSync(join(dir, "expected.json"), "utf8")) as {
  params: SearchParams;
  cases: { query: number[]; probe: number[]; two_stage: [number, number][]; brute: [number, number][] }[];
};

describe("index format", () => {
  it("parses header and meta", () => {
    expect(idx.n).toBe(400);
    expect(idx.dim).toBe(32);
    expect(idx.nClusters).toBe(8);
    expect(idx.offsets[8]).toBe(400);
    expect(readMeta(idx, 0).id).toMatch(/^synth_/);
  });
});

describe("two-stage search matches the Python mirror", () => {
  expected.cases.forEach((c, i) => {
    it(`case ${i}`, () => {
      const q = Float32Array.from(c.query);
      expect(probeClusters(idx, q, expected.params)).toEqual(c.probe);

      const ts = twoStageSearch(idx, q, expected.params);
      expect(ts.map((h) => h.row)).toEqual(c.two_stage.map(([r]) => r));
      ts.forEach((h, j) => expect(h.score).toBeCloseTo(c.two_stage[j][1], 4));

      const bf = bruteForceSearch(idx, q, expected.params.k);
      expect(bf.map((h) => h.row)).toEqual(c.brute.map(([r]) => r));
    });
  });

  it("equals brute force when every cluster is probed", () => {
    const all: SearchParams = { k: 10, minProbe: 8, maxProbe: 8, minCandidates: 0, maxCandidates: 1e9 };
    for (const c of expected.cases) {
      const q = Float32Array.from(c.query);
      expect(twoStageSearch(idx, q, all).map((h) => h.row)).toEqual(bruteForceSearch(idx, q, 10).map((h) => h.row));
    }
  });
});
