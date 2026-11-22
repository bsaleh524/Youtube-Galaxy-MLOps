import type { ClusterInfo } from "../data";

/** Cluster list, biggest first, with a filter box. onPick gets the cluster's position in `clusters`. */
export function renderLegend(
  el: HTMLElement,
  clusters: ClusterInfo[],
  titleOf: (id: string) => string | undefined,
  onPick: (c: number) => void,
): void {
  el.replaceChildren();
  const head = document.createElement("div");
  head.className = "legend-head";
  const label = document.createElement("label");
  label.textContent = `${clusters.filter((c) => c.size > 0).length} clusters`;
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = "Filter clusters";
  input.setAttribute("aria-label", "Filter clusters");
  label.append(input);
  head.append(label);

  const list = document.createElement("div");
  list.className = "legend-list";
  const order = clusters.map((_, i) => i).filter((i) => clusters[i].size > 0);
  order.sort((a, b) => clusters[b].size - clusters[a].size || a - b);
  const rows = order.map((i) => {
    const c = clusters[i];
    const b = document.createElement("button");
    b.type = "button";
    b.className = "legend-row";
    b.dataset.key = c.key;
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = c.colour;
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = c.name;
    const meta = document.createElement("span");
    meta.className = "meta";
    const leader = c.leader_id ? titleOf(c.leader_id) : undefined;
    meta.textContent = leader ? `${c.size} · e.g. ${leader}` : `${c.size}`;
    b.append(sw, name, meta);
    b.addEventListener("click", () => onPick(i));
    return b;
  });
  list.append(...rows);

  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    for (const r of rows) r.hidden = q !== "" && !(r.querySelector(".name")!.textContent ?? "").toLowerCase().includes(q);
  });
  el.append(head, list);
}
