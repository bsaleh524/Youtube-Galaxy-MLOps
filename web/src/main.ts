import "./style.css";
import { BASE } from "./config";
import { DataError, loadGalaxy, loadManifest, type Galaxy } from "./data";
import { createMap, type GalaxyMap } from "./map";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

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

async function start() {
  const status = $("status");
  let g: Galaxy;
  try {
    const manifest = await loadManifest(fetch, BASE);
    g = await loadGalaxy(fetch, BASE, manifest);
  } catch (e) {
    status.textContent = "The map couldn't load. Try refreshing.";
    if (!(e instanceof DataError)) throw e;
    console.error(e);
    return;
  }
  status.textContent = "";
  const map: GalaxyMap = createMap($<HTMLDivElement>("map"), g, {
    onHover: (i, x, y) => showTooltip(g, i, x, y),
    onClick: () => {},
  });

  // Temporary 2D/3D switch; Task 5 replaces it with the toggles module.
  const btn = document.createElement("button");
  btn.className = "toggle";
  btn.textContent = "3D";
  btn.setAttribute("aria-pressed", "false");
  btn.onclick = () => {
    const to3d = btn.getAttribute("aria-pressed") !== "true";
    btn.setAttribute("aria-pressed", String(to3d));
    map.setMode(to3d ? "3d" : "2d");
  };
  $("toggles").append(btn);
}

void start();
