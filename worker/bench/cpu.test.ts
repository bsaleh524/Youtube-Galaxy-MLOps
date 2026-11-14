import { readFileSync } from "node:fs";
import { it } from "vitest";
import { parseIndex, readMeta } from "../src/indexFormat";
import { twoStageSearch, bruteForceSearch, l2normalize, probeClusters, DEFAULT_PARAMS } from "../src/search";
const ld = (f: string) => { const b = readFileSync(new URL("../assets/", import.meta.url).pathname + f); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer; };
it("bench", () => {
  let t = performance.now();
  const idx = parseIndex(ld("index.bin"), ld("centroids.bin"), ld("meta.bin"));
  console.log("parse ms", (performance.now() - t).toFixed(3));
  const qs = Array.from({ length: 600 }, () => l2normalize(Array.from({ length: 384 }, () => Math.random() - 0.5)));
  for (const [name, fn] of [["two-stage", (q: Float32Array) => twoStageSearch(idx, q)], ["brute", (q: Float32Array) => bruteForceSearch(idx, q, 10)]] as const) {
    for (let i = 0; i < 100; i++) fn(qs[i]); // warm up JIT
    const ts: number[] = [];
    for (let i = 100; i < 600; i++) { const s = performance.now(); const h = fn(qs[i]); h.forEach(x => readMeta(idx, x.row)); ts.push(performance.now() - s); }
    ts.sort((a, b) => a - b);
    console.log(name, "p50", ts[250].toFixed(3), "p95", ts[475].toFixed(3), "p99", ts[495].toFixed(3), "ms");
  }
  const cands = qs.slice(0, 200).map(q => probeClusters(idx, q, DEFAULT_PARAMS).reduce((a, c) => a + idx.offsets[c + 1] - idx.offsets[c], 0));
  cands.sort((a, b) => a - b); console.log("candidates p50", cands[100], "max", cands[199]);
}, 120_000);
