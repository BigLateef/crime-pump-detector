# Quickstart

Exact commands for every step of local setup and verification. All paths
are relative to the project root unless noted. Run `chmod +x scripts/*.sh`
once if the scripts aren't already executable.

## 1. One-time setup

```bash
./scripts/setup.sh
```

Does: creates a Python venv, installs backend deps, copies `.env.example`
→ `.env`, installs frontend deps (`npm install`), copies
`frontend/.env.local.example` → `frontend/.env.local`. Stops immediately
and reports the exact failure if `pip install` or `npm install` can't
reach their registries.

Equivalent manual commands, if you'd rather run them yourself:

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Frontend
cd frontend
npm install
cp .env.local.example .env.local
cd ..
```

## 2. Start PostgreSQL and Redis

```bash
docker compose up -d postgres redis
```

Wait for both to report healthy:

```bash
docker compose ps
```

Or without Docker, point `.env`'s `DATABASE_URL` / `REDIS_URL` at any
Postgres 16+ / Redis 7+ instance you already have running.

Verify either way:

```bash
./scripts/check_services.sh
```

## 3. Run database migrations

```bash
source .venv/bin/activate
alembic upgrade head
```

This applies `alembic/versions/0001_initial_schema.py` — generated
directly from `app/models/*.py` (not hand-retyped) since no live database
was available to run `alembic revision --autogenerate` when this project
was built. **Verify it against a real Postgres before trusting it in
production**: `alembic upgrade head` followed by a manual check that all
12 tables exist with the expected columns.

Bootstrap the first admin account (required before any invite can exist):

```bash
python -m app.seed
```

## 4. Start the backend

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Or via Docker Compose (includes Postgres + Redis):

```bash
docker compose up api
```

## 5. Start the frontend

```bash
cd frontend
npm run dev
```

Or via Docker Compose:

```bash
docker compose up frontend
```

Visit `http://localhost:3000`.

## 6. Run pure-logic tests (no DB/network required)

```bash
source .venv/bin/activate
pytest app/tests/test_scoring.py app/tests/test_security_rules.py \
       app/tests/test_backtesting.py app/tests/test_backtesting_validation.py \
       app/tests/test_importer_parsing.py app/tests/test_loader.py -v
```

## 7. Run integration tests (needs real PostgreSQL)

```bash
./scripts/check_services.sh   # confirm Postgres/Redis are up first
pytest app/tests/test_loader_integration.py -v
```

## 8. Run adapter tests (mocked — no real network calls)

```bash
pytest app/tests/test_adapters.py -v
```

## 9. Run the database importer tests

Covered by the integration suite in step 7 (`test_loader_integration.py`
exercises dataset creation, snapshot insertion, and grouping against a
real database). A dedicated `import_dataset()` write-path test does not
exist yet — see `README.md`'s remaining-limitations section.

## 10. Frontend type checking

```bash
cd frontend
npx tsc --noEmit
```

## 11. Frontend linting

```bash
cd frontend
npm run lint
```

## 12. Next.js production build

```bash
cd frontend
npm run build
```

## 13. Run a local API smoke test

```bash
# with the API already running (step 4)
./scripts/smoke_test.sh
```

Checks `/health`, `/health/ready`, `/docs`, and — only if
`DATA_PROVIDER_MODE=live` in `.env` — attempts real DexScreener/GoPlus
connectivity checks. Otherwise reports those as `PENDING`, never a
fabricated pass.

## Run everything at once

```bash
./scripts/setup.sh
docker compose up -d postgres redis
./scripts/check_services.sh
alembic upgrade head
docker compose up -d api frontend
./scripts/test_backend.sh
./scripts/test_frontend.sh
./scripts/smoke_test.sh
```
