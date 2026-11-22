// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import type { Detail } from "../src/data";
import { renderDetail, type DetailView } from "../src/ui/detail";

const DETAIL: Detail = {
  bio: "Makes videos about trains.",
  source_url: "https://youtube.fandom.com/wiki/Train_Guy",
  youtube_url: "https://www.youtube.com/channel/UC123",
  thumbnail: "https://static.wikia.nocookie.net/youtube/images/x.png",
};

function view(over: Partial<DetailView> = {}): DetailView {
  return {
    title: "Train Guy",
    cluster: { name: "Railway Fans", colour: "#ff0000" },
    detail: DETAIL,
    neighbours: [{ id: "fandom_2", title: "Rail Gal" }],
    onSelect: vi.fn(),
    onRetry: vi.fn(),
    onClose: vi.fn(),
    ...over,
  };
}

function render(over: Partial<DetailView> = {}) {
  const el = document.createElement("div");
  const v = view(over);
  renderDetail(el, v);
  return { el, v };
}

const links = (el: HTMLElement) => Array.from(el.querySelectorAll("a"));

describe("detail panel", () => {
  it("links the wiki source page in a new tab", () => {
    const a = links(render().el).find((l) => l.textContent === "Read on the YouTube Wiki")!;
    expect(a.href).toBe(DETAIL.source_url);
    expect(a.target).toBe("_blank");
    expect(a.rel).toBe("noopener noreferrer");
  });

  it("shows a YouTube link only when there is one", () => {
    expect(links(render().el).some((l) => l.href === DETAIL.youtube_url)).toBe(true);
    const { el } = render({ detail: { ...DETAIL, youtube_url: null } });
    expect(links(el).some((l) => /youtube\.com/.test(l.href))).toBe(false);
  });

  it("loads the thumbnail lazily without a referrer and falls back to text", () => {
    const { el } = render();
    const img = el.querySelector("img")!;
    expect(img.getAttribute("loading")).toBe("lazy");
    expect(img.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(img.getAttribute("alt")).toBe("");
    img.dispatchEvent(new Event("error"));
    expect(el.querySelector("img")).toBeNull();
    expect(el.querySelector(".card")!.classList.contains("no-thumb")).toBe(true);
  });

  it("renders no image without a thumbnail", () => {
    expect(render({ detail: { ...DETAIL, thumbnail: null } }).el.querySelector("img")).toBeNull();
  });

  it("shows a bio containing HTML as text", () => {
    const { el } = render({ detail: { ...DETAIL, bio: "<img src=x onerror=alert(1)>", thumbnail: null } });
    expect(el.querySelector("img")).toBeNull();
    expect(el.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("flags pages that are gone from the wiki", () => {
    const { el } = render({ detail: { ...DETAIL, missing_from_wiki_since: "2026-12-01" } });
    expect(el.textContent).toContain("No longer on the wiki (since 2026-12-01)");
  });

  it("keeps title, cluster and neighbours when details fail, with a retry", () => {
    const { el, v } = render({ detail: "error" });
    expect(el.textContent).toContain("Details couldn't load");
    expect(el.textContent).toContain("Train Guy");
    expect(el.textContent).toContain("Railway Fans");
    expect(el.textContent).toContain("Rail Gal");
    Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "Retry")!.click();
    expect(v.onRetry).toHaveBeenCalled();
  });

  it("shows a loading line while details load", () => {
    expect(render({ detail: "loading" }).el.textContent).toContain("Loading details…");
  });

  it("selects a neighbour by id", () => {
    const { el, v } = render();
    Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "Rail Gal")!.click();
    expect(v.onSelect).toHaveBeenCalledWith("fandom_2");
  });

  it("says similar creators are loading", () => {
    expect(render({ neighbours: null }).el.textContent).toContain("Loading similar creators…");
  });

  it("closes", () => {
    const { el, v } = render();
    (el.querySelector("button.close") as HTMLButtonElement).click();
    expect(v.onClose).toHaveBeenCalled();
  });
});
