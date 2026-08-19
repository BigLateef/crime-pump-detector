#!/usr/bin/env bash
# Production start command for the FastAPI backend. Never uses --reload
# (that's dev-only and leaks source paths into behavior). Reads PORT from
# the environment since most PaaS platforms (Railway, Render, Fly) assign
# it dynamically rather than letting you hardcode 8000.
set -euo pipefail

: "${PORT:=8000}"
# Render sets WEB_CONCURRENCY based on the actual CPU/RAM sized to your
# instance plan - respect it if present instead of guessing a worker
# count ourselves. UVICORN_WORKERS remains available as an explicit
# override for platforms that don't set WEB_CONCURRENCY. Falls back to 1
# (not 2) because running multiple full worker processes - each with its
# own DB connection pool - on a small instance is what caused the boot
# crash loop this replaces: workers were getting killed almost instantly
# after spawning, consistent with hitting the instance's memory ceiling.
: "${UVICORN_WORKERS:=${WEB_CONCURRENCY:-1}}"

if [ "${APP_ENV:-development}" = "development" ]; then
  echo "WARNING: APP_ENV=development - refusing to start in production mode." >&2
  echo "         Set APP_ENV=production in your deployment platform's env vars." >&2
  exit 1
fi

if [ "${SECRET_KEY:-}" = "change-me-to-a-64-char-random-string" ] || [ -z "${SECRET_KEY:-}" ]; then
  echo "FATAL: SECRET_KEY is unset or still the example placeholder." >&2
  exit 1
fi
if [ "${SCAN_TRIGGER_SECRET:-}" = "change-me-to-a-random-string" ] || [ -z "${SCAN_TRIGGER_SECRET:-}" ]; then
  echo "FATAL: SCAN_TRIGGER_SECRET is unset or still the example placeholder." >&2
  exit 1
fi
if [ "${DISCORD_WEBHOOK_ENCRYPTION_KEY:-}" = "change-me-32-byte-key" ] || [ -z "${DISCORD_WEBHOOK_ENCRYPTION_KEY:-}" ]; then
  echo "FATAL: DISCORD_WEBHOOK_ENCRYPTION_KEY is unset or still the example placeholder." >&2
  exit 1
fi

# Migrations run HERE, not only via the Procfile's separate `release`
# step - many platforms (most non-Heroku ones) don't support a distinct
# release phase and would otherwise silently start the app against a
# stale schema. `alembic upgrade head` is idempotent (a no-op if already
# current), so running it on every boot is safe and cheap. If it fails,
# the app must NOT start against a schema it doesn't match - `set -e`
# above means a non-zero exit here already aborts the script, but this
# is spelled out explicitly so it's never accidentally "improved" into a
# background/best-effort call.
echo "Running database migrations (alembic upgrade head)..."
if ! alembic upgrade head; then
  echo "FATAL: migrations failed - refusing to start the app against a schema that might not match the code." >&2
  exit 1
fi

echo "Starting backend on port $PORT with $UVICORN_WORKERS worker(s)..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers "$UVICORN_WORKERS"
