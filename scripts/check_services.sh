#!/usr/bin/env bash
# Reports whether PostgreSQL and Redis are reachable, using whatever the
# project's .env says, without assuming either is running. Never fails
# the whole script just because one service is down — it reports both,
# then exits non-zero only if something it needs to check with is
# missing entirely (e.g. no python3).
set -uo pipefail

echo "=== Service availability check ==="

if [ -f .env ]; then
  set -a; source .env; set +a
else
  echo "WARN: .env not found — using defaults from .env.example for this check"
  set -a; source .env.example; set +a
fi

DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
REDIS_HOST_CHECK="${REDIS_HOST:-localhost}"
REDIS_PORT_CHECK="${REDIS_PORT:-6379}"

check_tcp() {
  local host="$1" port="$2" name="$3"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$host" "$port" <<'PYEOF'
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect((host, port))
    sys.exit(0)
except Exception as e:
    print(f"  reason: {e}")
    sys.exit(1)
finally:
    s.close()
PYEOF
    if [ $? -eq 0 ]; then
      echo "PASS: $name reachable at $host:$port"
      return 0
    else
      echo "FAIL: $name NOT reachable at $host:$port"
      return 1
    fi
  else
    echo "SKIP: no python3 available to check $name"
    return 2
  fi
}

pg_ok=0
redis_ok=0
check_tcp "$DB_HOST" "$DB_PORT" "PostgreSQL" || pg_ok=1
check_tcp "$REDIS_HOST_CHECK" "$REDIS_PORT_CHECK" "Redis" || redis_ok=1

echo ""
if [ $pg_ok -ne 0 ] || [ $redis_ok -ne 0 ]; then
  echo "One or more services are unreachable. If using Docker Compose, run:"
  echo "  docker compose up -d postgres redis"
  echo "and wait for both healthchecks to pass before re-running this script."
  exit 1
fi

echo "All checked services reachable."
exit 0
