// Local Node benchmark config (not the Workers runtime): reads ../data/spike via fs.
import { defineConfig } from "vitest/config";

export default defineConfig({ test: { include: ["bench/**/*.bench.ts"], environment: "node" } });
