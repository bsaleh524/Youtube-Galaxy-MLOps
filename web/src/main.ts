import "./style.css";
import type { Focus } from "./colour";
import { askChat, chatUrl } from "./chat";
import { BASE } from "./config";
import { createLoader, DataError, loadGalaxy, loadManifest, type Galaxy, type Loader, type Manifest } from "./data";
import { formatHash, parseHash, type HashState } from "./hash";
import { createMap, type GalaxyMap } from "./map";
import { makeSearch } from "./search";
import { mountChatPanel } from "./ui/chat-panel";
import { renderDetail } from "./ui/detail";
import { renderFooter } from "./ui/footer";
import { renderLegend, type Legend } from "./ui/legend";
import { mountSearchBox } from "./ui/search-box";
import { loadSettings, mountToggles, type Settings } from "./ui/toggles";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

export interface App {
  g: Galaxy;
  manifest: Manifest;
  map: GalaxyMap;
  loader: Loader;
  neighbours: Record<string, string[]> | null;
  selected: number | null;
  cluster: number | null;
  settings: Settings;
  legend: Legend | null;
}

function showTooltip(g: Galaxy, i: number | null, x: number, y: number) {
  const tip = $("tooltip");
  if (i === null) {
    tip.hidden = true;
    return;
  }
  tip.replaceChildren();
  const title = document.createElement("div");
  title.textContent = g.titles[i];
  const sub = document.createElement("div");
  sub.className = "sub";
  sub.textContent = g.clusters[g.cluster[i]].name;
  tip.append(title, sub);
  tip.style.left = `${x + 12}px`;
  tip.style.top = `${y + 12}px`;
  tip.hidden = false;
}

function setHash(s: HashState) {
  const h = formatHash(s);
  history.replaceState(null, "", h || location.pathname + location.search);
}

/** Neighbour positions of creator i (known ids only), or [] until neighbours.json has loaded. */
function neighbourIdx(app: App, i: number): number[] {
  const ids = app.neighbours?.[app.g.ids[i]] ?? [];
  return ids.map((id) => app.g.index.get(id)).filter((j): j is number => j !== undefined);
}

function showDetail(app: App, i: number | null) {
  const panel = $("detail");
  if (i === null) {
    panel.hidden = true;
    return;
  }
  const { g } = app;
  const info = g.clusters[g.cluster[i]];
  const id = g.ids[i];
  const neighbours = app.neighbours
    ? neighbourIdx(app, i).map((j) => ({ id: g.ids[j], title: g.titles[j] }))
    : null;
  const draw = (detail: Parameters<typeof renderDetail>[1]["detail"]) =>
    renderDetail(panel, {
      title: g.titles[i],
      cluster: { name: info.name, colour: info.colour },
      detail,
      neighbours,
      onSelect: (nid) => {
        const j = g.index.get(nid);
        if (j !== undefined) selectCreator(app, j);
      },
      onRetry: () => showDetail(app, i),
      onClose: () => clearSelection(app),
    });
  draw("loading");
  panel.hidden = false;
  app.loader.details(info.key).then(
    (d) => app.selected === i && draw(d[id] ?? null),
    () => app.selected === i && draw("error"),
  );
}

export function selectCreator(app: App, i: number, fly = true) {
  app.selected = i;
  app.cluster = null;
  const keep = neighbourIdx(app, i);
  const focus: Focus = { cluster: app.g.cluster[i], keep: [i, ...keep] };
  app.map.setFocus(focus);
  app.map.setLinks(i, keep);
  if (fly) app.map.flyTo(i);
  setHash({ creator: app.g.ids[i] });
  showDetail(app, i);
}

export function selectCluster(app: App, c: number) {
  const info = app.g.clusters[c];
  app.selected = null;
  app.cluster = c;
  app.map.setFocus({ cluster: c });
  app.map.setLinks(null, []);
  showDetail(app, null);
  app.legend?.showMembers(c);
  const mode3d = app.settings.mode === "3d";
  const centre = mode3d ? [info.cx3, info.cy3, info.cz3] : [info.cx2, info.cy2, 0];
  if (centre.every((v) => v !== null)) app.map.flyToPoint(centre as number[]);
  setHash({ cluster: info.key });
}

export function clearSelection(app: App) {
  app.selected = null;
  app.cluster = null;
  app.map.setFocus(null);
  app.map.setLinks(null, []);
  showDetail(app, null);
  app.legend?.showClusters();
  setHash({});
}

function applyHash(app: App) {
  const h = parseHash(location.hash);
  if (h.creator !== undefined) {
    const i = app.g.index.get(h.creator);
    if (i !== undefined) selectCreator(app, i);
  } else if (h.cluster !== undefined) {
    const c = app.g.clusters.findIndex((k) => k.key === h.cluster);
    if (c >= 0) selectCluster(app, c);
  }
}

function loadNeighboursLater(app: App) {
  const go = () =>
    app.loader.neighbors().then(
      (n) => {
        app.neighbours = n;
        if (app.selected !== null) selectCreator(app, app.selected, false);
      },
      (e) => console.warn("similar creators couldn't load", e),
    );
  if ("requestIdleCallback" in window) window.requestIdleCallback(() => void go(), { timeout: 2000 });
  else setTimeout(() => void go(), 500);
}

const isPhone = () => !(window.matchMedia?.("(min-width: 700px)").matches ?? true);

/** The chat side panel, only when a chat Worker is configured (manifest chat.url or VITE_CHAT_URL). */
function mountChat(app: App) {
  const url = chatUrl(app.manifest);
  if (!url) return;
  const slot = $("chat-slot");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "toggle chat-toggle";
  btn.textContent = "Ask";
  btn.setAttribute("aria-controls", "chat-slot");
  const panel = mountChatPanel(
    slot,
    app.g,
    (q, forceTopic) => askChat(fetch, url, q, { forceTopic }),
    (i) => {
      selectCreator(app, i);
      if (isPhone()) setOpen(false); // the creator card needs the bottom of the screen
    },
  );
  const setOpen = (open: boolean) => {
    if (open) panel.open();
    else panel.close();
    btn.setAttribute("aria-expanded", String(open));
  };
  new MutationObserver(() => btn.setAttribute("aria-expanded", String(!slot.classList.contains("closed")))).observe(
    slot,
    { attributes: true, attributeFilter: ["class"] },
  );
  btn.addEventListener("click", () => setOpen(slot.classList.contains("closed")));
  slot.hidden = false;
  setOpen(!isPhone());
  $("toggles").prepend(btn);
}

async function start() {
  const status = $("status");
  let g: Galaxy;
  let manifest: Manifest;
  try {
    manifest = await loadManifest(fetch, BASE);
    g = await loadGalaxy(fetch, BASE, manifest);
  } catch (e) {
    status.textContent = "The map couldn't load. Try refreshing.";
    if (!(e instanceof DataError)) throw e;
    console.error(e);
    return;
  }
  status.textContent = "";
  renderFooter($("footer"), manifest);
  const settings = loadSettings();
  const app = { g, manifest, neighbours: null, selected: null, cluster: null, settings, legend: null } as unknown as App;
  app.loader = createLoader(fetch, BASE, manifest.version);
  app.map = createMap($<HTMLDivElement>("map"), g, {
    onHover: (i, x, y) => showTooltip(g, i, x, y),
    onClick: (i) => (i === null ? clearSelection(app) : selectCreator(app, i, false)),
  });

  mountSearchBox($("search"), g, makeSearch(g.titles), (i) => selectCreator(app, i));
  const titleOf = (id: string) => {
    const i = g.index.get(id);
    return i === undefined ? undefined : g.titles[i];
  };
  let byCluster: number[][] | null = null; // creator positions per cluster, built on first use
  app.legend = renderLegend($("legend"), g.clusters, titleOf, (c) => selectCluster(app, c), {
    membersOf: (c) => {
      if (!byCluster) {
        byCluster = g.clusters.map(() => []);
        g.cluster.forEach((k, i) => byCluster![k]?.push(i));
      }
      return byCluster[c] ?? [];
    },
    titleAt: (i) => g.titles[i],
    onPickCreator: (i) => selectCreator(app, i),
    onBack: () => clearSelection(app),
  });

  const applySettings = (s: Settings) => {
    app.settings = s;
    app.map.setMode(s.mode);
    app.map.setPerformance(s.performance);
    if (app.selected !== null) selectCreator(app, app.selected, false);
  };
  mountToggles($("toggles"), settings, applySettings);
  applySettings(settings);

  // Cluster list: open on wide screens, a toggle-able sheet on phones.
  const legend = $("legend");
  const legendBtn = document.createElement("button");
  legendBtn.type = "button";
  legendBtn.className = "toggle legend-toggle";
  legendBtn.textContent = "Clusters";
  legendBtn.setAttribute("aria-controls", "legend");
  const setLegend = (open: boolean) => {
    legend.classList.toggle("closed", !open);
    legendBtn.setAttribute("aria-expanded", String(open));
  };
  setLegend(window.matchMedia?.("(min-width: 700px)").matches ?? true);
  legendBtn.addEventListener("click", () => setLegend(legend.classList.contains("closed")));
  $("toggles").prepend(legendBtn);
  mountChat(app);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !(e.target instanceof HTMLInputElement)) clearSelection(app);
  });
  window.addEventListener("hashchange", () => applyHash(app));
  applyHash(app);
  loadNeighboursLater(app);
  (window as unknown as { galaxyApp: App }).galaxyApp = app; // handy for debugging in the console
}

void start();
