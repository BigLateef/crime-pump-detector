#!/usr/bin/env bash
# One-time project setup: backend venv + deps, frontend node_modules,
# .env from template. Stops on the first real error; reports network/
# registry blocks explicitly instead of hanging or failing silently.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== 1. Backend: Python environment ==="
if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: python3 not found on PATH."
  exit 1
fi
PY_VERSION=$(python3 --version)
echo "Using: $PY_VERSION"

if [ ! -d ".venv" ]; then
  echo "Creating virtualenv at .venv ..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing backend dependencies from requirements.txt ..."
if ! pip install -r requirements.txt; then
  echo "FAIL: pip install failed. This usually means no network access to PyPI"
  echo "      (this exact command failed with a registry/network error above)."
  echo "      Re-run this script somewhere with network access to PyPI."
  exit 1
fi
echo "PASS: backend dependencies installed."

echo ""
echo "=== 2. Backend: .env ==="
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit SECRET_KEY, DISCORD_WEBHOOK_ENCRYPTION_KEY,"
  echo "and SCAN_TRIGGER_SECRET before doing anything beyond local dev."
else
  echo ".env already exists — leaving it as-is."
fi

echo ""
echo "=== 3. Frontend: Node dependencies ==="
if ! command -v npm >/dev/null 2>&1; then
  echo "FAIL: npm not found on PATH."
  exit 1
fi
cd frontend
if [ ! -f ".env.local" ]; then
  cp .env.local.example .env.local
  echo "Created frontend/.env.local from .env.local.example."
fi
echo "Installing frontend dependencies from package.json ..."
if ! npm install; then
  echo "FAIL: npm install failed. This usually means no network access to the"
  echo "      npm registry (this exact command failed with a registry/network"
  echo "      error above). Re-run this script somewhere with network access."
  exit 1
fi
echo "PASS: frontend dependencies installed. package-lock.json is now generated"
echo "      for the first time by this run, if it didn't already exist."
cd "$ROOT_DIR"

echo ""
echo "=== Setup complete ==="
echo "Next: ./scripts/check_services.sh, then docker compose up, then ./scripts/smoke_test.sh"
