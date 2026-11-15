// Readers for the binary formats written by pipeline/index_format.py. Little-endian throughout.
// All arrays are views over the original buffer (no copies). Never JSON.parse a whole blob:
// meta records are decoded one at a time by byte offset.

export interface IndexView {
  n: number;
  dim: number;
  k: number;
  offsets: Uint32Array; // k+1 row offsets; rows are ordered by cluster
  scales: Float32Array; // per-row int8 scale
  vecs: Int8Array; // n*dim
}

export interface CentroidsView {
  k: number;
  dim: number;
  data: Float32Array; // k*dim, L2-normalised
}

export interface MetaView {
  n: number;
  offsets: Uint32Array; // n+1 byte offsets into blob
  blob: Uint8Array;
}

export interface MetaRecord {
  id: string;
  title: string;
  cluster: number;
  url: string;
  snippet: string;
}

const INDEX_MAGIC = "GXIDX1\0\0";
const CENTROIDS_MAGIC = "GXCEN1\0\0";
const META_MAGIC = "GXMETA1\0";
const decoder = new TextDecoder();

function checkMagic(buf: ArrayBuffer, magic: string, name: string): void {
  const head = new Uint8Array(buf, 0, Math.min(8, buf.byteLength));
  for (let i = 0; i < 8; i++) {
    if (head[i] !== magic.charCodeAt(i)) throw new Error(`bad magic: ${name}`);
  }
}

export function parseIndex(buf: ArrayBuffer): IndexView {
  checkMagic(buf, INDEX_MAGIC, "index");
  const view = new DataView(buf);
  const n = view.getUint32(8, true);
  const dim = view.getUint32(12, true);
  const k = view.getUint32(16, true);
  let pos = 20;
  const offsets = new Uint32Array(buf, pos, k + 1);
  pos += 4 * (k + 1);
  const scales = new Float32Array(buf, pos, n);
  pos += 4 * n;
  const vecs = new Int8Array(buf, pos, n * dim);
  return { n, dim, k, offsets, scales, vecs };
}

export function parseCentroids(buf: ArrayBuffer): CentroidsView {
  checkMagic(buf, CENTROIDS_MAGIC, "centroids");
  const view = new DataView(buf);
  const k = view.getUint32(8, true);
  const dim = view.getUint32(12, true);
  return { k, dim, data: new Float32Array(buf, 16, k * dim) };
}

export function parseMeta(buf: ArrayBuffer): MetaView {
  checkMagic(buf, META_MAGIC, "meta");
  const n = new DataView(buf).getUint32(8, true);
  const offsets = new Uint32Array(buf, 12, n + 1);
  const base = 12 + 4 * (n + 1);
  return { n, offsets, blob: new Uint8Array(buf, base) };
}

export function readRecord(meta: MetaView, row: number): MetaRecord {
  if (row < 0 || row >= meta.n) throw new RangeError(`meta row out of range: ${row}`);
  const bytes = meta.blob.subarray(meta.offsets[row], meta.offsets[row + 1]);
  return JSON.parse(decoder.decode(bytes)) as MetaRecord;
}
