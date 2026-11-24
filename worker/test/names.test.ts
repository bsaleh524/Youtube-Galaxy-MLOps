import { describe, expect, it } from "vitest";
import { type IndexView, type MetaView, parseMeta } from "../src/format";
import { buildNameIndex, creatorVector, findNamedCreator, foldName } from "../src/names";

/** Encode records in the meta.bin layout parseMeta reads: magic, u32 n, (n+1) u32 offsets, blob. */
function makeMeta(titles: string[]): MetaView {
  const enc = new TextEncoder();
  const parts = titles.map((title, i) =>
    enc.encode(JSON.stringify({ id: `fandom_${i}`, title, cluster: "C", url: "u", snippet: "s" })),
  );
  const blobLen = parts.reduce((a, p) => a + p.length, 0);
  const buf = new ArrayBuffer(12 + 4 * (titles.length + 1) + blobLen);
  const bytes = new Uint8Array(buf);
  bytes.set(enc.encode("GXMETA1\0"), 0);
  new DataView(buf).setUint32(8, titles.length, true);
  const offsets = new Uint32Array(buf, 12, titles.length + 1);
  let pos = 0;
  const base = 12 + 4 * (titles.length + 1);
  parts.forEach((p, i) => {
    offsets[i] = pos;
    bytes.set(p, base + pos);
    pos += p.length;
  });
  offsets[titles.length] = pos;
  return parseMeta(buf);
}

const TITLES = ["Markiplier", "Mark", "Mark Rober", "Target", "TARGET", "Minecraft", "Dream", "ab"];
const names = buildNameIndex(makeMeta(TITLES));
const row = (t: string) => TITLES.indexOf(t);

describe("foldName", () => {
  it("strips accents, case and punctuation", () => {
    expect(foldName("Café  Ñandú!")).toBe("cafe nandu");
  });
  it("keeps non-Latin letters", () => {
    expect(foldName("ねくろちゃん -Yamaguro Nekuro-")).toBe("ねくろちゃん yamaguro nekuro");
  });
});

describe("findNamedCreator", () => {
  it("matches a question that is just a title", () => {
    expect(findNamedCreator("Markiplier", names)).toBe(row("Markiplier"));
    expect(findNamedCreator("markiplier?", names)).toBe(row("Markiplier"));
  });
  it("matches a title after a cue", () => {
    expect(findNamedCreator("channels like Markiplier", names)).toBe(row("Markiplier"));
    expect(findNamedCreator("YouTubers similar to Mark Rober", names)).toBe(row("Mark Rober"));
    expect(findNamedCreator("more like dream", names)).toBe(row("Dream"));
    expect(findNamedCreator("The best creators similar to markiplier", names)).toBe(row("Markiplier"));
  });
  it("prefers the longest title and allows filler words after it", () => {
    expect(findNamedCreator("like mark rober videos", names)).toBe(row("Mark Rober"));
  });
  it("needs a cue or a whole-question match", () => {
    expect(findNamedCreator("minecraft speedruns", names)).toBeNull();
  });
  it("needs the title to end the question", () => {
    expect(findNamedCreator("videos like minecraft speedruns", names)).toBeNull();
  });
  it("ignores titles shorter than 3 characters", () => {
    expect(findNamedCreator("like ab", names)).toBeNull();
  });
  it("returns null for an ordinary topic question", () => {
    expect(findNamedCreator("science explainers", names)).toBeNull();
  });
});

describe("buildNameIndex", () => {
  it("maps duplicate titles to the lowest row", () => {
    expect(names.get("target")).toBe(row("Target"));
  });
});

describe("creatorVector", () => {
  it("dequantises a row to a unit vector close to the original", () => {
    const dim = 8;
    const orig = Float32Array.from([0.3, -0.5, 0.1, 0.9, -0.2, 0.05, 0.4, -0.7]);
    const scale = Math.max(...orig.map(Math.abs)) / 127;
    const vecs = new Int8Array(2 * dim);
    for (let d = 0; d < dim; d++) vecs[dim + d] = Math.round(orig[d] / scale);
    const idx: IndexView = {
      n: 2,
      dim,
      k: 1,
      offsets: Uint32Array.from([0, 2]),
      scales: Float32Array.from([1, scale]),
      vecs,
    };
    const v = creatorVector(idx, 1);
    const norm = Math.hypot(...v);
    expect(norm).toBeCloseTo(1, 5);
    const on = Math.hypot(...orig);
    const cos = v.reduce((a, x, d) => a + x * orig[d], 0) / on;
    expect(cos).toBeGreaterThan(0.99);
  });
});

describe("topic words", () => {
  const withTopics = buildNameIndex(makeMeta(TITLES), new Set(["minecraft", "music"]));
  it("never treats a common topic word as a creator name", () => {
    expect(findNamedCreator("minecraft", withTopics)).toBeNull();
    expect(findNamedCreator("channels like Minecraft", withTopics)).toBeNull();
  });
  it("still finds other names", () => {
    expect(findNamedCreator("channels like Markiplier", withTopics)).toBe(row("Markiplier"));
  });
});
