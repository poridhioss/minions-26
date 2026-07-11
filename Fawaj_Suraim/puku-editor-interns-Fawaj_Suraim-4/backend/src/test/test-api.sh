#!/usr/bin/env bash
set -euo pipefail

BASE=${BASE:-http://localhost:3000}
KEY=${API_KEY:-}

H=(-H 'Content-Type: application/json')
[[ -n "$KEY" ]] && H+=(-H "x-api-key: $KEY")

echo "Submitting job..."
JOB=$(curl -sS -X POST "$BASE/jobs" "${H[@]}" \
  -d '{"image":"alpine","command":"echo phase2 && sleep 1 && echo done"}')
echo "$JOB"
JOB_ID=$(echo "$JOB" | python3 -c "import sys,json;print(json.load(sys.stdin)['jobId'])")

echo "Polling status..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  STATE=$(curl -sS "$BASE/jobs/$JOB_ID" "${H[@]}" | python3 -c "import sys,json;print(json.load(sys.stdin)['state'])")
  echo "  state=$STATE"
  [[ "$STATE" == "completed" || "$STATE" == "failed" ]] && break
  sleep 1
done

echo "Fetching logs..."
curl -sS "$BASE/jobs/$JOB_ID/logs" "${H[@]}"