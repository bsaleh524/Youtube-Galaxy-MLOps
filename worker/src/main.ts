// Production entry. The index files are bundled into the script as Data modules (see the "rules"
// in wrangler.jsonc), so they are parsed and the search code is JIT-warmed at isolate startup,
// which has its own 1 s budget, instead of inside the first request's 10 ms CPU budget.
// Fetching ~11 MB from static assets inside a request cost 30-50 ms CPU on every cold isolate
// (docs/NOTES.md, Checkpoint 1).
import centroidsBin from "../assets/centroids.bin";
import indexBin from "../assets/index.bin";
import manifest from "../assets/index_manifest.json";
import metaBin from "../assets/meta.bin";
import { parseCentroids, parseIndex, parseMeta, readRecord } from "./format";
import { createHandler } from "./handler";
import { type IndexManifest, type LoadedIndex, validateLoaded } from "./index_loader";
import { twoStageSearch } from "./search";

const loaded: LoadedIndex = validateLoaded({
  manifest: manifest as IndexManifest,
  index: parseIndex(indexBin),
  centroids: parseCentroids(centroidsBin),
  meta: parseMeta(metaBin),
});

// Warm-up: run a few searches now so V8 has optimised the hot loops before any request arrives.
// Deterministic queries; results are discarded.
(function warmUp(rounds: number) {
  const dim = loaded.index.dim;
  let s = 1;
  for (let r = 0; r < rounds; r++) {
    const q = new Float32Array(dim);
    for (let d = 0; d < dim; d++) {
      s = (s * 1103515245 + 12345) >>> 0;
      q[d] = s / 2 ** 32 - 0.5;
    }
    const hits = twoStageSearch(q, loaded.centroids, loaded.index);
    if (hits.length) readRecord(loaded.meta, hits[0].row);
  }
})(20);

const ready = Promise.resolve(loaded);
export default createHandler(() => ready);
