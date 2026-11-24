// Local Node benchmark of the two-stage search on the full-size synthetic spike index.
// Numbers are indicative only: the deployed Workers runtime is what counts against the 10 ms limit.
import { existsSync, readFileSync } from "node:fs";
import { bench, describe } from "vitest";
import { parseCentroids, parseIndex } from "../src/format";
import { bruteForce, twoStageSearch } from "../src/search";

const dir = new URL("../../data/spike/", import.meta.url);
const have = existsSync(new URL("index.bin", dir));

function load(name: string): ArrayBuffer {
  const b = readFileSync(new URL(name, dir));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
}

describe.skipIf(!have)("search on data/spike (20.8K x 384, 120 clusters)", () => {
  const idx = have ? parseIndex(load("index.bin")) : (null as never);
  const cents = have ? parseCentroids(load("centroids.bin")) : (null as never);
  let seed = 12345;
  const rand = () => ((seed = (seed * 1103515245 + 12345) >>> 0) / 2 ** 32) * 2 - 1;
  const queries = Array.from({ length: 200 }, () => Float32Array.from({ length: 384 }, rand));
  let i = 0;

  bench("twoStageSearch (k=10, defaults)", () => {
    twoStageSearch(queries[i++ % queries.length], cents, idx);
  });
  bench("bruteForce (k=10)", () => {
    bruteForce(queries[i++ % queries.length], idx, 10);
  });
});
