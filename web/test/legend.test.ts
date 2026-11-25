// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { renderLegend } from "../src/ui/legend";
import { cluster } from "./helpers";

// The real stylesheet, so tests see what the page shows (a `display` rule can override `hidden`).
const css = document.createElement("style");
css.textContent = readFileSync(resolve(__dirname, "../src/style.css"), "utf8");
document.head.append(css);
const shown = (e: Element | null): boolean =>
  e === null || e === document.body || (getComputedStyle(e).display !== "none" && shown(e.parentElement));

const clusters = [
  { ...cluster("c001", "Minecraft Survival", "#ff0000", 50), leader_id: "fandom_1" },
  cluster("c002", "Music", "#00ff00", 200),
  cluster("c003", "minecraft · server", "#0000ff", 100),
];
const titleOf = (id: string) => ({ fandom_1: "Dream" })[id];

// Creators by position: cluster 0 has rows 0, 2, 3; cluster 1 has row 1.
const TITLES = ["zeta", "Music Guy", "Álvaro", "beta"];
const CLUSTER_OF = [0, 1, 0, 0];

function setup() {
  const el = document.createElement("div");
  el.className = "legend";
  document.body.replaceChildren(el);
  const onPick = vi.fn();
  const onPickCreator = vi.fn();
  const onBack = vi.fn();
  const legend = renderLegend(el, clusters, titleOf, onPick, {
    membersOf: (c) => CLUSTER_OF.flatMap((k, i) => (k === c ? [i] : [])),
    titleAt: (i) => TITLES[i],
    onPickCreator,
    onBack,
  });
  const rows = () => Array.from(el.querySelectorAll<HTMLButtonElement>("button.legend-row")).filter(shown);
  const members = () => Array.from(el.querySelectorAll<HTMLButtonElement>("button.member-row")).filter(shown);
  return { el, onPick, onPickCreator, onBack, legend, rows, members };
}

describe("legend", () => {
  it("lists clusters as buttons, biggest first", () => {
    const { rows } = setup();
    expect(rows().map((b) => b.dataset.key)).toEqual(["c002", "c003", "c001"]);
    expect(rows()[2].textContent).toContain("Dream");
  });

  it("filters by name, ignoring case", () => {
    const { el, rows } = setup();
    const input = el.querySelector("input")!;
    input.value = "mine";
    input.dispatchEvent(new Event("input"));
    expect(rows().map((b) => b.dataset.key)).toEqual(["c003", "c001"]);
  });

  it("reports the cluster's position in clusters, not its sorted rank", () => {
    const { rows, onPick } = setup();
    rows()[0].click(); // c002, position 1
    expect(onPick).toHaveBeenCalledWith(1);
  });

  it("filter really hides rows on the page, not just in the DOM", () => {
    const { el } = setup();
    const input = el.querySelector("input")!;
    input.value = "music";
    input.dispatchEvent(new Event("input"));
    const all = Array.from(el.querySelectorAll("button.legend-row"));
    expect(all.filter(shown).map((b) => (b as HTMLElement).dataset.key)).toEqual(["c002"]);
  });

  it("filter matches whatever the capitalisation", () => {
    const { el, rows } = setup();
    const input = el.querySelector("input")!;
    input.value = "SERVER";
    input.dispatchEvent(new Event("input"));
    expect(rows().map((b) => b.dataset.key)).toEqual(["c003"]);
  });
});

describe("cluster members", () => {
  it("shows a cluster's creators in place of the cluster list, sorted by title", () => {
    const { el, legend, rows, members } = setup();
    legend.showMembers(0);
    expect(rows()).toEqual([]);
    expect(el.querySelector(".members-head")!.textContent).toContain("Minecraft Survival");
    expect(el.querySelector(".members-head")!.textContent).toContain("3 creators");
    expect(members().map((b) => b.textContent)).toEqual(["Álvaro", "beta", "zeta"]);
  });

  it("picking a creator reports its position", () => {
    const { legend, members, onPickCreator } = setup();
    legend.showMembers(0);
    members()[1].click(); // beta, row 3
    expect(onPickCreator).toHaveBeenCalledWith(3);
  });

  it("the back arrow returns to the cluster list, keeping its filter", () => {
    const { el, legend, rows, members, onBack } = setup();
    const input = el.querySelector<HTMLInputElement>(".legend-head input")!;
    input.value = "mine";
    input.dispatchEvent(new Event("input"));
    legend.showMembers(0);
    const back = el.querySelector<HTMLButtonElement>("button.members-back")!;
    expect(back.getAttribute("aria-label")).toBe("Back to clusters");
    back.click();
    expect(onBack).toHaveBeenCalled();
    expect(members()).toEqual([]);
    expect(rows().map((b) => b.dataset.key)).toEqual(["c003", "c001"]);
  });

  it("filters the member list", () => {
    const { el, legend, members } = setup();
    legend.showMembers(0);
    const input = el.querySelector<HTMLInputElement>(".members-head input")!;
    input.value = "alv";
    input.dispatchEvent(new Event("input"));
    expect(members().map((b) => b.textContent)).toEqual(["Álvaro"]);
  });

  it("showClusters goes back without calling onBack; a second cluster replaces the first", () => {
    const { legend, rows, members, onBack } = setup();
    legend.showMembers(0);
    legend.showMembers(1);
    expect(members().map((b) => b.textContent)).toEqual(["Music Guy"]);
    legend.showClusters();
    expect(rows().length).toBe(3);
    expect(onBack).not.toHaveBeenCalled();
  });
});
