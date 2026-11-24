import { describe, expect, it } from "vitest";
import { WindowLimiter } from "../src/limiter";

describe("WindowLimiter", () => {
  it("allows `limit` hits per key per window, then refuses until the window slides", () => {
    let t = 0;
    const lim = new WindowLimiter(3, 60_000, 100, () => t);
    expect([lim.allow("a"), lim.allow("a"), lim.allow("a"), lim.allow("a")]).toEqual([true, true, true, false]);
    expect(lim.allow("b")).toBe(true); // keys are independent
    t = 59_999;
    expect(lim.allow("a")).toBe(false);
    t = 60_000; // the first three hits are now a full window old
    expect(lim.allow("a")).toBe(true);
  });

  it("refused hits do not extend the wait", () => {
    let t = 0;
    const lim = new WindowLimiter(1, 1000, 100, () => t);
    expect(lim.allow("a")).toBe(true);
    t = 500;
    expect(lim.allow("a")).toBe(false);
    t = 1000;
    expect(lim.allow("a")).toBe(true);
  });

  it("never tracks more than maxKeys keys", () => {
    let t = 0;
    const lim = new WindowLimiter(1, 60_000, 2, () => t);
    lim.allow("a");
    lim.allow("b");
    lim.allow("c"); // over the cap: old keys are forgotten rather than growing memory
    expect(lim.size()).toBeLessThanOrEqual(2);
    t = 1;
    expect(lim.allow("c")).toBe(false);
  });
});
