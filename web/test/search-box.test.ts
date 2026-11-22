// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { toGalaxy } from "../src/data";
import { makeSearch } from "../src/search";
import { mountSearchBox } from "../src/ui/search-box";
import { CLUSTERS } from "./helpers";

const NODES = {
  id: ["fandom_449281", "fandom_372805"],
  title: ["TARGET", "Target"],
  cluster: [0, 1],
  x2: [0, 1], y2: [0, 1], x3: [0, 1], y3: [0, 1], z3: [0, 1],
};

const key = (input: HTMLInputElement, k: string) => input.dispatchEvent(new KeyboardEvent("keydown", { key: k }));

describe("search box", () => {
  it("picks the highlighted creator, and a second Enter picks nothing else", () => {
    const g = toGalaxy("v1", NODES, CLUSTERS);
    const el = document.createElement("div");
    const onPick = vi.fn();
    mountSearchBox(el, g, makeSearch(g.titles), onPick);
    const input = el.querySelector("input")!;
    input.value = "target";
    input.dispatchEvent(new Event("input"));
    key(input, "ArrowDown");
    key(input, "Enter");
    expect(onPick).toHaveBeenCalledTimes(1);
    const picked = onPick.mock.calls[0][0];
    key(input, "Enter");
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(g.ids[picked]).toBe(g.ids[makeSearch(g.titles)("target")[1]]);
  });
});
