// Local Node benchmark of one chat request's CPU work on the real staged index (worker/assets).
import { existsSync, readFileSync } from "node:fs";
import { bench, describe } from "vitest";
import { searchChat } from "../src/chat";
import { readRecord } from "../src/format";
import { assemble, type IndexManifest } from "../src/index_loader";
import { creatorVector, findNamedCreator } from "../src/names";
import { normalize, twoStageSearch } from "../src/search";

const dir = new URL("../assets/", import.meta.url);
const have = existsSync(new URL("index.bin", dir));
const buf = (n: string) => {
  const b = readFileSync(new URL(n, dir));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
};

describe.skipIf(!have)("chat request on worker/assets", () => {
  const args = have
    ? ([JSON.parse(readFileSync(new URL("index_manifest.json", dir), "utf8")) as IndexManifest, buf("index.bin"), buf("centroids.bin"), buf("meta.bin")] as const)
    : (null as never);
  const l = have ? assemble(...args) : (null as never);
  const v = have ? creatorVector(l.index, 1234) : (null as never);
  const embed = async () => v;
  bench("assemble (cold isolate)", () => void assemble(...args));
  bench("findNamedCreator", () => void findNamedCreator("science explainers for kids", l.names));
  bench("twoStageSearch k=8", () => void twoStageSearch(normalize(v)!, l.centroids, l.index, { k: 8 }));
  bench("readRecord x8", () => { for (let r = 0; r < 8; r++) readRecord(l.meta, r * 977); });
  bench("searchChat topic", async () => void (await searchChat(l, "science explainers", embed)));
  bench("searchChat similar", async () => void (await searchChat(l, "channels like Markiplier", embed)));
});
