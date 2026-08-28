# Crime Pump Early Detector

Private, invite-only research and alerting platform for early-stage
low-cap token momentum. **Research alerts only — not financial advice.
No automated trading. No market manipulation.**

## Quick start (local dev)

```bash
cp .env.example .env
# edit .env: set real values for SECRET_KEY, DISCORD_WEBHOOK_ENCRYPTION_KEY,
# SCAN_TRIGGER_SECRET before doing anything beyond local dry-run testing

docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed          # creates the first admin
docker compose exec api pytest app/tests -v
curl http://localhost:8000/health/ready
```

Then, as the admin, call `POST /admin/invites` (bearer token from
`POST /auth/login`) to generate the first invite for a friend.

## What's real vs. what's a documented gap

| Area | Status |
|---|---|
| Auth, invites, atomic redemption | Real, tested (pure-logic tests pass; DB-backed paths untested — no network in build sandbox) |
| Security filtering rules | Real, tested against GoPlus's documented schema |
| Scoring engine | Real, tested, matches the point breakdown in the spec exactly |
| DexScreener adapter | Real code, **untested against the live API** — no network access when built. Also missing a "new pairs" endpoint on the free tier (documented in the adapter) |
| GoPlus adapter | Real code, untested against live API |
| Mock/dry-run adapter | Real, fully functional, used by default (`DRY_RUN=true`) |
| Holder/wallet-level data (unique buyers, wallet clustering, deployer tracking) | **Not wired to a real source.** No free API provides this reliably across chains — every option researched (Birdeye, Nansen, Arkham, Moralis) is paid. Schema and scoring inputs exist; a real adapter does not |
| Discord delivery + encryption | Real. Delivery-row creation and sending are now wired into the scan-triggered flow (previously a real gap — nothing created `DiscordDelivery` rows at all, found and fixed in a security-hardening pass), with a DB-level unique constraint preventing duplicates. Still untested against a live webhook |
| Paper trading | Real, fully functional, pure simulation |
| Backtesting framework | Real methodology and evaluator. **Contains no real historical data** — populating `HistoricalCase` records for $COAI/$SIREN/$M/$LAB and 20 comparable tokens requires a real historical data pipeline, which this build does not have network access to create. Fabricating numbers for real tickers would be actively misleading, so it wasn't done |
| Social/narrative monitoring | Not built — `ENABLE_SOCIAL_ANALYSIS=false` by default per the low-cost-mode requirement, and no adapter exists yet |
| AI-assisted analysis layer | Not built — `ENABLE_AI_ANALYSIS=false` by default; deterministic scoring/security run first per Section 13 |
| Frontend dashboard (18 pages) | **Built this round** — Next.js 14 (App Router) + TypeScript + Tailwind, in `/frontend`. Never run through `npm install`/`npm run build` (no network access in the build sandbox) — every file was manually bracket/syntax-reviewed but not compiled. Consumes the API endpoints above; several panels (holder distribution, wallet flow, worker/scan metrics) show an honest empty state because the backend doesn't populate that data yet — see the frontend's own README note below |
| Google/Discord/Wallet login | Not built — schema and auth module are structured so they can be added without reworking the User model |

## Deployment checklist (before enabling `ENABLE_LIVE_DATA=true`)

1. Generate real secrets — `SECRET_KEY`, `DISCORD_WEBHOOK_ENCRYPTION_KEY`,
   `SCAN_TRIGGER_SECRET` — none of the `.env.example` values are safe to
   use as-is.
2. Confirm the DexScreener and GoPlus adapters actually work against the
   live APIs (they were never exercised against a network in this build).
3. Run the full test suite with real Postgres/Redis.
4. Point an external scheduler (cron-job.org or similar) at
   `POST /internal/scan` with the `X-Scan-Secret` header — do not run an
   always-on worker loop, per the cost-control requirements.
5. Verify `/health/ready` reports `ok` for both database and redis.
6. Confirm invite codes are never appearing in logs — grep any deployed
   log output for a sample generated code as a smoke test.
7. Review `LOW_COST_MODE` and the `MAX_*` / `*_INTERVAL_SECONDS` env vars
   against actual API rate limits before raising them.

## Known security-review items for a human reviewer

- `require_admin` / `get_current_user` gate every admin and per-user
  route — verified by grep across all API files (16/16 admin routes
  carry `Depends(require_admin)`) during a prior security-hardening
  pass. Re-verify after any future route additions.
- **Fixed**: CORS previously allowed all methods/headers (`["*"]"`) —
  now restricted to the exact methods/headers this API uses (`GET`,
  `POST`, `PATCH`, `DELETE`; `Authorization`, `Content-Type`,
  `X-Scan-Secret`). `ALLOWED_ORIGINS` still must be set to the exact
  deployed frontend origin(s) in production, never `*`.
- Rate limiting uses a fixed-window counter in Redis, not a sliding
  window — acceptable for launch, but bursty at window boundaries. As
  of the security-hardening pass, it fails **closed** (rejects with 503)
  by default on Redis outage for every auth/invite/admin/upload/scanner
  endpoint, and fails open only where explicitly opted in for low-risk
  reads (none currently opt in).
- The security-filtering module fails closed when GoPlus data is
  unavailable — confirm that's the desired behavior under real load
  (it will suppress alerts during any GoPlus outage). This is
  intentional, not a bug — see `app/security/rules.py`.
- **Fixed**: Discord delivery duplicate prevention previously relied on
  an application-level check only (a real TOCTOU race under
  concurrency). Now enforced by a real database `UniqueConstraint` on
  `discord_deliveries(signal_alert_id, discord_integration_id)`
  (migration `0002`), with `IntegrityError` handled gracefully.
- **Fixed**: production startup previously only ran migrations via a
  Procfile `release` step that most non-Heroku platforms don't support.
  `scripts/start_prod.sh` now runs `alembic upgrade head` itself before
  starting the server, on every boot.
- **Fixed**: no frontend-side admin guard existed beyond hiding nav
  links. `app/(dashboard)/admin/layout.tsx` now shows a clean
  "Admins only" state for a non-admin hitting an admin URL directly.
- **Fixed**: a 401 that survived a token-refresh attempt previously left
  the user on a dead session with no redirect. `lib/api.ts` /
  `lib/auth-context.tsx` now redirect to `/login` with the original
  destination preserved, with open-redirect and loop prevention.

## Project layout

See `HANDOFF.md` for the full file map and phase-by-phase history.

## Live adapters + backtesting pipeline (this phase)

**Live data adapters** — `app/adapters/`:
- `DataStatus` enum (`VERIFIED`/`CACHED`/`DEMO`/`UNAVAILABLE`/`FAILED`) is now on every `TokenSnapshot` and `SecurityCheckResult` — nothing is ever silently treated as safe/live just because a field is `None`.
- `DexScreenerAdapter` and `GoPlusAdapter` go through `app/adapters/provider_utils.py`: Redis cache (`DATA_CACHE_TTL_SECONDS`), retry with exponential backoff on timeout/429/5xx (`DATA_MAX_RETRIES`), and a fixed request timeout (`DATA_REQUEST_TIMEOUT_SECONDS`). All requests are server-side only — the frontend never calls these providers directly.
- `MockChainAdapter` now labels every generated name/symbol `DEMO...` and always returns `status=DEMO`.
- New env vars: `DATA_PROVIDER_MODE`, `DEXSCREENER_ENABLED`, `GOPLUS_ENABLED`, `DEXSCREENER_BASE_URL`, `GOPLUS_BASE_URL`, `DATA_CACHE_TTL_SECONDS`, `DATA_REQUEST_TIMEOUT_SECONDS`, `DATA_MAX_RETRIES`.
- `app/adapters/factory.py` picks adapters off `DATA_PROVIDER_MODE` + the per-provider `*_ENABLED` flags — live mode requires both, so flipping the mode alone can't silently turn on a provider nobody configured.

**Backtesting data pipeline** — `app/backtesting/` + `app/models/historical_snapshot.py`:
- `schema.py` is the single source of truth for the 28 required/optional fields (token_address, chain, snapshot_timestamp, minutes_before_major_move, all the volume/holder/security fields, source, data_quality, outcome, etc.) — the CSV/JSON templates in `/data_templates/` are generated from it, so they can't drift out of sync.
- `validation.py`: required-field checks, per-chain address format validation, negative-value rejection, duplicate detection (within a file), future-data-leakage rejection (`snapshot_timestamp` must be strictly before `major_move_timestamp`), and non-blocking "suspicious value" warnings (e.g. unique_buyers > buy_count).
- `importer.py`: parses CSV/JSON, re-checks duplicates against the database (not just within the uploaded file), and writes `HistoricalDataset` + `HistoricalSnapshot` rows. DEMO uploads force every row's `data_quality` to `DEMO` regardless of file content.
- `loader.py`: converts DB snapshots into the pure `HistoricalCase`/`Checkpoint` objects the existing evaluation framework (`framework.py`, built in the previous phase) already consumes. `require_verified=True` by default — refuses to build a "real" case set from anything but `VERIFIED` rows.
- `/data_templates/historical_snapshot_template.csv` and `sample_demo_dataset.json` — the sample is 21 rows of **clearly fictional** data (three synthetic cases: runner, flat, rugged) that I ran through the real validator and confirmed passes clean. It is not, and must never be presented as, real token data.

**Backtesting API** — `app/api/backtesting.py`: `/admin/backtesting/validate` (no DB write), `/import`, `/datasets`, `/datasets/{id}`, `/run`, `/export`. All admin-only.

**Frontend additions**: `/admin/data-sources` (provider status), `/admin/backtesting/datasets` (upload/validate/import/history), `/admin/backtesting/run` (configure + results), a `DataQualityBadge` and `DataStatusBadge` reused on the token detail page for per-metric freshness.

**Tests actually executed in this sandbox** (no DB/network dependency): 28 pure-logic tests pass — `test_scoring.py` (5), `test_security_rules.py` (5), `test_backtesting.py` (3), `test_backtesting_validation.py` (11, new), `test_importer_parsing.py` (4, new). `test_adapters.py` (new, `httpx.MockTransport`-based) and `test_security_primitives.py` are syntax-checked only — they need `httpx`/`argon2-cffi`/`pyjwt`, which couldn't be installed offline.

### Remaining limitations from this phase

- DexScreener/GoPlus adapters have still never been called against the real live APIs — only against mock transports in tests that themselves haven't executed (no `httpx` installed offline).
- `import_dataset()` (the actual DB write path) has no executed test — it needs a real async Postgres session. `test_importer_parsing.py` only covers the pure parsing functions.
- No frontend page yet for "dataset quality" as its own view beyond what's shown inline on the datasets list — quality currently means the validation-error/row counts already visible there, not a deeper per-field quality score.
- The scoring-input mapping in `loader.py` (`_snapshot_to_scoring_input`) can't populate `price_change_1h_pct` or `volume_accel_ratio` from a single snapshot row — those need the *previous* checkpoint's data, which isn't wired up yet.
- Linting and full `next build`/`tsc` type-checking still haven't run anywhere — only manual bracket-balance checks and Python `py_compile`.

## Verification checklist — what needs what

| Check | Needs network | Needs PostgreSQL | Needs Redis | Needs API credentials |
|---|---|---|---|---|
| `py_compile` (all backend files) | No | No | No | No |
| Pure-logic tests (`test_scoring.py`, `test_security_rules.py`, `test_backtesting.py`, `test_backtesting_validation.py`, `test_importer_parsing.py`, `test_loader.py`) | No | No | No | No |
| `test_security_primitives.py` | No (once installed) | No | No | No |
| `test_adapters.py` (MockTransport) | No | No | No | No |
| `test_loader_integration.py` | No | **Yes** | No | No |
| `alembic upgrade head` | No | **Yes** | No | No |
| Frontend bracket-balance check | No | No | No | No |
| `npm install` | **Yes** (npm registry) | No | No | No |
| `tsc --noEmit`, `npm run lint`, `npm run build` | No (once `npm install` succeeds) | No | No | No |
| `scripts/check_services.sh` | No | **Yes** (to pass) | **Yes** (to pass) | No |
| `scripts/smoke_test.sh` local checks | No | No | No | No |
| `scripts/smoke_test.sh` live-provider checks | **Yes** | No | No | No (both DexScreener and GoPlus are keyless — see below) |

DexScreener and GoPlus are both free/keyless APIs, so "needs API
credentials" is technically never true for either — but live checks still
need real network egress, which this build environment doesn't have. If a
provider requiring a key is added later, credentials must be set via
environment variables only and are never logged (`app/core/logging.py`
never receives raw request/response bodies from adapter code).

## DEMO vs VERIFIED data

Every historical snapshot row and every live token snapshot carries an
explicit `data_quality` / `status` value — `VERIFIED`, `DEMO`,
`ESTIMATED`, or `UNAVAILABLE` (snapshots) / `VERIFIED`, `CACHED`, `DEMO`,
`UNAVAILABLE`, `FAILED` (live adapter results). Rules enforced in code,
not just convention:

- `app/backtesting/loader.py`'s `load_cases(require_verified=True)`
  (the default) refuses to build a backtest case set from anything but
  `VERIFIED` rows — raises `DatasetIntegrityError` instead of silently
  including demo data.
- `app/backtesting/importer.py` force-tags every row `DEMO` when the
  upload itself is marked `DEMO`, regardless of what the file's
  `data_quality` column says — a demo file can't accidentally get counted
  as verified through a copy-paste mistake in the CSV.
- The frontend's `DataQualityBadge` and `DataStatusBadge` components
  render a visibly different label (`DEMO DATA`, `VERIFIED`, `CACHED`,
  etc.) everywhere data quality is shown, so it's never ambiguous in the
  UI either.

**To import real, verified historical data:** upload a CSV or JSON file
matching `data_templates/historical_snapshot_template.csv` through
`/admin/backtesting/validate` (dry-run — no DB write) and then
`/admin/backtesting/import` with `data_quality: "VERIFIED"`. Every
VERIFIED row must carry a real `source` — the import is rejected outright
if no row has one. See `data_templates/sample_demo_dataset.json` for the
field shapes (that file itself is fictional demo data, clearly labeled,
and must never be imported as VERIFIED).

## Low-cost mode

`LOW_COST_MODE=true` by default in `.env.example`. What it controls:

- `SCANNER_INTERVAL_SECONDS` / `HIGH_ACTIVITY_SCAN_INTERVAL_SECONDS` /
  `LOW_ACTIVITY_SCAN_INTERVAL_SECONDS`: adaptive scan frequency — active
  tokens get scanned more often, quiet ones less, per the architecture in
  `app/workers/scanner.py`.
- `MAX_TOKENS_PER_BATCH` / `MAX_API_REQUESTS_PER_MINUTE`: caps work per
  scan invocation so a single run can't blow through a provider's rate
  limit or run unbounded.
- `ALERT_COOLDOWN_MINUTES`: per-token Redis cooldown key prevents
  re-alerting the same token every scan pass.
- `ENABLE_SOCIAL_ANALYSIS` / `ENABLE_AI_ANALYSIS`: both `false` by
  default — deterministic scoring and security filtering (cheap) always
  run first; social/AI analysis (expensive) is opt-in and never a
  prerequisite for a Discord alert to fire.
- No always-on worker process exists anywhere in this codebase. The
  scanner is invoked via `POST /internal/scan`, meant to be pinged by an
  external scheduler (cron-job.org or similar) — see
  `app/api/internal.py`. This phase added no new workers, per the
  instruction to preserve that architecture.
- If a scan is skipped or delayed (e.g. resource limits), the priority
  order is: keep auth/dashboard access working → keep core on-chain
  monitoring at reduced frequency → keep Discord alerts flowing → reduce
  social analysis first → reduce optional AI explanations second. This
  mirrors the original spec's degradation order; it isn't separately
  enforced in code today (no resource-limit detection exists yet) — worth
  flagging as a gap rather than claiming it's automatic.

### Worker health and data freshness

`GET /health/ready` reports `dry_run` and `low_cost_mode` status
alongside DB/Redis connectivity. `GET /data-sources/status` reports which
provider is live/mock/disabled. Every `TokenMetric` and
`HistoricalSnapshot` row carries its own `data_status` /
`data_quality`, so freshness and provenance are visible per-record, not
just at the system level — see the `DataStatusBadge` on the token detail
page and the dataset quality page. A dedicated scan-run-level metrics
endpoint (workers processed, queue depth, jobs skipped) does **not**
exist yet — `/admin/health` in the frontend shows an honest empty state
for that section rather than fake numbers.

## Deployment

Backend: build the root `Dockerfile`, run behind a real ASGI process
manager (not `--reload`), set real secrets (`SECRET_KEY`,
`DISCORD_WEBHOOK_ENCRYPTION_KEY`, `SCAN_TRIGGER_SECRET`), point
`DATABASE_URL`/`REDIS_URL` at managed Postgres/Redis, run
`alembic upgrade head` as a release step, and point an external scheduler
at `POST /internal/scan` with the `X-Scan-Secret` header.

Frontend: build the `frontend/Dockerfile`, set
`NEXT_PUBLIC_API_BASE_URL` to the deployed backend's public URL, run
`npm run build && npm run start` (not `next dev`) in the container.

Neither Dockerfile has been built or run anywhere with this phase's
changes — see the final report in the conversation for exactly what was
and wasn't executed.
