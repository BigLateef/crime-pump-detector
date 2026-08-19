#!/usr/bin/env bash
# Runs everything backend-side that CAN run, and reports each command's
# pass/fail/skip explicitly. Never claims a check passed without actually
# running it.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RESULTS=()
record() { RESULTS+=("$1: $2"); }

echo "=== 1. Python compilation check (all backend files) ==="
if find app -name "*.py" -print0 | xargs -0 python3 -m py_compile; then
  echo "PASS"
  record "py_compile" "PASS"
else
  echo "FAIL"
  record "py_compile" "FAIL"
fi

echo ""
echo "=== 2. Pure-logic tests (no DB/network required) ==="
if [ -d ".venv" ]; then source .venv/bin/activate; fi
if command -v pytest >/dev/null 2>&1; then
  if pytest app/tests/test_scoring.py app/tests/test_security_rules.py \
            app/tests/test_backtesting.py app/tests/test_backtesting_validation.py \
            app/tests/test_importer_parsing.py app/tests/test_loader.py -v; then
    echo "PASS"
    record "pytest (pure-logic)" "PASS"
  else
    echo "FAIL"
    record "pytest (pure-logic)" "FAIL"
  fi
else
  echo "SKIP: pytest not installed. Run ./scripts/setup.sh first."
  record "pytest (pure-logic)" "SKIPPED - pytest not installed"
fi

echo ""
echo "=== 3. Security primitive tests (needs argon2-cffi, pyjwt) ==="
if command -v pytest >/dev/null 2>&1; then
  if pytest app/tests/test_security_primitives.py -v; then
    echo "PASS"
    record "pytest (security primitives)" "PASS"
  else
    echo "FAIL"
    record "pytest (security primitives)" "FAIL"
  fi
else
  echo "SKIP: pytest not installed."
  record "pytest (security primitives)" "SKIPPED - pytest not installed"
fi

echo ""
echo "=== 4. Adapter tests (httpx.MockTransport - no real network) ==="
if command -v pytest >/dev/null 2>&1; then
  if pytest app/tests/test_adapters.py -v; then
    echo "PASS"
    record "pytest (adapters, mocked)" "PASS"
  else
    echo "FAIL"
    record "pytest (adapters, mocked)" "FAIL"
  fi
else
  echo "SKIP: pytest not installed."
  record "pytest (adapters, mocked)" "SKIPPED - pytest not installed"
fi

echo ""
echo "=== 5. Database-dependent tests (needs real PostgreSQL) ==="
if ./scripts/check_services.sh >/tmp/services_check.log 2>&1; then
  if command -v pytest >/dev/null 2>&1; then
    if pytest app/tests/test_loader_integration.py -v; then
      echo "PASS"
      record "pytest (DB integration)" "PASS"
    else
      echo "FAIL"
      record "pytest (DB integration)" "FAIL"
    fi
  else
    echo "SKIP: pytest not installed."
    record "pytest (DB integration)" "SKIPPED - pytest not installed"
  fi
else
  echo "SKIP: PostgreSQL/Redis not reachable - see /tmp/services_check.log"
  record "pytest (DB integration)" "SKIPPED - services unreachable"
fi

echo ""
echo "=== 6. Alembic migration check (needs real PostgreSQL) ==="
if ./scripts/check_services.sh >/tmp/services_check.log 2>&1; then
  if command -v alembic >/dev/null 2>&1; then
    if alembic upgrade head; then
      echo "PASS"
      record "alembic upgrade head" "PASS"
    else
      echo "FAIL"
      record "alembic upgrade head" "FAIL"
    fi
  else
    echo "SKIP: alembic not installed."
    record "alembic upgrade head" "SKIPPED - alembic not installed"
  fi
else
  echo "SKIP: PostgreSQL not reachable."
  record "alembic upgrade head" "SKIPPED - postgres unreachable"
fi

echo ""
echo "=== SUMMARY ==="
for r in "${RESULTS[@]}"; do echo "$r"; done
