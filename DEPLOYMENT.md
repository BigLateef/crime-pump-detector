# Deployment Guide

Architecture:
- **Frontend**: Next.js, deployed to **Vercel** from the `frontend/`
  subdirectory only — Vercel never touches the Python backend code.
- **Backend**: FastAPI, deployed to **Render** as a Docker web service
  built from the repository root (the root `Dockerfile`).
- **Database**: managed PostgreSQL (Neon or Supabase).
- **Cache/locks/rate-limiting**: managed Redis (Upstash).
- **Scanning**: an external scheduler (cron-job.org) calls a protected
  backend endpoint on an interval — no worker process runs inside Vercel,
  and no separate worker service is needed on Render either; the backend
  web service itself handles scan requests when the scheduler calls in.

None of this has been deployed or tested against real infrastructure —
this document describes how to, and the final report in the conversation
lists exactly what was and wasn't verified.

## 0. Push to GitHub first

Both Vercel and most backend platforms deploy from a GitHub repo, not a
local directory upload — do this before steps 1–3.

```bash
cd crime-pump-detector
git init                                  # skip if already a git repo
git add .
git status                                # sanity check: confirm no .env,
                                           # only .env.example files, appear
git commit -m "Initial commit"
gh repo create your-org/crime-pump-detector --private --source=. --push
# or, without the GitHub CLI:
#   git remote add origin git@github.com:your-org/crime-pump-detector.git
#   git branch -M main
#   git push -u origin main
```

Before pushing, confirm nothing secret is staged:

```bash
git status --porcelain --ignored | grep -E "^\?\?.*\.env$|^\?\?.*\.env\.[a-z]+$"
```

This should print nothing (real `.env` files are ignored — only the
`.example` templates are ever tracked). If it prints anything, stop and
fix `.gitignore` before pushing — see `.gitignore`'s "Secrets" section
and re-run `git status --porcelain --ignored` to confirm the fix worked
before proceeding.

## 1. Deploy the frontend to Vercel

**Vercel dashboard (recommended — deploys from GitHub on every push):**

1. Import the GitHub repo into Vercel.
2. Project Settings → General:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Next.js (auto-detected once Root Directory is set)
   - **Build Command**: `next build` (Vercel's default for Next.js — no override needed)
   - **Install Command**: `npm install` (default — no override needed)
   - **Output Directory**: `.next` (default — no override needed)
3. Deploy.

Setting **Root Directory: frontend** is the critical step — without it,
Vercel tries to build from the repo root and fails immediately (there's
no `package.json` there, only the Python backend).

**CLI alternative** (one-off deploys without connecting GitHub):

```bash
cd frontend
npx vercel link      # first time only - connects this dir to a Vercel project
npx vercel --prod     # deploy to production
```

No `vercel.json` is required for this project (no custom routes,
redirects, or build overrides needed) — Vercel auto-detects Next.js from
`frontend/package.json` once Root Directory is set correctly.

## 2. Configure Vercel environment variables

Project Settings → Environment Variables. Set `NEXT_PUBLIC_API_URL` for
each of the three scopes separately, using `frontend/.env.production.example`
and `frontend/.env.preview.example` as templates:

| Scope | NEXT_PUBLIC_API_URL |
|---|---|
| Production | `https://api.yourdomain.com` |
| Preview | `https://staging-api.yourdomain.com` (a separate staging backend — never point preview builds at production) |
| Development | `http://localhost:8000` (only relevant if you run `vercel dev`; most local dev uses `npm run dev` directly, reading `frontend/.env.local`) |

`NEXT_PUBLIC_*` variables are baked into the client bundle at build time
and visible to anyone via devtools. That's fine here since the backend
URL isn't sensitive — but it means **no secret should ever be prefixed
`NEXT_PUBLIC_`**. This project has no frontend secrets: no API keys,
database credentials, Redis credentials, or Discord webhook URLs are ever
sent to or stored in the frontend. The frontend only ever calls this
project's own backend, authenticated with the user's own JWT.

## 3. Deploy the FastAPI backend to Render

Render runs this as a **Docker web service** built from the repository
root — Render reads the root `Dockerfile` directly and does not use the
`Procfile` (that's kept for Heroku-style platforms as a fallback, not
needed on Render).

1. New → Web Service → connect the GitHub repo.
2. **Root Directory**: leave blank / repo root (not `frontend` — that's
   the Vercel setting, this is the opposite).
3. **Runtime**: Docker (Render auto-detects the root `Dockerfile`).
4. Render builds the image and runs its `CMD`, which is
   `./scripts/start_prod.sh` — this refuses to start with placeholder
   secrets or `APP_ENV=development`, then runs `alembic upgrade head`
   itself before starting uvicorn (see the script and the Dockerfile's
   comment on why the migration step has to live in the container's
   actual startup command rather than a Procfile release phase that
   Render doesn't run).
5. Set every variable from `.env.production.example` as a Render
   environment variable — generate `SECRET_KEY`,
   `DISCORD_WEBHOOK_ENCRYPTION_KEY`, and `SCAN_TRIGGER_SECRET` with
   `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`,
   never reuse the example placeholders. Render sets `$PORT` itself —
   don't hardcode it.
6. Health check path (Render's own liveness probe, under the service's
   Settings → Health Check Path): `/health`.

## 4. Configure managed PostgreSQL

**Neon**: create a project, copy the connection string from the
dashboard. It looks like `postgresql://user:pass@ep-xxx.neon.tech/dbname`
— rewrite the scheme to `postgresql+asyncpg://` (SQLAlchemy's asyncpg
driver, not the bare driver most providers show by default) and set
`DATABASE_SSL_REQUIRED=true`.

**Supabase**: Project Settings → Database → Connection string → URI. Same
rewrite (`postgresql+asyncpg://`), same `DATABASE_SSL_REQUIRED=true`.

Either way, set the result as `DATABASE_URL`. `app/core/db.py` reads
`DATABASE_SSL_REQUIRED` and passes `connect_args={"ssl": "require"}` to
the async engine — asyncpg doesn't honor an `sslmode=` query string the
way `psycopg2` does, so this flag is the actual mechanism, not the URL.

## 5. Configure managed Redis

**Upstash**: create a Redis database, copy the `rediss://` (note the
double-s — TLS) connection string, set it as `REDIS_URL`.

Redis is used for: rate limiting (login/invite-validate), the live-data
provider cache, per-token alert cooldowns, and the scanner run-lock. All
four now fail gracefully if Redis is unreachable — see
`app/core/rate_limit.py`, `app/adapters/provider_utils.py`, and
`app/workers/scanner.py`'s `_in_cooldown`. The one exception is the
scanner lock itself (`app/workers/scanner_lock.py`): if Redis is down,
`/internal/scanner/run` refuses to start a scan rather than risk two
overlapping runs — an outage pauses scanning rather than corrupting data.

## 6. Run migrations

Two ways to apply the schema, depending on what's convenient:

**Via Alembic** (what Render does automatically on every deploy, through
`scripts/start_prod.sh` — see Section 3):

```bash
alembic upgrade head
```

This applies `0001_initial_schema.py`, `0002_discord_delivery_unique_constraint.py`,
then `0003_discord_alert_types.py` in order.

**Via the Neon/Supabase SQL editor directly** (useful for a first manual
setup, or from a mobile browser where running a CLI isn't practical):
paste the contents of `neon_supabase_schema.sql` (repo root) into the
provider's SQL editor and run it once against an empty database — it
creates the same 12 tables plus both migrations' constraints in a single
transaction.

Both paths were generated directly from `app/models/*.py` via AST
parsing (not hand-typed) and are kept in sync with each other — but
**neither has ever been run against a real database**. Run one of them
against a real Neon/Supabase database and confirm all 12 tables exist
with the expected columns and constraints before trusting this in
production.

## 7. Configure cron-job.org

Create a new cron job:

- URL: `https://api.yourdomain.com/internal/scanner/run`
- Method: `POST`
- Custom header: `X-Scan-Secret: <your SCAN_TRIGGER_SECRET>`
- Schedule: every 1–5 minutes (the scanner itself is cheap per invocation
  — see `MAX_TOKENS_PER_BATCH`; the run-lock in `scanner_lock.py` means a
  slow run just causes the next ping to return
  `{"status": "skipped", "reason": "A scan is already in progress."}`
  rather than stacking up)

Check status the same way, with a GET:

```bash
curl -H "X-Scan-Secret: <secret>" https://api.yourdomain.com/internal/scanner/status
```

Returns `last_run_at`, `last_success_at`, `last_success_stats`,
`last_failure_at`, `last_failure_error`, `data_freshness_hours`.

**Never put `SCAN_TRIGGER_SECRET` in frontend code or a `NEXT_PUBLIC_*`
variable** — cron-job.org calls the backend directly, the frontend never
needs this secret at all.

## 8. Configure Discord alerts

Through the app itself once deployed and logged in as admin:
`/settings/discord` (or `POST /admin/discord-integrations`) — paste a
real Discord webhook URL, it's encrypted with `DISCORD_WEBHOOK_ENCRYPTION_KEY`
before it touches the database and is never returned by any API response
afterward (see `app/api/admin_discord.py`'s `DiscordIntegrationOut`
schema, which has no webhook field at all).

Delivery happens from the backend during a scan run
(`app/workers/discord_delivery.py`), triggered by the same cron ping
that runs the scanner — no separate always-on delivery worker. Retries
use exponential backoff (30s/60s/120s/240s/480s, 5 attempts, then
`permanently_failed`). Duplicate-alert prevention has two layers: a
Redis cooldown as a fast pre-check, and a real database
`UniqueConstraint` on `discord_deliveries(fingerprint,
discord_integration_id)` (migration `0003`) as the actual guarantee —
the DB constraint holds even if Redis is degraded or a concurrent
request races the application-level check. The frontend does not need
to be open for alerts to fire.

**Score filtering vs. all-signals mode.** By default, each Discord
destination only receives alerts at or above its own `minimum_score`
(set per-destination in `/settings/discord`, defaulting to
`DISCORD_ALERT_MIN_SCORE`). Set `DISCORD_ALERT_ALL_SIGNALS=true` to
override this globally — every valid signal the scanner constructs
(WATCH and above) gets delivered regardless of score, and every
destination's individual `minimum_score` is ignored while this is on.
This does not bypass security filtering, duplicate prevention, or
cooldowns — see `DISCORD_ALERT_COOLDOWN_MINUTES`, a second,
delivery-specific cooldown (independent of `ALERT_COOLDOWN_MINUTES`,
which governs whether a signal gets created at all) that exists
specifically because all-signals mode means low-score WATCH signals can
now be created much more often than before.

**Alert types.** Three of the seven Discord alert types have real
detection behind them today: `SIGNAL_DETECTED` (a scored signal),
`SECURITY_RISK` (a token that failed minimum security requirements —
previously these were silently dropped with no alert at all),
and `SCANNER_FAILURE` (a chain's scan pass raised an exception). The
other four (`LIQUIDITY_WARNING`, `DEPLOYER_SELLING`, `MOMENTUM_FAILURE`,
`MOMENTUM_RECOVERY`) are defined in `app/core/discord_alert_types.py`
and supported end-to-end in the schema/config/frontend, but have no
detection logic — each needs comparing a token's metrics across
multiple scan passes over time, which this codebase doesn't do yet
(every scan pass only looks at one snapshot). The `/settings/discord`
page shows which types are actually wired vs. not, rather than
implying all seven work.

## 9. Run production health checks

```bash
curl https://api.yourdomain.com/health
curl https://api.yourdomain.com/health/ready
```

`/health` is a bare liveness check. `/health/ready` actually queries
Postgres and Redis and reports `dry_run`/`low_cost_mode` status — use
this one for your platform's readiness probe, not `/health`, if the
platform supports distinguishing the two.

## 10. Test invite-only access

1. As the seeded admin (`python -m app.seed`), `POST /admin/invites` to
   generate a code.
2. In an incognito window, go to `https://yourdomain.com/invite`, enter
   the code — should validate.
3. Try a fabricated code — should get the same generic "invalid or
   expired" message (never reveals whether a code exists).
4. Complete signup, confirm the invite's `use_count` incremented via
   `GET /admin/invites`.
5. Try reusing a single-use invite a second time — should be rejected.

## 11. Verify data freshness

- Token detail page: shows `DataStatusBadge` (verified/cached/demo/
  unavailable/failed) plus a separate `STALE` badge when the latest
  metric is more than 15 minutes old — the two are independent (see
  `frontend/lib/staleness.ts`).
- `/admin/data-sources`: provider mode and per-provider live/mock status.
- `/admin/backtesting/datasets/[id]`: dataset-level freshness (hours
  since the most recent imported snapshot).
- `GET /internal/scanner/status`: system-level freshness (hours since
  last successful scan).

## 12. Application-error Discord alerts

Every request that would otherwise return a 500 - anywhere in the app,
not just the scanner - fires a Discord alert immediately (not queued
until the next scan cycle), to every enabled `DiscordIntegration`. See
`app/core/error_alerting.py` and the two exception handlers in
`app/main.py`. This is a separate, simpler, more direct path than the
queue-based `DiscordDelivery` system used for real trading signals - it
exists specifically so you don't have to go digging through Render logs
to notice the app broke.

The alert contains only the exception type, the endpoint, and a
truncated (300-char) message - never a full traceback, which can carry
SQL parameter values or request body contents. Render's logs still get
the full traceback via `logger.exception(...)`; the Discord alert is a
pointer telling you to go look, not a replacement for looking.

**Known limitation, stated plainly**: this still needs one DB lookup
(which integrations to notify, and their webhook). If the 500 you're
trying to get alerted about IS a full database outage, that lookup also
fails, and no alert reaches you - a real chicken-and-egg limit of
alerting from inside the app that just broke. External uptime
monitoring (something pinging `/health` on a schedule, independent of
this app) is the right complementary tool for that specific class of
failure.

A 5-minute cooldown (keyed by endpoint + error type) prevents an alert
storm if the same bug fires repeatedly across many requests.

## 13. Switch between mock and live data

Set `DATA_PROVIDER_MODE=live` **and** the specific provider's
`DEXSCREENER_ENABLED=true` / `GOPLUS_ENABLED=true` — both are required
together by design (`app/adapters/factory.py`), so flipping the mode
alone can't silently turn on a provider nobody configured.

**`DEXSCREENER_ENABLED=true` alone does not make the scanner discover
anything.** DexScreener's free tier has no "newest pairs" endpoint —
only lookups by a token address you already know (see
`app/adapters/dexscreener.py`'s `discover_new_pairs`, which deliberately
raises `NotImplementedError` rather than guess at an endpoint). Without
a real discovery source, every scan cycle runs and reports success while
finding zero tokens — this looks identical to "live mode is on but
nothing's happening" and is easy to mistake for a scanner or credentials
problem when it's actually a missing discovery source.

Set `GECKOTERMINAL_ENABLED=true` too (`app/adapters/geckoterminal.py`) —
GeckoTerminal's free, keyless API has a real `/networks/{network}/new_pools`
endpoint that fills exactly this gap, and `factory.py` prefers it over
DexScreener for discovery whenever both are enabled. It also happens to
expose genuine unique buyer/seller counts, which DexScreener's free tier
cannot provide at all — see that adapter's module docstring.

Verify with:

```bash
./scripts/smoke_test.sh
```

Reports `PASS`/`FAIL`/`PENDING` per provider — never claim live data is
working without seeing an actual `PASS` here.

## 14. Enable LOW_COST_MODE

`LOW_COST_MODE=true` in `.env.production.example` by default. See
`README.md`'s "Low-cost mode" section for exactly what it controls
(adaptive scan intervals, batch caps, cooldowns, social/AI analysis
disabled by default). No new workers were added in this phase — the
scanner remains a single shared, lock-protected, cron-triggered batch
job, never per-user or per-token.

## 15. Rotate secrets

1. Generate a new value (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`).
2. Set it in the platform's environment variables.
3. Redeploy the backend (picks up the new env var on restart).
4. For `SECRET_KEY`: rotating it invalidates every existing JWT — all
   users are logged out and must log in again. There's no dual-key grace
   period implemented, so plan a rotation for low-traffic hours.
5. For `DISCORD_WEBHOOK_ENCRYPTION_KEY`: rotating it makes every
   already-stored encrypted webhook URL undecryptable. Re-enter each
   Discord integration's webhook URL through the admin UI after rotating
   this one specifically.
6. For `SCAN_TRIGGER_SECRET`: update the header value in cron-job.org's
   job configuration at the same time you rotate it on the backend, or
   scans will start failing with 401 until both match.

## 16. Shut down or roll back safely

- **Frontend rollback**: Vercel keeps every deployment; use "Instant
  Rollback" in the dashboard to point production traffic at a previous
  deployment immediately.
- **Backend rollback**: Render keeps a build history per service — use
  "Rollback to this deploy" on a previous successful deploy in the
  Render dashboard.
- **Database rollback**: `alembic downgrade -1` reverts the last
  migration. The generated `0001_initial_schema.py` has a real
  `downgrade()` that drops all 12 tables in reverse dependency order —
  **this is destructive**, only use it against a database you mean to
  wipe (e.g. a broken fresh deploy), never against one with real data
  without a backup first.
- **Full shutdown**: disable the cron-job.org job first (stops new
  scans/alerts), then take the backend down, then the frontend. Taking
  the frontend down first would leave the scanner and Discord alerts
  still running with no one able to see the dashboard — usually not what
  you want.
