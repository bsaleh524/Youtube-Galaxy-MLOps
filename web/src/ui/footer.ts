import type { Manifest } from "../data";

function a(href: string, text: string) {
  const l = document.createElement("a");
  l.href = href;
  l.textContent = text;
  l.target = "_blank";
  l.rel = "noopener noreferrer";
  return l;
}

export function renderFooter(el: HTMLElement, m: Manifest): void {
  const at = m.attribution;
  const when = new Date(m.built_at).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  const credit = document.createElement("span");
  credit.append("Creator text from the ", a(at.source_url, at.source), ", available under ");
  credit.append(at.license_url ? a(at.license_url, at.license) : at.license, ". Each creator links its wiki page.");
  const stats = document.createElement("span");
  stats.textContent = `${m.creators.toLocaleString("en-GB")} creators · Last updated ${when}`;
  el.replaceChildren(credit, stats);
}
