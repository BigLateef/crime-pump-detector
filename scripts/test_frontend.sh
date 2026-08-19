#!/usr/bin/env bash
# Runs the frontend toolchain end to end. Does NOT claim success for any
# step it didn't actually execute.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend"

RESULTS=()
record() { RESULTS+=("$1: $2"); }

echo "=== 1. npm install ==="
if [ ! -d "node_modules" ]; then
  if npm install; then
    echo "PASS"
    record "npm install" "PASS"
  else
    echo "FAIL: could not install frontend dependencies (likely no network access"
    echo "      to the npm registry - see the error above for the exact cause)."
    record "npm install" "FAIL"
    echo ""
    echo "=== SUMMARY ==="
    for r in "${RESULTS[@]}"; do echo "$r"; done
    echo "Cannot continue past this point without node_modules."
    exit 1
  fi
else
  echo "SKIP: node_modules already present."
  record "npm install" "SKIPPED - already installed"
fi

echo ""
echo "=== 2. TypeScript type checking ==="
if npx tsc --noEmit; then
  echo "PASS"
  record "tsc --noEmit" "PASS"
else
  echo "FAIL"
  record "tsc --noEmit" "FAIL"
fi

echo ""
echo "=== 3. ESLint ==="
if npm run lint; then
  echo "PASS"
  record "eslint (next lint)" "PASS"
else
  echo "FAIL"
  record "eslint (next lint)" "FAIL"
fi

echo ""
echo "=== 4. Next.js production build ==="
if npm run build; then
  echo "PASS"
  record "next build" "PASS"
else
  echo "FAIL"
  record "next build" "FAIL"
fi

echo ""
echo "=== 5. Frontend tests ==="
echo "SKIP: no test runner (jest/vitest) is configured in package.json yet."
record "frontend tests" "SKIPPED - no test runner configured"

echo ""
echo "=== SUMMARY ==="
for r in "${RESULTS[@]}"; do echo "$r"; done
