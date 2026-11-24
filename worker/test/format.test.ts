import { describe, expect, it } from "vitest";
import { parseCentroids, parseIndex, parseMeta, readRecord } from "../src/format";
import { fixtureBuffer, fixtureJson } from "./helpers";

describe("binary formats", () => {
  it("parses the fixture index header and offsets", async () => {
    const idx = parseIndex(await fixtureBuffer("index.bin"));
    expect([idx.n, idx.dim, idx.k]).toEqual([600, 384, 12]);
    expect(idx.offsets[12]).toBe(600);
    expect(idx.vecs.length).toBe(600 * 384);
    expect(idx.scales.length).toBe(600);
  });

  it("parses centroids", async () => {
    const c = parseCentroids(await fixtureBuffer("centroids.bin"));
    expect([c.k, c.dim, c.data.length]).toEqual([12, 384, 12 * 384]);
  });

  it("throws on bad magic", () => {
    const buf = new Uint8Array(64).buffer;
    expect(() => parseIndex(buf)).toThrow("bad magic: index");
    expect(() => parseCentroids(buf)).toThrow("bad magic: centroids");
    expect(() => parseMeta(buf)).toThrow("bad magic: meta");
  });

  it("decodes UTF-8 records by byte offset, including same-titled channels", async () => {
    const meta = parseMeta(await fixtureBuffer("meta_utf8.bin"));
    const want = await fixtureJson<unknown[]>("meta_utf8.json");
    expect(meta.n).toBe(want.length);
    for (let i = 0; i < want.length; i++) expect(readRecord(meta, i)).toEqual(want[i]);
    expect(readRecord(meta, 0).title).toBe("ねくろちゃん -Yamaguro Nekuro-");
    expect([readRecord(meta, 2).id, readRecord(meta, 3).id]).toEqual(["fandom_449281", "fandom_372805"]);
  });

  it("reads a record from the main fixture meta", async () => {
    const meta = parseMeta(await fixtureBuffer("meta.bin"));
    expect(meta.n).toBe(600);
    expect(readRecord(meta, 5).id).toBe("syn_5");
  });
});
