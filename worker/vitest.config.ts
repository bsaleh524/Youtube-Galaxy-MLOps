import { defineConfig } from "vitest/config";

// `npm test` runs unit tests; `npm run bench` runs the CPU benchmark against worker/assets (synthetic or real index).
export default defineConfig({
  test: { include: process.env.BENCH ? ["bench/**/*.test.ts"] : ["test/**/*.test.ts"] },
});
