// Files matched by the "Data" rule in wrangler.jsonc are imported as ArrayBuffers.
declare module "*.bin" {
  const data: ArrayBuffer;
  export default data;
}

// Bundled by wrangler's built-in JSON loader. Declared here (no resolveJsonModule) so the
// typecheck passes when worker/assets/ is empty, as in CI.
declare module "*/index_manifest.json" {
  const manifest: { version: string; n: number; dim: number; k: number; model: string };
  export default manifest;
}
