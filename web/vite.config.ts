import { defineConfig } from "vite";

// SITE_BASE_PATH must match the folder the site is uploaded to (default /galaxy/).
// In dev, data comes from web/.devdata (`make web-data`); a build never copies data into dist.
export default defineConfig(({ command }) => ({
  base: process.env.SITE_BASE_PATH ?? "/galaxy/",
  publicDir: command === "serve" ? ".devdata" : "public",
}));
