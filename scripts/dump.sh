#!/usr/bin/env bash
# Dump the HTML of the web view in a Qt window matching the title substring.
set -euo pipefail
OUT="${1:?missing out.html}"
TITLE="${2:?missing title substring}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$REPO/.context/dump-requests"
mkdir -p "$DIR" "$(dirname "$OUT")"
ABS_OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
REQ="$DIR/req-$(date +%s%N).json"
cat > "$REQ" <<JSON
{"out":"${ABS_OUT}","title":"${TITLE}"}
JSON
for _ in $(seq 1 200); do
  if [[ -f "$ABS_OUT" ]] && [[ ! -f "$REQ" ]]; then
    echo "wrote $ABS_OUT"; exit 0
  fi
  sleep 0.1
done
echo "timeout" >&2; exit 1
