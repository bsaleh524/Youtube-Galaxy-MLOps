// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import type { Manifest } from "../src/data";
import { renderFooter } from "../src/ui/footer";

const M: Manifest = {
  version: "v1",
  built_at: "2026-11-18T17:18:50+00:00",
  creators: 20807,
  clusters: 120,
  attribution: {
    source: "YouTube Wiki (Fandom)",
    source_url: "https://youtube.fandom.com/",
    license: "CC BY-SA",
    license_url: "https://www.fandom.com/licensing",
    note: "",
  },
};

describe("footer", () => {
  it("credits the wiki and links the licence", () => {
    const el = document.createElement("footer");
    renderFooter(el, M);
    const a = Array.from(el.querySelectorAll("a"));
    expect(a.find((l) => l.textContent === "YouTube Wiki (Fandom)")!.href).toBe("https://youtube.fandom.com/");
    expect(a.find((l) => l.textContent === "CC BY-SA")!.href).toBe("https://www.fandom.com/licensing");
  });

  it("shows when it was last updated and how many creators", () => {
    const el = document.createElement("footer");
    renderFooter(el, M);
    expect(el.textContent).toContain("Last updated 18 Nov 2026");
    expect(el.textContent).toContain("20,807 creators");
  });
});
