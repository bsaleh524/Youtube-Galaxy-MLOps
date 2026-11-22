import type { Detail } from "../data";

export interface DetailView {
  title: string;
  cluster: { name: string; colour: string };
  detail: Detail | null | "loading" | "error";
  neighbours: { id: string; title: string }[] | null;
  onSelect(id: string): void;
  onRetry(): void;
  onClose(): void;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text; // wiki text is untrusted: text only, never HTML
  return e;
}

/** Wiki data is untrusted: only http(s) URLs become links (no javascript: and the like). */
export function safeUrl(href: string | null | undefined): string | null {
  if (!href) return null;
  try {
    const u = new URL(href);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
  } catch {
    return null;
  }
}

function link(href: string, text: string) {
  const a = el("a", undefined, text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

export function renderDetail(root: HTMLElement, v: DetailView): void {
  root.replaceChildren();
  const close = el("button", "close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "Close details");
  close.addEventListener("click", () => v.onClose());

  const card = el("div", "card");
  const d = typeof v.detail === "object" ? v.detail : null;
  if (d?.thumbnail) {
    const img = el("img", "thumb");
    img.setAttribute("loading", "lazy");
    img.setAttribute("referrerpolicy", "no-referrer");
    img.setAttribute("alt", "");
    img.src = d.thumbnail;
    img.addEventListener("error", () => {
      img.remove();
      card.classList.add("no-thumb");
    });
    card.append(img);
  } else {
    card.classList.add("no-thumb");
  }
  const head = el("div", "head");
  const h = el("h2", undefined, v.title);
  const cl = el("div", "cluster");
  const sw = el("span", "swatch");
  sw.style.background = v.cluster.colour;
  cl.append(sw, document.createTextNode(v.cluster.name));
  head.append(h, cl);
  card.append(head);
  root.append(close, card);

  if (v.detail === "loading") {
    root.append(el("p", "muted", "Loading details…"));
  } else if (v.detail === "error") {
    const p = el("p", "muted", "Details couldn't load. ");
    const retry = el("button", "retry", "Retry");
    retry.type = "button";
    retry.addEventListener("click", () => v.onRetry());
    p.append(retry);
    root.append(p);
  } else if (d) {
    if (d.missing_from_wiki_since) root.append(el("p", "flag", `No longer on the wiki (since ${d.missing_from_wiki_since})`));
    if (d.bio) root.append(el("p", "bio", d.bio));
    const links = el("p", "links");
    const source = safeUrl(d.source_url);
    const youtube = safeUrl(d.youtube_url);
    if (source) links.append(link(source, "Read on the YouTube Wiki"));
    if (youtube) links.append(link(youtube, "YouTube channel"));
    root.append(links);
  }

  root.append(el("h3", undefined, "Similar creators"));
  if (v.neighbours === null) {
    root.append(el("p", "muted", "Loading similar creators…"));
  } else {
    const ul = el("ul", "neighbours");
    for (const n of v.neighbours) {
      const li = el("li");
      const b = el("button", undefined, n.title);
      b.type = "button";
      b.addEventListener("click", () => v.onSelect(n.id));
      li.append(b);
      ul.append(li);
    }
    root.append(ul);
  }
}
