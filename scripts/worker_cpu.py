"""Read server-side CPU time quantiles for the deployed Worker from the GraphQL Analytics API.

    uv run python scripts/worker_cpu.py --since 2026-11-17T01:30:00Z [--until ...] [--script galaxy-chat]

Needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN (with Account Analytics: Read) in .env.
Analytics lag a few minutes behind real time. Values are reported in milliseconds (the API returns µs).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

QUERY = """
query ($account: string!, $script: string!, $since: Time!, $until: Time!) {
  viewer {
    accounts(filter: {accountTag: $account}) {
      workersInvocationsAdaptive(
        limit: 50
        filter: {scriptName: $script, datetime_geq: $since, datetime_leq: $until}
      ) {
        dimensions { status datetimeMinute }
        sum { requests errors }
        quantiles { cpuTimeP50 cpuTimeP90 cpuTimeP99 cpuTimeP999 wallTimeP50 wallTimeP99 }
      }
    }
  }
}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    ap.add_argument("--script", default="galaxy-chat")
    a = ap.parse_args()
    load_dotenv()
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID"), os.getenv("CLOUDFLARE_API_TOKEN")
    if not account or not token:
        print("missing CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN in .env", file=sys.stderr)
        return 2
    r = requests.post(
        "https://api.cloudflare.com/client/v4/graphql",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "query": QUERY,
            "variables": {"account": account, "script": a.script, "since": a.since, "until": a.until},
        },
        timeout=30,
    )
    body = r.json()
    if body.get("errors"):
        print(json.dumps(body["errors"], indent=2), file=sys.stderr)
        return 1
    rows = body["data"]["viewer"]["accounts"][0]["workersInvocationsAdaptive"]
    if not rows:
        print("no invocations in that window yet (analytics lag a few minutes)")
        return 1
    rows.sort(key=lambda r: r["dimensions"]["datetimeMinute"])
    for row in rows:
        q = {k: round(v / 1000, 3) for k, v in row["quantiles"].items()}
        print(f"{row['dimensions']['datetimeMinute']} status={row['dimensions']['status']} requests={row['sum']['requests']} errors={row['sum']['errors']}")
        print("  ms:", json.dumps(q))
    return 0


if __name__ == "__main__":
    sys.exit(main())
