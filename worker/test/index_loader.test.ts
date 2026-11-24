import { describe, expect, it } from "vitest";
import { parseCentroids, parseIndex, parseMeta } from "../src/format";
import { validateLoaded } from "../src/index_loader";
import { fixtureBuffer, fixtureJson } from "./helpers";

async function parts() {
  return {
    manifest: await fixtureJson<{ version: string; n: number; dim: number; k: number; model: string }>(
      "index_manifest.json",
    ),
    index: parseIndex(await fixtureBuffer("index.bin")),
    centroids: parseCentroids(await fixtureBuffer("centroids.bin")),
    meta: parseMeta(await fixtureBuffer("meta.bin")),
  };
}

describe("validateLoaded", () => {
  it("accepts a consistent set", async () => {
    const p = await parts();
    expect(validateLoaded(p)).toBe(p);
  });

  it("rejects meta from a different build (row count mismatch)", async () => {
    const p = await parts();
    p.meta = parseMeta(await fixtureBuffer("meta_utf8.bin"));
    expect(() => validateLoaded(p)).toThrow(/index files disagree: meta\.n 4 != index\.n 600/);
  });

  it("rejects a manifest that disagrees with the index", async () => {
    const p = await parts();
    p.manifest = { ...p.manifest, n: 601 };
    expect(() => validateLoaded(p)).toThrow(/manifest\.n 601 != index\.n 600/);
  });

  it("rejects centroids with a different k or dim", async () => {
    const p = await parts();
    p.centroids = { ...p.centroids, k: 11 };
    expect(() => validateLoaded(p)).toThrow(/centroids\.k 11 != index\.k 12/);
  });
});
