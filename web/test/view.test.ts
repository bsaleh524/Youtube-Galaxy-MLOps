import { describe, expect, it } from "vitest";
import { bounds, fitView } from "../src/view";

describe("bounds", () => {
  it("finds min and max per dimension", () => {
    const b = bounds(new Float32Array([0, 5, 10, -2, 4, 8]), 2);
    expect(b).toEqual({ min: [0, -2], max: [10, 8] });
  });
});

describe("fitView", () => {
  it("centres a 2D box and zooms it to fit with padding", () => {
    const v = fitView({ min: [0, 0], max: [10, 10] }, 1000, 1000);
    expect(v.target).toEqual([5, 5, 0]);
    expect(v.zoom).toBeCloseTo(Math.log2(90));
  });

  it("uses the tighter of width and height", () => {
    const v = fitView({ min: [0, 0], max: [10, 20] }, 1000, 1000, 1);
    expect(v.zoom).toBeCloseTo(Math.log2(50));
  });

  it("centres a 3D box in z too", () => {
    expect(fitView({ min: [0, 0, 2], max: [4, 4, 6] }, 400, 400).target).toEqual([2, 2, 4]);
  });
});
