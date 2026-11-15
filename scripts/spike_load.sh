#!/usr/bin/env bash
# Drive the deployed spike Worker to measure search latency, then read server-side CPU time.
# Usage: scripts/spike_load.sh https://galaxy-chat.<subdomain>.workers.dev [N=300]
set -euo pipefail
URL="${1:?usage: $0 WORKER_URL [N]}"
N="${2:-300}"

curl -fsS "$URL/spike/search?seed=0" > /dev/null   # warm-up (cold start loads the index)
cold=$(curl -o /dev/null -fsS -w '%{time_total}' "$URL/spike/search?seed=999999")
echo "one more request after warm-up: ${cold}s"

times=$(mktemp)
for i in $(seq 1 "$N"); do
  curl -o /dev/null -fsS -w '%{time_total}\n' "$URL/spike/search?seed=$i" >> "$times"
done
sort -n "$times" | awk '{a[NR]=$1} END {
  printf "client-side latency over %d requests: p50 %.1f ms, p95 %.1f ms, max %.1f ms\n",
    NR, a[int(NR*0.50)]*1000, a[int(NR*0.95)]*1000, a[NR]*1000 }'
rm -f "$times"

cat <<'TXT'

Client latency includes the network. Server-side CPU time per request:
  * Dashboard: Workers & Pages → galaxy-chat → Metrics → "CPU Time per execution" (quantiles).
  * GraphQL (docs/NOTES.md): POST https://api.cloudflare.com/client/v4/graphql, dataset
    workersInvocationsAdaptive, filter scriptName "galaxy-chat" and the time window of this run,
    fields quantiles { cpuTimeP50 cpuTimeP99 } (microseconds). Budget: 10 ms = 10000 µs.
TXT
