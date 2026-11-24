import { describe, expect, it } from "vitest";
import { fold, makeSearch } from "../src/search";

describe("fold", () => {
  it("strips accents, case and punctuation", () => {
    expect(fold("Pokémon  Go!")).toBe("pokemon go");
    expect(fold("  ")).toBe("");
  });
});

describe("makeSearch", () => {
  it("same-title creators both match", () => {
    const search = makeSearch(["Target", "TARGET", "Target3DGaming"]);
    const r = search("target");
    expect(new Set(r.slice(0, 2))).toEqual(new Set([0, 1]));
    expect(r[2]).toBe(2);
  });

  it("ranks a prefix match above a substring match", () => {
    expect(makeSearch(["LS Mark", "Markiplier"])("mark")).toEqual([1, 0]);
  });

  it("ranks a word prefix above a plain substring", () => {
    expect(makeSearch(["Remarkable", "The Mark Show"])("mark")).toEqual([1, 0]);
  });

  it("matches without accents", () => {
    expect(makeSearch(["Pokémon Fan", "Other"])("pokemon")).toEqual([0]);
  });

  it("respects the limit and ignores empty queries", () => {
    const search = makeSearch(Array.from({ length: 30 }, (_, i) => `Creator ${i}`));
    expect(search("creator").length).toBe(10);
    expect(search("creator", 3).length).toBe(3);
    expect(search("")).toEqual([]);
    expect(search("   ")).toEqual([]);
  });

  it("answers fast on 20,000 titles", () => {
    const titles = Array.from({ length: 20000 }, (_, i) => `Channel ${i} ${(i * 7919).toString(36)}`);
    const search = makeSearch(titles);
    const t = performance.now();
    search("channel 1999");
    expect(performance.now() - t).toBeLessThan(50);
  });
});
