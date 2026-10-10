#!/usr/bin/env bash
# Smoke test after a deploy: the web app serves the SPA, and the API behind it
# answers its health check through the internal /api path.
#   ./infra/smoke-test.sh https://ca-codelyst-web-staging.<region>.azurecontainerapps.io
set -euo pipefail

URL="${1:?usage: $0 <web url>}"

check() {
  local path="$1" expect="$2"
  for attempt in $(seq 1 20); do   # up to ~5 minutes for new revisions / cold starts
    if body="$(curl -fsS --max-time 20 "${URL}${path}")" && grep -q "$expect" <<<"$body"; then
      echo "ok   ${path}"
      return 0
    fi
    echo "wait ${path} (attempt ${attempt}/20)"
    sleep 15
  done
  echo "FAIL ${path}: expected '${expect}'" >&2
  return 1
}

check "/"        '<div id="root">'
check "/healthz" '"status":"ok"'
