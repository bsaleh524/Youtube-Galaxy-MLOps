import { describe, expect, it } from "vitest";
import { askChat, chatUrl } from "../src/chat";
import type { Manifest } from "../src/data";

const URL_ = "https://w.example/api/chat";

function replying(status: number, body: string) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fn = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(body, { status, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  return { fn, calls };
}

const manifest = (chat?: { url: string }) =>
  ({ version: "v", built_at: "", creators: 1, clusters: 1, attribution: {}, chat }) as unknown as Manifest;

describe("askChat", () => {
  it("POSTs the question as JSON and returns the parsed body", async () => {
    const ok = { status: "ok", mode: "search", kind: "topic", about: null, results: [], index_version: "v" };
    const { fn, calls } = replying(200, JSON.stringify(ok));
    expect(await askChat(fn, URL_, "cooking")).toEqual(ok);
    expect(calls[0].url).toBe(URL_);
    expect(calls[0].init?.method).toBe("POST");
    expect(new Headers(calls[0].init?.headers).get("content-type")).toBe("application/json");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ question: "cooking" });
  });

  it("sends force_topic when asked", async () => {
    const { fn, calls } = replying(200, "{}");
    await askChat(fn, URL_, "dream", { forceTopic: true });
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ question: "dream", force_topic: true });
  });

  it("passes error bodies through", async () => {
    for (const [code, body] of [
      [400, { status: "bad_request", error: "too_long" }],
      [429, { status: "rate_limited", retry_after: 60 }],
      [501, { status: "unavailable" }],
      [503, { status: "resting" }],
    ] as const) {
      expect(await askChat(replying(code, JSON.stringify(body)).fn, URL_, "q")).toEqual(body);
    }
  });

  it("is offline on a network error, a non-JSON reply or a timeout", async () => {
    const thrown = (async () => {
      throw new TypeError("network");
    }) as unknown as typeof fetch;
    expect(await askChat(thrown, URL_, "q")).toEqual({ status: "offline" });
    expect(await askChat(replying(502, "<html>bad gateway</html>").fn, URL_, "q")).toEqual({ status: "offline" });
    let aborted = false;
    const hang = ((_: RequestInfo | URL, init?: RequestInit) =>
      new Promise((_, reject) => {
        init?.signal?.addEventListener("abort", () => {
          aborted = true;
          reject(new DOMException("aborted", "AbortError"));
        });
      })) as typeof fetch;
    expect(await askChat(hang, URL_, "q", { timeoutMs: 20 })).toEqual({ status: "offline" });
    expect(aborted).toBe(true);
  });
});

describe("chatUrl", () => {
  it("prefers the dev override, then the manifest, else null", () => {
    expect(chatUrl(manifest({ url: URL_ }), "http://localhost:8787/api/chat")).toBe("http://localhost:8787/api/chat");
    expect(chatUrl(manifest({ url: URL_ }), undefined)).toBe(URL_);
    expect(chatUrl(manifest(), undefined)).toBeNull();
    expect(chatUrl(manifest(), "")).toBeNull();
  });
});
