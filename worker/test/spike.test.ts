import { env, exports } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import type { Env } from "../src/env";
import { getIndex } from "../src/index_loader";

describe("spike endpoints", () => {
  it("/spike/search?seed=1 returns 10 hits sorted by score", async () => {
    const res = await exports.default.fetch("http://example.com/spike/search?seed=1");
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      hits: { id: string; title: string; score: number }[];
      probed: number;
      candidates: number;
    };
    expect(body.hits).toHaveLength(10);
    const scores = body.hits.map((h) => h.score);
    expect(scores).toEqual([...scores].sort((a, b) => b - a));
    expect(body.hits.every((h) => typeof h.id === "string" && typeof h.title === "string")).toBe(true);
    expect(body.probed).toBeGreaterThan(0);
    expect(body.candidates).toBeGreaterThan(0);
  });

  it("is deterministic for the same seed", async () => {
    const a = await (await exports.default.fetch("http://example.com/spike/search?seed=42")).json();
    const b = await (await exports.default.fetch("http://example.com/spike/search?seed=42")).json();
    expect(a).toEqual(b);
  });

  it("missing or bad seed returns 400", async () => {
    for (const q of ["", "?seed=", "?seed=abc"]) {
      const res = await exports.default.fetch(`http://example.com/spike/search${q}`);
      expect(res.status).toBe(400);
      expect(await res.json()).toEqual({ error: "bad_request" });
    }
  });

  it("getIndex caches the loaded index per isolate", async () => {
    const a = await getIndex(env as unknown as Env);
    const b = await getIndex(env as unknown as Env);
    expect(a).toBe(b);
    expect(a.index.n).toBe(600);
  });

  it("/health reports the index manifest version", async () => {
    const res = await exports.default.fetch("http://example.com/health");
    expect(await res.json()).toEqual({ ok: true, index_version: "fixture-1" });
  });
});
