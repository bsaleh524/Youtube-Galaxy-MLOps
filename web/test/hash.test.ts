import { describe, expect, it } from "vitest";
import { formatHash, parseHash } from "../src/hash";

describe("hash links", () => {
  it("parses a creator link", () => {
    expect(parseHash("#/creator/fandom_449281")).toEqual({ creator: "fandom_449281" });
  });

  it("parses a cluster link", () => {
    expect(parseHash("#/cluster/c071")).toEqual({ cluster: "c071" });
  });

  it("ignores anything else", () => {
    expect(parseHash("#/creator/")).toEqual({});
    expect(parseHash("#foo")).toEqual({});
    expect(parseHash("")).toEqual({});
  });

  it("decodes and round-trips", () => {
    expect(parseHash(formatHash({ creator: "fandom_372805" }))).toEqual({ creator: "fandom_372805" });
    expect(parseHash(formatHash({ cluster: "c001" }))).toEqual({ cluster: "c001" });
    expect(formatHash({})).toBe("");
  });
});
