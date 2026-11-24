// Per-isolate sliding-window limiter. Backs up the Rate Limiting binding, which went live
// without ever refusing (2026-11-24: 30 rapid requests from one IP, all 200). An isolate only
// sees its own traffic, so this is a floor, not an exact count — enough to stop one client
// from burning the daily Workers AI quota.
export class WindowLimiter {
  private hits = new Map<string, number[]>();

  constructor(
    private readonly limit: number,
    private readonly periodMs: number,
    private readonly maxKeys = 10_000,
    private readonly now: () => number = Date.now,
  ) {}

  allow(key: string): boolean {
    const t = this.now();
    const recent = (this.hits.get(key) ?? []).filter((h) => t - h < this.periodMs);
    if (recent.length >= this.limit) {
      this.hits.set(key, recent);
      return false;
    }
    recent.push(t);
    this.hits.delete(key); // re-insert so Map order is least-recently-used first
    this.hits.set(key, recent);
    while (this.hits.size > this.maxKeys) this.hits.delete(this.hits.keys().next().value as string);
    return true;
  }

  size(): number {
    return this.hits.size;
  }
}
