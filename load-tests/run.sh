#!/bin/bash
set -e

# NOTE: run this script from the repo root, e.g.:
#   load-tests/run.sh 1 http://localhost:8000
# (paths below are relative to the repo root, not to this script's directory)

PHASE=${1:-1}
BASE_URL=${2:-http://localhost:8000}

# k6 may not be on PATH (fresh Windows install) — fall back to the default install location.
K6_BIN="${K6_BIN:-k6}"
if ! command -v "$K6_BIN" >/dev/null 2>&1; then
  if [ -x "/c/Program Files/k6/k6.exe" ]; then
    K6_BIN="/c/Program Files/k6/k6.exe"
  fi
fi

mkdir -p load-tests/reports

echo "🚀 Phase $PHASE 부하테스트 시작 → $BASE_URL"
"$K6_BIN" run \
  --env BASE_URL="$BASE_URL" \
  --out json="load-tests/reports/phase${PHASE}-raw.json" \
  "load-tests/phase${PHASE}.js"
