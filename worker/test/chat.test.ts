import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { AiQuotaError, type Embed } from "../src/chat";
import type { Env } from "../src/env";
import { readRecord } from "../src/format";
import { createHandler } from "../src/handler";
import { getIndex } from "../src/index_loader";
import { creatorVector } from "../src/names";
import { twoStageSearch } from "../src/search";

const SITE = "https://spookypharaoh.com";
const baseEnv = env as unknown as Env;

interface Body {
  status: string;
  error?: string;
  kind?: string;
  about?: { id: string; title: string } | null;
  results?: { id: string; title: string; cluster: unknown; score: number; url: string; snippet: string }[];
  index_version?: string;
  retry_after?: number;
}

async function rowOf(title: string): Promise<number> {
  const l = await getIndex(baseEnv);
  for (let r = 0; r < l.meta.n; r++) if (readRecord(l.meta, r).title === title) return r;
  throw new Error(`no fixture row titled ${title}`);
}

/** A handler whose embedder returns a fixed fixture row's vector (or throws), counting calls. */
async function setup(opts: { throws?: Error; extraEnv?: Partial<Env> } = {}) {
  const l = await getIndex(baseEnv);
  const vector = creatorVector(l.index, 42);
  let calls = 0;
  const fake: Embed = async () => {
    calls++;
    if (opts.throws) throw opts.throws;
    return vector;
  };
  const h = createHandler(getIndex, { embed: () => fake });
  const e = { ...baseEnv, ...opts.extraEnv } as Env;
  const send = async (init: { method?: string; origin?: string | null; body?: unknown; raw?: string; path?: string }) => {
    const headers: Record<string, string> = { "content-type": "application/json" };
    const origin = init.origin === undefined ? SITE : init.origin;
    if (origin) headers.Origin = origin;
    const method = init.method ?? "POST";
    const req = new Request(`http://w${init.path ?? "/api/chat"}`, {
      method,
      headers,
      body: method === "POST" ? (init.raw ?? JSON.stringify(init.body)) : undefined,
    });
    const res = await h.fetch!(req as Request<unknown, IncomingRequestCfProperties>, e, {} as ExecutionContext);
    return { res, body: (res.status === 204 ? {} : await res.json()) as Body };
  };
  return { send, vector, loaded: l, calls: () => calls };
}

describe("POST /api/chat — topic search", () => {
  it("returns up to 8 sorted results with the contract fields and CORS", async () => {
    const { send } = await setup();
    const { res, body } = await send({ body: { question: "anything" } });
    expect(res.status).toBe(200);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe(SITE);
    expect(body).toMatchObject({ status: "ok", mode: "search", kind: "topic", about: null, index_version: "fixture-1" });
    const r = body.results!;
    expect(r.length).toBeGreaterThan(0);
    expect(r.length).toBeLessThanOrEqual(8);
    expect(r.map((x) => x.score)).toEqual([...r.map((x) => x.score)].sort((a, b) => b - a));
    for (const x of r) {
      expect(Object.keys(x).sort()).toEqual(["cluster", "id", "score", "snippet", "title", "url"]);
      expect(Math.round(x.score * 1e4) / 1e4).toBe(x.score);
    }
  });

  it("is the same two-stage search the index gives directly", async () => {
    const { send, vector, loaded } = await setup();
    const { body } = await send({ body: { question: "anything" } });
    const direct = twoStageSearch(vector, loaded.centroids, loaded.index, { k: 8 }).map(
      (h) => readRecord(loaded.meta, h.row).id,
    );
    expect(body.results!.map((x) => x.id)).toEqual(direct);
  });
});

describe("POST /api/chat — name lookup", () => {
  it("answers 'like <title>' with that creator's neighbours and no AI call", async () => {
    const { send, loaded, calls } = await setup();
    const row = await rowOf("Synthetic 7");
    const id = readRecord(loaded.meta, row).id;
    const { res, body } = await send({ body: { question: "creators like Synthetic 7" } });
    expect(res.status).toBe(200);
    expect(body.kind).toBe("similar");
    expect(body.about).toEqual({ id, title: "Synthetic 7" });
    expect(body.results!.length).toBe(8);
    expect(body.results!.some((x) => x.id === id)).toBe(false);
    expect(calls()).toBe(0);
  });

  it("force_topic skips the name lookup", async () => {
    const { send, calls } = await setup();
    const { body } = await send({ body: { question: "creators like Synthetic 7", force_topic: true } });
    expect(body.kind).toBe("topic");
    expect(calls()).toBe(1);
  });

  it("still answers name questions while AI is resting", async () => {
    const { send } = await setup({ throws: new AiQuotaError("daily free allocation used") });
    const { res, body } = await send({ body: { question: "like Synthetic 7" } });
    expect(res.status).toBe(200);
    expect(body.kind).toBe("similar");
  });
});

describe("POST /api/chat — errors", () => {
  it("ask mode is not available yet", async () => {
    const { send } = await setup();
    const { res, body } = await send({ body: { question: "x", mode: "ask" } });
    expect(res.status).toBe(501);
    expect(body).toEqual({ status: "unavailable" });
  });

  it("rejects bad input with 400", async () => {
    const { send } = await setup();
    const cases: [Parameters<typeof send>[0], string][] = [
      [{ raw: "{not json" }, "bad_json"],
      [{ body: { question: "" } }, "empty"],
      [{ body: { question: "a".repeat(301) } }, "too_long"],
      [{ body: { question: "x", mode: "x" } }, "bad_mode"],
    ];
    for (const [init, error] of cases) {
      const { res, body } = await send(init);
      expect(res.status).toBe(400);
      expect(body).toEqual({ status: "bad_request", error });
    }
  });

  it("refuses a missing or foreign Origin", async () => {
    const { send } = await setup();
    for (const origin of [null, "https://evil.example"]) {
      const { res, body } = await send({ origin, body: { question: "x" } });
      expect(res.status).toBe(403);
      expect(body).toEqual({ status: "forbidden" });
    }
  });

  it("answers CORS preflight for allowed origins only", async () => {
    const { send } = await setup();
    const ok = await send({ method: "OPTIONS" });
    expect(ok.res.status).toBe(204);
    expect(ok.res.headers.get("Access-Control-Allow-Methods")).toBe("POST, OPTIONS");
    const bad = await send({ method: "OPTIONS", origin: "https://evil.example" });
    expect(bad.res.status).toBe(403);
  });

  it("maps AI quota errors to resting and other AI errors to error", async () => {
    const resting = await (await setup({ throws: new AiQuotaError("quota") })).send({ body: { question: "x" } });
    expect(resting.res.status).toBe(503);
    expect(resting.body).toEqual({ status: "resting" });
    const broken = await (await setup({ throws: new Error("boom") })).send({ body: { question: "x" } });
    expect(broken.res.status).toBe(502);
    expect(broken.body).toEqual({ status: "error" });
  });

  it("rate limits per IP and globally when the bindings say no", async () => {
    const no = { limit: async () => ({ success: false }) } as unknown as RateLimit;
    const yes = { limit: async () => ({ success: true }) } as unknown as RateLimit;
    for (const extraEnv of [{ PER_IP: no, GLOBAL: yes }, { PER_IP: yes, GLOBAL: no }]) {
      const { res, body } = await (await setup({ extraEnv })).send({ body: { question: "x" } });
      expect(res.status).toBe(429);
      expect(body).toEqual({ status: "rate_limited", retry_after: 60 });
    }
  });

  it("GET /api/chat is 405", async () => {
    const { send } = await setup();
    const { res } = await send({ method: "GET" });
    expect(res.status).toBe(405);
  });
});

describe("other routes", () => {
  it("spike routes are gone", async () => {
    const { send } = await setup();
    const { res } = await send({ method: "GET", path: "/spike/search?seed=1" });
    expect(res.status).toBe(404);
  });

  it("/health reports the index version", async () => {
    const { send } = await setup();
    const { body } = await send({ method: "GET", path: "/health" });
    expect(body).toEqual({ ok: true, index_version: "fixture-1" });
  });
});
