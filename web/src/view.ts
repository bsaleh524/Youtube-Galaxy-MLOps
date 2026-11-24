export interface Bounds {
  min: number[];
  max: number[];
}

export interface FitView {
  target: [number, number, number];
  zoom: number;
}

export function bounds(pos: Float32Array, dims: 2 | 3): Bounds {
  const min = Array(dims).fill(Infinity);
  const max = Array(dims).fill(-Infinity);
  for (let i = 0; i < pos.length; i += dims) {
    for (let d = 0; d < dims; d++) {
      const v = pos[i + d];
      if (v < min[d]) min[d] = v;
      if (v > max[d]) max[d] = v;
    }
  }
  return { min, max };
}

/** Centre of the box, and a zoom (log2 pixels per unit) that fits it in width×height. */
export function fitView(b: Bounds, width: number, height: number, pad = 0.9): FitView {
  const span = (d: number) => Math.max(b.max[d] - b.min[d], 1e-6);
  const mid = (d: number) => (b.min[d] + b.max[d]) / 2;
  return {
    target: [mid(0), mid(1), b.min.length > 2 ? mid(2) : 0],
    zoom: Math.log2(pad * Math.min(width / span(0), height / span(1))),
  };
}
