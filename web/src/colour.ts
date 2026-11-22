import type { Galaxy } from "./data";

/** Alpha for points outside the current focus. */
export const DIM_ALPHA = 40;

export interface Focus {
  cluster: number;
  keep?: number[];
}

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

/** n×4 RGBA bytes: cluster colour per node; with a focus, everything outside it is dimmed. */
export function fillColours(g: Galaxy, focus: Focus | null, out?: Uint8Array): Uint8Array {
  const n = g.ids.length;
  const c = out ?? new Uint8Array(n * 4);
  const rgb = g.clusters.map((k) => hexToRgb(k.colour));
  for (let i = 0; i < n; i++) {
    const [r, gr, b] = rgb[g.cluster[i]];
    c[i * 4] = r;
    c[i * 4 + 1] = gr;
    c[i * 4 + 2] = b;
    c[i * 4 + 3] = !focus || g.cluster[i] === focus.cluster ? 255 : DIM_ALPHA;
  }
  for (const i of focus?.keep ?? []) c[i * 4 + 3] = 255;
  return c;
}
