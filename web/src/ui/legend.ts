import type { ClusterInfo } from "../data";

/** What the member view needs: a cluster's creators (positions), their titles, and the callbacks. */
export interface MemberSource {
  membersOf: (c: number) => number[];
  titleAt: (i: number) => string;
  onPickCreator: (i: number) => void;
  onBack: () => void;
}

export interface Legend {
  /** Replace the cluster list with cluster c's creators (A–Z), under a back arrow. */
  showMembers(c: number): void;
  /** Back to the cluster list (its filter is kept). Doesn't call onBack. */
  showClusters(): void;
}

/** Case- and accent-insensitive text for filtering ("Álvaro" → "alvaro"). */
const fold = (s: string) => s.normalize("NFKD").replace(/\p{M}+/gu, "").toLowerCase();

function filterBox(placeholder: string, onInput: (q: string) => void): HTMLInputElement {
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = placeholder;
  input.setAttribute("aria-label", placeholder);
  input.addEventListener("input", () => onInput(fold(input.value.trim())));
  return input;
}

/**
 * Cluster list, biggest first, with a filter box. onPick gets the cluster's position in `clusters`.
 * With `members`, the caller can swap the list for one cluster's creators (showMembers).
 */
export function renderLegend(
  el: HTMLElement,
  clusters: ClusterInfo[],
  titleOf: (id: string) => string | undefined,
  onPick: (c: number) => void,
  members?: MemberSource,
): Legend {
  el.replaceChildren();
  const clusterView = document.createElement("div");
  clusterView.className = "legend-view";
  const head = document.createElement("div");
  head.className = "legend-head";
  const label = document.createElement("label");
  label.textContent = `${clusters.filter((c) => c.size > 0).length} clusters`;

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
    b.dataset.fold = fold(c.name);
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
  label.append(filterBox("Filter clusters", (q) => {
    for (const r of rows) r.hidden = q !== "" && !r.dataset.fold!.includes(q);
  }));
  head.append(label);
  clusterView.append(head, list);

  const memberView = document.createElement("div");
  memberView.className = "legend-view members";
  memberView.hidden = true;
  el.append(clusterView, memberView);

  const showClusters = () => {
    memberView.hidden = true;
    memberView.replaceChildren();
    clusterView.hidden = false;
  };

  const showMembers = (c: number) => {
    if (!members) return;
    const info = clusters[c];
    const mhead = document.createElement("div");
    mhead.className = "legend-head members-head";
    const top = document.createElement("div");
    top.className = "members-top";
    const back = document.createElement("button");
    back.type = "button";
    back.className = "members-back";
    back.textContent = "←";
    back.setAttribute("aria-label", "Back to clusters");
    back.addEventListener("click", () => {
      showClusters();
      members.onBack();
    });
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = info.colour;
    const title = document.createElement("span");
    title.className = "members-title";
    title.textContent = info.name;
    top.append(back, sw, title);

    const ids = members.membersOf(c).map((i) => ({ i, title: members.titleAt(i), key: fold(members.titleAt(i)) }));
    ids.sort((a, b) => a.key.localeCompare(b.key) || a.i - b.i);
    const count = document.createElement("label");
    count.textContent = `${ids.length} creators`;
    const mlist = document.createElement("div");
    mlist.className = "legend-list";
    const mrows = ids.map(({ i, title: t, key }) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "member-row";
      b.textContent = t;
      b.dataset.fold = key;
      b.addEventListener("click", () => members.onPickCreator(i));
      return b;
    });
    mlist.append(...mrows);
    count.append(filterBox("Filter creators", (q) => {
      for (const r of mrows) r.hidden = q !== "" && !r.dataset.fold!.includes(q);
    }));
    mhead.append(top, count);
    memberView.replaceChildren(mhead, mlist);
    clusterView.hidden = true;
    memberView.hidden = false;
    mlist.scrollTop = 0;
  };

  return { showMembers, showClusters };
}
