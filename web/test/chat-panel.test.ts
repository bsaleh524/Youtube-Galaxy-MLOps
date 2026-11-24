// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import type { ChatResult } from "../src/chat";
import { toGalaxy } from "../src/data";
import { HINT, mountChatPanel } from "../src/ui/chat-panel";
import { CLUSTERS, NODES } from "./helpers";

const hit = (id: string, title: string) => ({ id, title, cluster: "x", score: 0.5, url: "u", snippet: `about ${title}` });
const ok = (over: Partial<Extract<ChatResult, { status: "ok" }>> = {}): ChatResult => ({
  status: "ok",
  mode: "search",
  kind: "topic",
  about: null,
  results: [hit("fandom_2", "Beta"), hit("fandom_999", "Unknown"), hit("fandom_3", "Gamma")],
  index_version: "v",
  ...over,
});

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

function mount(ask: (q: string, forceTopic?: boolean) => Promise<ChatResult>) {
  const g = toGalaxy("v", NODES, CLUSTERS);
  const el = document.createElement("aside");
  document.body.append(el);
  const onPick = vi.fn();
  const panel = mountChatPanel(el, g, ask, onPick);
  const input = el.querySelector("input")!;
  const submit = async (q: string) => {
    input.value = q;
    el.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    await new Promise((r) => setTimeout(r, 0));
  };
  const region = el.querySelector<HTMLElement>("[aria-live]")!;
  return { el, input, submit, region, onPick, panel };
}

describe("chat panel", () => {
  it("shows the hint before any question, then hides it", async () => {
    const { region, submit } = mount(async () => ok());
    expect(HINT).toBe(
      'Try a topic (science explainers) or "channels like Vsauce". Search finds creators by what their wiki pages say; it can\'t rank creators or answer who likes whom.',
    );
    expect(region.textContent).toContain(HINT);
    await submit("cooking");
    expect(region.textContent).not.toContain(HINT);
  });

  it("asks with the trimmed text and shows Searching… while waiting", async () => {
    const d = deferred<ChatResult>();
    const ask = vi.fn(() => d.promise);
    const { region, input, el } = mount(ask);
    input.value = "  cooking  ";
    el.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(ask).toHaveBeenCalledWith("cooking", false);
    expect(region.textContent).toContain("Searching…");
    d.resolve(ok());
    await new Promise((r) => setTimeout(r, 0));
    expect(region.textContent).not.toContain("Searching…");
  });

  it("lists known results with cluster and snippet, and picks on click", async () => {
    const { region, submit, onPick } = mount(async () => ok());
    await submit("music");
    const buttons = [...region.querySelectorAll<HTMLButtonElement>("button.result")];
    expect(buttons.map((b) => b.querySelector(".title")!.textContent)).toEqual(["Beta", "Gamma"]); // unknown id skipped
    expect(buttons[0].textContent).toContain("Music");
    expect(buttons[0].textContent).toContain("about Beta");
    expect(buttons[0].querySelector<HTMLElement>(".swatch")!.style.background).toBeTruthy();
    buttons[1].click();
    expect(onPick).toHaveBeenCalledWith(2);
  });

  it("titles similar-to results and offers a topic search instead", async () => {
    const ask = vi.fn(async () => ok({ kind: "similar", about: { id: "fandom_1", title: "Alpha" } }));
    const { region, submit, onPick } = mount(ask);
    await submit("like alpha");
    const head = region.querySelector(".chat-head")!;
    expect(head.textContent).toBe("Creators similar to Alpha");
    head.querySelector("button")!.click();
    expect(onPick).toHaveBeenCalledWith(0);
    region.querySelector<HTMLButtonElement>("button.as-topic")!.click();
    expect(ask).toHaveBeenLastCalledWith("like alpha", true);
  });

  it("says when nothing matched", async () => {
    const { region, submit } = mount(async () => ok({ results: [] }));
    await submit("zzz");
    expect(region.textContent).toContain("No matching creators found.");
  });

  it("explains every failure in plain words", async () => {
    const cases: [ChatResult, string][] = [
      [{ status: "resting" }, "Search is resting for today (free quota used up). Try again tomorrow, or search by name above."],
      [{ status: "rate_limited", retry_after: 60 }, "Too many questions at once. Wait a minute and try again."],
      [{ status: "offline" }, "Search is unavailable right now."],
      [{ status: "error" }, "Search is unavailable right now."],
      [{ status: "bad_request", error: "too_long" }, "Keep it under 300 characters."],
      [{ status: "unavailable" }, "Answers are coming soon."],
    ];
    for (const [result, text] of cases) {
      const { region, submit } = mount(async () => result);
      await submit("q");
      expect(region.textContent).toContain(text);
    }
  });

  it("ignores empty questions and limits length", async () => {
    const ask = vi.fn(async () => ok());
    const { input, submit } = mount(ask);
    await submit("   ");
    expect(ask).not.toHaveBeenCalled();
    expect(input.maxLength).toBe(300);
  });

  it("shows only the latest answer when questions overlap", async () => {
    const first = deferred<ChatResult>();
    const second = deferred<ChatResult>();
    const answers = [first.promise, second.promise];
    const { region, submit } = mount(() => answers.shift()!);
    await submit("one");
    await submit("two");
    second.resolve(ok({ results: [hit("fandom_3", "Gamma")] }));
    await new Promise((r) => setTimeout(r, 0));
    first.resolve(ok({ results: [hit("fandom_2", "Beta")] }));
    await new Promise((r) => setTimeout(r, 0));
    expect(region.textContent).toContain("Gamma");
    expect(region.textContent).not.toContain("Beta");
  });

  it("closes and reopens with results intact", async () => {
    const { el, region, submit, panel } = mount(async () => ok());
    await submit("music");
    el.querySelector<HTMLButtonElement>("button.close")!.click();
    expect(el.classList.contains("closed")).toBe(true);
    panel.open();
    expect(el.classList.contains("closed")).toBe(false);
    expect(region.textContent).toContain("Beta");
  });
});
