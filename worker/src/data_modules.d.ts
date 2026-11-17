// Files matched by the "Data" rule in wrangler.jsonc are imported as ArrayBuffers.
declare module "*.bin" {
  const data: ArrayBuffer;
  export default data;
}
