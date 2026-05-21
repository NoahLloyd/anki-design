#!/usr/bin/env bash
# snap.sh - request a Qt grab() screenshot from the running dev Anki.
#
# Usage:
#   scripts/snap.sh <out.png> <title-substring|"main"> [--open-addcards] [--fill-sample]
#
# Writes a JSON request into .context/screenshot-requests/; the Anki Design
# dev-watch thread picks it up, grabs the matching top-level widget on the
# Qt main thread, saves the PNG, then deletes the request file.
set -euo pipefail
OUT="${1:?missing out.png path}"
TITLE="${2:?missing title substring (or \"main\")}"
shift 2 || true
OPEN_FLAG="false"
FILL_FLAG="false"
COG_FLAG="false"
HOVER_FLAG="false"
TYPE_FLAG="false"
EMBED_FLAG="false"
CLOSE_FLAG="false"
TRIGGER_KEY=""
MW_WIDTH="0"
for arg in "$@"; do
  case "$arg" in
    --open-addcards) OPEN_FLAG="true" ;;
    --fill-sample) FILL_FLAG="true" ;;
    --click-cog) COG_FLAG="true" ;;
    --hover-add) HOVER_FLAG="true" ;;
    --click-type) TYPE_FLAG="true" ;;
    --embed-add) OPEN_FLAG="true"; EMBED_FLAG="true" ;;
    --close-after) CLOSE_FLAG="true" ;;
    --trigger=*) TRIGGER_KEY="${arg#--trigger=}" ;;
    --width=*) MW_WIDTH="${arg#--width=}" ;;
    --hover-add-btn) HOVER_FLAG="true" ;;
    --test-add) TEST_ADD="true" ;;
  esac
done
TEST_ADD="${TEST_ADD:-false}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$REPO/.context/screenshot-requests"
mkdir -p "$DIR" "$(dirname "$OUT")"
ABS_OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

# Stable filename ⇒ unique stamp per request
REQ="$DIR/req-$(date +%s%N).json"
cat > "$REQ" <<JSON
{
  "out": "${ABS_OUT}",
  "title": "${TITLE}",
  "open_addcards": ${OPEN_FLAG},
  "fill_sample": ${FILL_FLAG},
  "click_cog": ${COG_FLAG},
  "click_type": ${TYPE_FLAG},
  "embed_add": ${EMBED_FLAG},
  "close_after": ${CLOSE_FLAG},
  "trigger_shortcut": "${TRIGGER_KEY}",
  "mw_width": ${MW_WIDTH},
  "hover_add": ${HOVER_FLAG},
  "test_add": ${TEST_ADD},
  "delay_ms": 6500
}
JSON

# Wait up to 30s for the addon to write the PNG (and delete the request).
# Editor.html loads async via WebEngine so we allow ~1s render delay inside.
for _ in $(seq 1 300); do
  if [[ -f "$ABS_OUT" ]] && [[ ! -f "$REQ" ]]; then
    echo "wrote $ABS_OUT"
    exit 0
  fi
  if [[ -f "$ABS_OUT.err" ]]; then
    echo "screenshot error: $(cat "$ABS_OUT.err")" >&2
    rm -f "$ABS_OUT.err"
    exit 1
  fi
  sleep 0.1
done
echo "timeout waiting for screenshot (req=$REQ)" >&2
exit 1
