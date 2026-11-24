// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { renderLegend } from "../src/ui/legend";
import { cluster } from "./helpers";

const clusters = [
  { ...cluster("c001", "Minecraft Survival", "#ff0000", 50), leader_id: "fandom_1" },
  cluster("c002", "Music", "#00ff00", 200),
  cluster("c003", "minecraft · server", "#0000ff", 100),
];
const titleOf = (id: string) => ({ fandom_1: "Dream" })[id];

function setup() {
  const el = document.createElement("div");
  const onPick = vi.fn();
  renderLegend(el, clusters, titleOf, onPick);
  const rows = () => Array.from(el.querySelectorAll<HTMLButtonElement>("button.legend-row")).filter((b) => !b.hidden);
  return { el, onPick, rows };
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
});
