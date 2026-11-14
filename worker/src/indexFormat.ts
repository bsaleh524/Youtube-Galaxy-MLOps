// Reader for the binary index files written by pipeline/index_format.py. Keep in sync with it.
// Everything is a typed-array view over the raw buffers: no copies, no JSON.parse of large blobs.

export interface LoadedIndex {
  n: number;
  dim: number;
  nClusters: number;
  offsets: Uint32Array; // nClusters + 1 row offsets (rows are cluster-ordered)
  scales: Float32Array; // per-row dequantisation scale
  data: Int8Array; // n * dim
  centroids: Float32Array; // nClusters * dim, L2-normalised
  metaOffsets: Uint32Array; // n + 1 byte offsets into metaBytes
  metaBytes: Uint8Array;
}

export interface MetaRecord {
  id: string;
  title: string;
  cluster: number;
  url: string;
  bio: string;
}

const FORMAT_VERSION = 1;

function magic(buf: ArrayBuffer, expected: string): void {
  const got = new TextDecoder().decode(new Uint8Array(buf, 0, 4));
  if (got !== expected) throw new Error(`bad magic: expected ${expected}, got ${got}`);
}

export function parseIndex(indexBuf: ArrayBuffer, centroidBuf: ArrayBuffer, metaBuf: ArrayBuffer): LoadedIndex {
  magic(indexBuf, "GXI1");
  const h = new DataView(indexBuf);
  const n = h.getUint32(4, true);
  const dim = h.getUint32(8, true);
  const nClusters = h.getUint32(12, true);
  const ver = h.getUint32(16, true);
  if (ver !== FORMAT_VERSION) throw new Error(`unsupported index format ${ver}`);

  let pos = 32;
  const offsets = new Uint32Array(indexBuf, pos, nClusters + 1);
  pos += 4 * (nClusters + 1);
  const scales = new Float32Array(indexBuf, pos, n);
  pos += 4 * n;
  const data = new Int8Array(indexBuf, pos, n * dim);

  magic(centroidBuf, "GXC1");
  const ch = new DataView(centroidBuf);
  if (ch.getUint32(4, true) !== nClusters || ch.getUint32(8, true) !== dim) {
    throw new Error("centroids do not match index");
  }
  const centroids = new Float32Array(centroidBuf, 16, nClusters * dim);

  magic(metaBuf, "GXM1");
  const mn = new DataView(metaBuf).getUint32(4, true);
  if (mn !== n) throw new Error("meta does not match index");
  const metaOffsets = new Uint32Array(metaBuf, 16, n + 1);
  const metaBytes = new Uint8Array(metaBuf, 16 + 4 * (n + 1));

  return { n, dim, nClusters, offsets, scales, data, centroids, metaOffsets, metaBytes };
}

const decoder = new TextDecoder();

/** Decode one record. Only called for the handful of top-k rows. */
export function readMeta(idx: LoadedIndex, row: number): MetaRecord {
  const a = idx.metaOffsets[row];
  const b = idx.metaOffsets[row + 1];
  return JSON.parse(decoder.decode(idx.metaBytes.subarray(a, b))) as MetaRecord;
}
