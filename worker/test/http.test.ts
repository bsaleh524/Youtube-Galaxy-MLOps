import { describe, expect, it } from "vitest";
import { allowedOrigin, corsHeaders, MAX_QUESTION, parseChatRequest, parseOrigins } from "../src/http";

const SITE = "https://spookypharaoh.com";
const req = (origin?: string) =>
  new Request("http://w/api/chat", { method: "POST", headers: origin ? { Origin: origin } : {} });

describe("parseOrigins", () => {
  it("splits on commas, trims and drops empties", () => {
    expect(parseOrigins(` ${SITE} , https://www.spookypharaoh.com,,`)).toEqual(
      new Set([SITE, "https://www.spookypharaoh.com"]),
    );
  });
  it("is empty for undefined", () => {
    expect(parseOrigins(undefined).size).toBe(0);
  });
});

describe("allowedOrigin", () => {
  const allowed = new Set([SITE]);
  it("returns an allowed origin", () => {
    expect(allowedOrigin(req(SITE), allowed)).toBe(SITE);
  });
  it("is null for a missing or other origin", () => {
    expect(allowedOrigin(req(), allowed)).toBeNull();
    expect(allowedOrigin(req("https://evil.example"), allowed)).toBeNull();
  });
});

describe("corsHeaders", () => {
  it("has exactly the allow-list headers", () => {
    expect(corsHeaders(SITE)).toEqual({
      "Access-Control-Allow-Origin": SITE,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "content-type",
      "Access-Control-Max-Age": "86400",
      Vary: "Origin",
    });
  });
});

describe("parseChatRequest", () => {
  it("trims and defaults mode to search", () => {
    expect(parseChatRequest({ question: "  cooking  " })).toEqual({ ok: true, question: "cooking", mode: "search" });
  });
  it("passes ask through", () => {
    expect(parseChatRequest({ question: "x", mode: "ask" })).toEqual({ ok: true, question: "x", mode: "ask" });
  });
  it("rejects empty, whitespace, non-string and null", () => {
    for (const body of [{ question: "" }, { question: "   " }, { question: 5 }, null, {}]) {
      expect(parseChatRequest(body)).toEqual({ ok: false, error: "empty" });
    }
  });
  it("allows exactly MAX_QUESTION characters and rejects one more", () => {
    expect(MAX_QUESTION).toBe(300);
    expect(parseChatRequest({ question: "a".repeat(300) }).ok).toBe(true);
    expect(parseChatRequest({ question: "a".repeat(301) })).toEqual({ ok: false, error: "too_long" });
  });
  it("rejects an unknown mode", () => {
    expect(parseChatRequest({ question: "x", mode: "chat" })).toEqual({ ok: false, error: "bad_mode" });
  });
});
