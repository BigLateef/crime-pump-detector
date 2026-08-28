#!/usr/bin/env bash
# Two things:
#  1. A local smoke test against a running backend (health, readiness,
#     public endpoints) - needs the API to already be up.
#  2. A safe live-provider check - only actually calls DexScreener/GoPlus
#     if DATA_PROVIDER_MODE=live AND the relevant *_ENABLED flag AND
#     network access are all present. Otherwise it explicitly reports
#     "PENDING", never a fabricated pass.
set -uo pipefail

API_BASE="${API_BASE_URL:-http://localhost:8000}"
RESULTS=()
record() { RESULTS+=("$1: $2"); }

echo "=== 1. Local API smoke test against $API_BASE ==="

check_endpoint() {
  local path="$1" name="$2"
  if command -v python3 >/dev/null 2>&1; then
    if python3 -c "
import urllib.request, sys
try:
    resp = urllib.request.urlopen('$API_BASE$path', timeout=5)
    sys.exit(0 if resp.status == 200 else 1)
except Exception as e:
    print(f'  error: {e}')
    sys.exit(1)
"; then
      echo "PASS: $name ($path)"
      record "$name" "PASS"
      return 0
    else
      echo "FAIL: $name ($path) - is the API running? Try: docker compose up -d api"
      record "$name" "FAIL"
      return 1
    fi
  else
    echo "SKIP: no python3 available"
    record "$name" "SKIPPED - no python3"
    return 2
  fi
}

check_endpoint "/health" "Liveness check"
check_endpoint "/health/ready" "Readiness check (DB + Redis)"
check_endpoint "/docs" "OpenAPI docs (debug mode only)"

echo ""
echo "=== 2. Live data provider verification ==="

if [ -f .env ]; then
  set -a; source .env; set +a
fi

MODE="${DATA_PROVIDER_MODE:-mock}"
DEX_ENABLED="${DEXSCREENER_ENABLED:-false}"
GOPLUS_ENABLED_VAR="${GOPLUS_ENABLED:-false}"
GECKO_ENABLED="${GECKOTERMINAL_ENABLED:-false}"

if [ "$MODE" != "live" ]; then
  echo "PENDING: DATA_PROVIDER_MODE=$MODE, not 'live'. Live adapter verification"
  echo "         was not attempted. This is expected and correct for local dev -"
  echo "         it is NOT a failure, just not yet checked."
  record "DexScreener live check" "PENDING - provider mode is not 'live'"
  record "GoPlus live check" "PENDING - provider mode is not 'live'"
  record "GeckoTerminal live check" "PENDING - provider mode is not 'live'"
else
  echo "DATA_PROVIDER_MODE=live - attempting real provider checks."
  echo "(Never printing any credential value, even if one is configured.)"

  if [ "$DEX_ENABLED" = "true" ]; then
    if python3 -c "
import urllib.request, sys
try:
    urllib.request.urlopen('${DEXSCREENER_BASE_URL:-https://api.dexscreener.com/latest/dex}/tokens/So11111111111111111111111111111111111111112', timeout=10)
    sys.exit(0)
except Exception as e:
    print(f'  error: {type(e).__name__}')
    sys.exit(1)
"; then
      echo "PASS: DexScreener reachable"
      record "DexScreener live check" "PASS"
    else
      echo "FAIL: DexScreener not reachable (network blocked, or provider down)"
      record "DexScreener live check" "FAIL"
    fi
  else
    echo "PENDING: DEXSCREENER_ENABLED=false"
    record "DexScreener live check" "PENDING - not enabled"
  fi

  if [ "$GOPLUS_ENABLED_VAR" = "true" ]; then
    if python3 -c "
import urllib.request, sys
try:
    urllib.request.urlopen('${GOPLUS_BASE_URL:-https://api.gopluslabs.io/api/v1/token_security}/1', timeout=10)
    sys.exit(0)
except Exception as e:
    print(f'  error: {type(e).__name__}')
    sys.exit(1)
"; then
      echo "PASS: GoPlus reachable"
      record "GoPlus live check" "PASS"
    else
      echo "FAIL: GoPlus not reachable (network blocked, or provider down)"
      record "GoPlus live check" "FAIL"
    fi
  else
    echo "PENDING: GOPLUS_ENABLED=false"
    record "GoPlus live check" "PENDING - not enabled"
  fi

  if [ "$GECKO_ENABLED" = "true" ]; then
    if python3 -c "
import urllib.request, sys
try:
    urllib.request.urlopen('${GECKOTERMINAL_BASE_URL:-https://api.geckoterminal.com/api/v2}/networks/eth/new_pools', timeout=10)
    sys.exit(0)
except Exception as e:
    print(f'  error: {type(e).__name__}')
    sys.exit(1)
"; then
      echo "PASS: GeckoTerminal reachable"
      record "GeckoTerminal live check" "PASS"
    else
      echo "FAIL: GeckoTerminal not reachable (network blocked, or provider down)"
      record "GeckoTerminal live check" "FAIL"
    fi
  else
    echo "PENDING: GECKOTERMINAL_ENABLED=false"
    record "GeckoTerminal live check" "PENDING - not enabled"
  fi
fi

echo ""
echo "=== SUMMARY ==="
for r in "${RESULTS[@]}"; do echo "$r"; done
echo ""
echo "Reminder: a PENDING result is not a pass. Do not report live verification"
echo "as complete unless every relevant line above says PASS."
