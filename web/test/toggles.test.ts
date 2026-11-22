// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadSettings, mountToggles } from "../src/ui/toggles";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("toggles", () => {
  it("reports changes and remembers them", () => {
    const el = document.createElement("div");
    const onChange = vi.fn();
    mountToggles(el, { mode: "2d", performance: false }, onChange);
    const [mode] = Array.from(el.querySelectorAll("button"));
    mode.click();
    expect(onChange).toHaveBeenLastCalledWith({ mode: "3d", performance: false });
    expect(mode.getAttribute("aria-pressed")).toBe("true");
    expect(loadSettings()).toEqual({ mode: "3d", performance: false });
  });

  it("falls back to defaults when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadSettings()).toEqual({ mode: "2d", performance: false });
    const el = document.createElement("div");
    mountToggles(el, loadSettings(), () => {});
    expect(() => el.querySelectorAll("button")[1].click()).not.toThrow();
  });

  it("ignores junk in storage", () => {
    localStorage.setItem("galaxy.settings", "{not json");
    expect(loadSettings()).toEqual({ mode: "2d", performance: false });
  });
});
