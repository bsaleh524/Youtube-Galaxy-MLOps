// Thin deck.gl wrapper. Logic that can be tested lives in colour.ts and view.ts; this file is checked by eye.
import { Deck, LinearInterpolator, OrbitView, OrthographicView } from "@deck.gl/core";
import { LineLayer, ScatterplotLayer } from "@deck.gl/layers";
import { fillColours, type Focus } from "./colour";
import type { Galaxy } from "./data";
import { bounds, fitView } from "./view";

export type Mode = "2d" | "3d";

export interface MapHandlers {
  onHover(i: number | null, x: number, y: number): void;
  onClick(i: number | null): void;
}

export interface GalaxyMap {
  setMode(m: Mode): void;
  setFocus(f: Focus | null): void;
  setLinks(from: number | null, to: number[]): void;
  flyTo(i: number): void;
  flyToPoint(xy: number[]): void;
  setPerformance(on: boolean): void;
  destroy(): void;
}

const FLY_MS = 600;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ViewState = Record<string, any>;

export function createMap(parent: HTMLDivElement, g: Galaxy, h: MapHandlers): GalaxyMap {
  let mode: Mode = "2d";
  let performance = false;
  let colours = fillColours(g, null);
  let links: { from: number | null; to: number[] } = { from: null, to: [] };
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  const box = { "2d": bounds(g.pos2, 2), "3d": bounds(g.pos3, 3) };

  const homeView = (m: Mode): ViewState => {
    const f = fitView(box[m], parent.clientWidth || 800, parent.clientHeight || 600);
    // The orbit camera is perspective and the box is rotated, so start a bit further out than a flat fit.
    return m === "2d" ? { target: f.target, zoom: f.zoom } : { target: f.target, zoom: f.zoom - 0.6, rotationOrbit: 30, rotationX: 30 };
  };
  let viewState: ViewState = homeView(mode);

  const pos = (i: number): [number, number, number] =>
    mode === "2d" ? [g.pos2[i * 2], g.pos2[i * 2 + 1], 0] : [g.pos3[i * 3], g.pos3[i * 3 + 1], g.pos3[i * 3 + 2]];

  const deck = new Deck<OrthographicView | OrbitView>({
    parent,
    views: new OrthographicView({ id: "2d" }),
    controller: true,
    initialViewState: viewState,
    useDevicePixels: true,
    onViewStateChange: ({ viewState: vs }) => {
      viewState = vs as ViewState;
      return vs;
    },
    onHover: (info) => h.onHover(info.index >= 0 ? info.index : null, info.x, info.y),
    onClick: (info) => h.onClick(info.index >= 0 ? info.index : null),
    getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
  });

  function layers() {
    const out: unknown[] = [
      new ScatterplotLayer({
        id: "creators",
        data: {
          length: g.ids.length,
          attributes: {
            getPosition: { value: mode === "2d" ? g.pos2 : g.pos3, size: mode === "2d" ? 2 : 3 },
            getFillColor: { value: colours, size: 4, normalized: true },
          },
        },
        radiusUnits: "pixels",
        getRadius: performance ? 1.5 : 2.5,
        billboard: mode === "3d",
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 220],
        updateTriggers: { getRadius: performance },
      }),
    ];
    if (links.from !== null && !performance && links.to.length) {
      const from = pos(links.from);
      out.push(
        new LineLayer({
          id: "neighbour-links",
          data: links.to.map((t) => pos(t)),
          getSourcePosition: () => from,
          getTargetPosition: (d: [number, number, number]) => d,
          getColor: [255, 255, 255, 160],
          getWidth: 1,
        }),
      );
    }
    return out;
  }

  function render() {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    deck.setProps({ layers: layers() as any });
  }

  function jump(target: number[], zoom: number) {
    const animate = !performance && !reducedMotion?.matches;
    viewState = {
      ...viewState,
      target: [target[0], target[1], target[2] ?? 0],
      zoom,
      transitionDuration: animate ? FLY_MS : 0,
      transitionInterpolator: animate ? new LinearInterpolator(["target", "zoom"]) : undefined,
    };
    deck.setProps({ initialViewState: viewState });
  }

  render();

  return {
    setMode(m) {
      if (m === mode) return;
      mode = m;
      viewState = homeView(m);
      deck.setProps({
        views: m === "2d" ? new OrthographicView({ id: "2d" }) : new OrbitView({ id: "3d" }),
        initialViewState: viewState,
      });
      render();
    },
    setFocus(f) {
      colours = fillColours(g, f); // new buffer, so deck re-uploads the colours
      render();
    },
    setLinks(from, to) {
      links = { from, to };
      render();
    },
    flyTo(i) {
      jump(pos(i), Math.max(viewState.zoom ?? 0, homeView(mode).zoom + 3));
    },
    flyToPoint(xy) {
      jump(xy, Math.max(viewState.zoom ?? 0, homeView(mode).zoom + 1.5));
    },
    setPerformance(on) {
      performance = on;
      deck.setProps({ useDevicePixels: !on });
      render();
    },
    destroy() {
      deck.finalize();
    },
  };
}
