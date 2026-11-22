import "./style.css";
import type { Focus } from "./colour";
import { BASE } from "./config";
import { createLoader, DataError, loadGalaxy, loadManifest, type Galaxy, type Loader, type Manifest } from "./data";
import { formatHash, parseHash, type HashState } from "./hash";
import { createMap, type GalaxyMap } from "./map";
import { makeSearch } from "./search";
import { renderLegend } from "./ui/legend";
import { mountSearchBox } from "./ui/search-box";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

export interface App {
  g: Galaxy;
  manifest: Manifest;
  map: GalaxyMap;
  loader: Loader;
  neighbours: Record<string, string[]> | null;
  selected: number | null;
  cluster: number | null;
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

// Task 5 replaces this with the detail panel.
let showDetail: (app: App, i: number | null) => void = () => {};
export function setDetailRenderer(fn: (app: App, i: number | null) => void) {
  showDetail = fn;
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
  const mode3d = document.body.dataset.mode === "3d";
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
  const app = { g, manifest, neighbours: null, selected: null, cluster: null } as unknown as App;
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
  renderLegend($("legend"), g.clusters, titleOf, (c) => selectCluster(app, c));

  // Temporary 2D/3D switch; Task 5 replaces it with the toggles module.
  const btn = document.createElement("button");
  btn.className = "toggle";
  btn.textContent = "3D";
  btn.setAttribute("aria-pressed", "false");
  btn.onclick = () => {
    const to3d = btn.getAttribute("aria-pressed") !== "true";
    btn.setAttribute("aria-pressed", String(to3d));
    document.body.dataset.mode = to3d ? "3d" : "2d";
    app.map.setMode(to3d ? "3d" : "2d");
  };
  $("toggles").append(btn);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !(e.target instanceof HTMLInputElement)) clearSelection(app);
  });
  window.addEventListener("hashchange", () => applyHash(app));
  applyHash(app);
  loadNeighboursLater(app);
  (window as unknown as { galaxyApp: App }).galaxyApp = app; // handy for debugging in the console
}

void start();
