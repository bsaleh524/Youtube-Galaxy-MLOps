import { defineConfig } from "vite";

// SITE_BASE_PATH must match the folder the site is uploaded to (default /galaxy/).
export default defineConfig({
  base: process.env.SITE_BASE_PATH ?? "/galaxy/",
});
