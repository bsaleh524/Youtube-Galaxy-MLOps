"""Phase 1: measure per-request CPU time of the deployed spike Worker on the free plan.

Run from the repo root after `make worker-deploy` (with the synthetic index in worker/assets):

    uv run python scripts/spike_measure.py https://galaxy-chat.<subdomain>.workers.dev

It starts `wrangler tail --format json`, sends warm-up + measured requests, and prints CPU/wall percentiles
per route from the tail events. If the tail events carry no CPU fields, read p50/p99 CPU from the
dashboard instead: Workers & Pages -> galaxy-chat -> Metrics (or Observability).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

OUT = Path("data/spike_tail.jsonl")
QUESTIONS = ["minecraft let's play", "makeup tutorials", "true crime documentaries", "speedrunners", "video essays"]


def find(obj, key):
    """First value for `key` anywhere in a nested JSON object."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find(v, key)
            if r is not None:
                return r
    return None


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    node = 'source "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 && nvm use --silent >/dev/null 2>&1; '
    tail = subprocess.Popen(
        ["bash", "-c", node + "cd worker && exec npx wrangler tail --format json"],
        stdout=open(OUT, "w"),
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=os.environ,
    )
    time.sleep(8)  # let the tail connect

    s = requests.Session()
    t = time.time()
    first = s.get(f"{base}/health").json()
    print(f"first /health ({'cold' if first.get('cold') else 'warm'} isolate): {time.time() - t:.2f}s wall", first)
    for i in range(300):
        s.get(f"{base}/spike/search", params={"seed": i})
    for i in range(60):
        s.get(f"{base}/spike/search", params={"seed": i, "mode": "brute"})
    chat_ok = 0
    for q in QUESTIONS * 4:
        r = s.post(f"{base}/api/chat", json={"question": q})
        chat_ok += r.ok
    print(f"/api/chat ok: {chat_ok}/{len(QUESTIONS) * 4}")
    time.sleep(10)  # let events flush
    os.killpg(tail.pid, signal.SIGTERM)

    groups = defaultdict(lambda: {"cpu": [], "wall": []})
    for line in OUT.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = find(ev, "url") or ""
        route = url.split("://", 1)[-1].split("/", 1)[-1].split("?")[0]
        if "mode=brute" in url:
            route += " (brute)"
        cpu, wall = find(ev, "cpuTime"), find(ev, "wallTime")
        if cpu is not None:
            groups[route]["cpu"].append(cpu)
        if wall is not None:
            groups[route]["wall"].append(wall)

    if not groups:
        print(f"No cpuTime/wallTime fields in tail events ({OUT}). Use the dashboard metrics instead.")
        return 1
    for route, g in sorted(groups.items()):
        c = g["cpu"]
        print(
            f"/{route:24s} n={len(c):4d}  cpu p50={pct(c, 50)} p95={pct(c, 95)} p99={pct(c, 99)} max={max(c) if c else None} ms"
            f"  wall p50={pct(g['wall'], 50)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
