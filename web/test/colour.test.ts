import { describe, expect, it } from "vitest";
import { DIM_ALPHA, fillColours, hexToRgb } from "../src/colour";
import { toGalaxy } from "../src/data";
import { CLUSTERS, NODES } from "./helpers";

const g = toGalaxy("v1", NODES, CLUSTERS); // node 0 in cluster 0 (red), nodes 1–2 in cluster 1 (green)

const alphas = (c: Uint8Array) => Array.from({ length: c.length / 4 }, (_, i) => c[i * 4 + 3]);

describe("hexToRgb", () => {
  it("parses #rrggbb", () => {
    expect(hexToRgb("#f10080")).toEqual([241, 0, 128]);
  });
});

describe("fillColours", () => {
  it("colours every node by its cluster at full alpha with no focus", () => {
    const c = fillColours(g, null);
    expect(c.length).toBe(12);
    expect(Array.from(c.slice(0, 4))).toEqual([255, 0, 0, 255]);
    expect(Array.from(c.slice(4, 8))).toEqual([0, 255, 0, 255]);
    expect(alphas(c)).toEqual([255, 255, 255]);
  });

  it("dims everything outside the focused cluster", () => {
    expect(alphas(fillColours(g, { cluster: 1 }))).toEqual([DIM_ALPHA, 255, 255]);
    expect(DIM_ALPHA).toBe(40);
  });

  it("keeps listed nodes bright", () => {
    expect(alphas(fillColours(g, { cluster: 1, keep: [0] }))).toEqual([255, 255, 255]);
  });

  it("reuses the out buffer", () => {
    const out = new Uint8Array(12);
    expect(fillColours(g, null, out)).toBe(out);
  });
});
