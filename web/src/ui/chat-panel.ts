import type { ChatResult } from "../chat";
import type { Galaxy } from "../data";

export const HINT =
  'Try a topic (science explainers) or "channels like Vsauce". Search finds creators by what their wiki pages say; it can\'t rank creators or answer who likes whom.';

const MESSAGES: Record<string, string> = {
  resting: "Search is resting for today (free quota used up). Try again tomorrow, or search by name above.",
  rate_limited: "Too many questions at once. Wait a minute and try again.",
  offline: "Search is unavailable right now.",
  error: "Search is unavailable right now.",
  forbidden: "Search is unavailable right now.",
  unavailable: "Answers are coming soon.",
  too_long: "Keep it under 300 characters.",
  bad_request: "Try asking that a different way.",
};

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

/**
 * The "Ask the galaxy" side panel. `ask(question, forceTopic)` calls the Worker; picking a result
 * calls onPick with the creator's position (results the map doesn't know are skipped).
 */
export function mountChatPanel(
  root: HTMLElement,
  g: Galaxy,
  ask: (q: string, forceTopic?: boolean) => Promise<ChatResult>,
  onPick: (i: number) => void,
): { open(): void; close(): void } {
  root.replaceChildren();
  const head = el("div", "chat-top");
  head.append(el("h2", undefined, "Ask the galaxy"));
  const close = el("button", "close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "Close");
  head.append(close);

  const form = el("form", "chat-form");
  const input = el("input");
  input.type = "text";
  input.maxLength = 300;
  input.placeholder = "e.g. science explainers";
  input.setAttribute("aria-label", "Ask about creators");
  const go = el("button", "go", "Ask");
  go.type = "submit";
  form.append(input, go);

  const region = el("div", "chat-results");
  region.setAttribute("aria-live", "polite");
  region.append(el("p", "hint", HINT));
  const foot = el("p", "chat-foot", "Results by meaning, from YouTube Wiki text.");
  root.append(head, form, region, foot);

  let latest = 0;

  function message(text: string) {
    region.replaceChildren(el("p", "msg", text));
  }

  function creatorButton(i: number, snippet: string): HTMLButtonElement {
    const info = g.clusters[g.cluster[i]];
    const b = el("button", "result");
    b.type = "button";
    const sw = el("span", "swatch");
    sw.style.background = info.colour;
    const meta = el("span", "cluster");
    meta.append(sw, document.createTextNode(info.name));
    b.append(el("span", "title", g.titles[i]), meta, el("span", "snippet", snippet));
    b.addEventListener("click", () => onPick(i));
    return b;
  }

  function show(q: string, r: ChatResult) {
    if (r.status !== "ok") {
      message((r.status === "bad_request" && MESSAGES[r.error]) || MESSAGES[r.status] || MESSAGES.error);
      return;
    }
    const parts: HTMLElement[] = [];
    if (r.kind === "similar" && r.about) {
      const h = el("p", "chat-head");
      const j = g.index.get(r.about.id);
      h.append(document.createTextNode("Creators similar to "));
      if (j === undefined) h.append(document.createTextNode(r.about.title));
      else {
        const b = el("button", "link", r.about.title);
        b.type = "button";
        b.addEventListener("click", () => onPick(j));
        h.append(b);
      }
      const instead = el("button", "as-topic", `Search “${q}” as a topic instead`);
      instead.type = "button";
      instead.addEventListener("click", () => void run(q, true));
      parts.push(h, instead);
    }
    const list = el("ul", "chat-list");
    for (const hit of r.results) {
      const i = g.index.get(hit.id);
      if (i === undefined) continue; // Worker and site data out of step: skip rather than break
      const li = el("li");
      li.append(creatorButton(i, hit.snippet));
      list.append(li);
    }
    if (!list.children.length) parts.push(el("p", "msg", "No matching creators found."));
    else parts.push(list);
    region.replaceChildren(...parts);
  }

  async function run(q: string, forceTopic = false) {
    const mine = ++latest;
    message("Searching…");
    const r = await ask(q, forceTopic);
    if (mine === latest) show(q, r);
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (q) void run(q);
  });

  const api = {
    open() {
      root.classList.remove("closed");
    },
    close() {
      root.classList.add("closed");
    },
  };
  close.addEventListener("click", () => api.close());
  return api;
}
