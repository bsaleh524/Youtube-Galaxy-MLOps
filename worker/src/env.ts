// Bindings and vars available to the Worker.
export interface Env {
  ASSETS: Fetcher; // static assets: index.bin, centroids.bin, meta.bin, index_manifest.json
  AI: Ai; // Workers AI (query embeddings)
}
