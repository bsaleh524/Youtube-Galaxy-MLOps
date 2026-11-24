#!/usr/bin/env bash
# Load the deployed chat Worker with name-lookup questions ("channels like X"), which use no Workers AI
# quota, to measure search CPU time (issue #1). Then read server-side CPU with scripts/worker_cpu.py.
# Usage: scripts/chat_load.sh https://galaxy-chat.<subdomain>.workers.dev [N=300]
# Note: the per-IP rate limit (10/min) answers most of these with 429 quickly, which still exercises the
# Worker but not the search; space requests out (SLEEP=6) to measure searches only.
set -euo pipefail
URL="${1:?usage: $0 WORKER_URL [N]}"
N="${2:-300}"
SLEEP="${SLEEP:-0}"
NAMES=("Markiplier" "MrBeast" "PewDiePie" "Vsauce" "Kurzgesagt" "Dream" "Technoblade" "Smosh" "Dude Perfect"
       "Linus Tech Tips" "CoryxKenshin" "Jacksepticeye" "TommyInnit" "Mark Rober" "Veritasium" "Tom Scott"
       "Ludwig" "Ninja" "James Charles" "Marques Brownlee")

ask() {
  curl -o /dev/null -sS -w '%{http_code} %{time_total}\n' -X POST "$URL/api/chat" \
    -H 'Origin: https://spookypharaoh.com' -H 'content-type: application/json' \
    -d "{\"question\":\"channels like $1\"}"
}

ask "Markiplier" > /dev/null   # warm-up
start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
out=$(mktemp)
for i in $(seq 1 "$N"); do
  ask "${NAMES[$((i % ${#NAMES[@]}))]}" >> "$out"
  sleep "$SLEEP"
done
awk '{codes[$1]++} END {for (c in codes) printf "HTTP %s: %d\n", c, codes[c]}' "$out"
awk '$1 == 200 {print $2}' "$out" | sort -n | awk '{a[NR]=$1} END { if (NR) printf "client latency over %d answered: p50 %.0f ms, p95 %.0f ms\n", NR, a[int(NR*0.5)+0]*1000, a[int(NR*0.95)+0]*1000 }'
rm -f "$out"
echo "started $start — in a few minutes: uv run python scripts/worker_cpu.py --since $start"
