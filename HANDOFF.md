# Crime Pump Early Detector — Handoff (Phases 1–9)

Private, invite-only research and alerting platform for early-stage
low-cap token momentum. **Research alerts only — not financial advice.
No automated trading. No market manipulation.** This doc lets a new chat
or another engineer pick the project up without the original conversation
history — see also `README.md` for setup commands and the security-review
checklist.

## Status in one line

Backend is functionally complete across all 9 phases at the API level.
Nothing has been run against a live network (no network access in the
build sandbox) — everything was syntax-checked, and pure-logic modules
(scoring, security rules, invite-code generation, backtesting) have real
unit tests. The Next.js frontend (18 dashboard pages) was **not** built —
only the API it would consume.

## Phase-by-phase summary

**Phase 1 — Foundation.** FastAPI app, async SQLAlchemy engine, Redis
client, structured JSON logging, `/health` + `/health/ready`, Docker
Compose (`api`/`postgres`/`redis`), basic tests.

**Phase 2 — Auth + invites.** `User`/`Invite`/`InviteRedemption`/
`UserPreference` models. Argon2id password hashing. JWT access (15 min)
+ refresh (30 day) tokens. Invite codes generated with `secrets`
(CSPRNG), stored only as a SHA-256 hash — raw code is returned to the
admin exactly once and never logged. Invite validation and signup both
return an identical "invalid or expired" error regardless of which
specific case applies. Signup does the invite-lookup-with-row-lock +
user-create + use-count-increment + redemption-record in one transaction
to prevent double-redemption races. Login and invite-validate are
rate-limited via Redis. Admin endpoints: create/list/revoke invites,
list/disable/delete users.

**Phase 3 — Token discovery.** `Token`/`TokenMetric`/`SignalAlert`
models. `ChainDataAdapter` interface so providers are swappable. Three
adapters: `MockChainAdapter` (deterministic synthetic data, used by
default since `DRY_RUN=true`), `DexScreenerAdapter` (real, free, keyless
— but its free tier has no "new pairs" endpoint, documented as a gap in
the adapter itself), `GoPlusAdapter` (real, free, keyless, contract
security data). **Documented gap:** no free, reliable, cross-chain source
exists for holder counts or wallet-level data (unique buyers, wallet
clustering, deployer tracking) — every option researched (Birdeye,
Nansen, Arkham, Moralis) is paid. The schema and scoring inputs support
these fields; no real adapter populates them yet.

**Phase 4 — Security filtering + scoring.** `app/security/rules.py`:
deterministic rules against GoPlus's documented schema — honeypot,
blacklist/whitelist, pause/freeze controls, and hidden-owner privileges
are hard fails; mint authority, high tax, unlocked liquidity, and holder
concentration are soft penalties (capped at 30). Fails closed (treats
"no data" as unsafe) rather than assuming safety. `app/scoring/engine.py`:
transparent 0–100 score matching the spec's point breakdown exactly
(momentum 25 / buyer quality 15 / liquidity 15 / smart money 15 /
social 10 / holder distribution 10, minus up to 30 each for contract
risk / manipulation / insider risk), with every point traceable to a
named reason string.

**Phase 5 — Discord + low-cost background processing.**
`DiscordIntegration`/`DiscordDelivery` models. Webhook URLs encrypted at
rest with Fernet (key derived from `DISCORD_WEBHOOK_ENCRYPTION_KEY`),
never returned by any API response, never logged. Delivery worker
retries with exponential backoff (30s/60s/120s/240s/480s, 5 attempts,
then `permanently_failed`). Per Section 13's cost-control requirements,
there is **no always-on worker loop** — `app/workers/scanner.py` runs one
shared batch scan (never per-user, never per-token) and is triggered by
`POST /internal/scan`, meant to be pinged by an external scheduler
(cron-job.org or similar), matching the pattern already used in the
dreamDEX bot project. Alert deduplication uses a fingerprint (token +
signal level + score bucket) plus a Redis cooldown key per token.

**Phase 6 — Dashboard API.** Read endpoints for token listing/detail/
metrics/alerts and user preferences (GET/PATCH). This is the API surface
a frontend would call — **no frontend was built**.

**Phase 7 — Paper trading.** `PaperTrade` model, pure simulation (no
wallet connection, no real orders). Entry price is adjusted for
simulated slippage/DEX-fee/gas friction; exits check stop-loss/
take-profit/max-holding-period against the latest known price via an
on-demand `check-exit` endpoint rather than a dedicated worker.

**Phase 8 — Backtesting.** `app/backtesting/framework.py`: time-ordered
train/test split (never shuffled, to avoid leaking future data),
strictly-no-lookahead case evaluation, and a baseline comparison (naive
liquidity-floor alerting vs. the scoring engine). **This module contains
no real historical data.** Populating `HistoricalCase` records for
$COAI/$SIREN/$M/$LAB and 20 comparable tokens needs a real historical
data pipeline this sandbox can't build (no network access) — and
inventing plausible numbers for real tickers would be actively
misleading, so that wasn't done. The tests use clearly-labeled synthetic
cases (`SYNTHETIC-RUNNER-01`, etc.).

**Phase 9 — Testing, docs, deployment prep.** Alembic setup (`env.py`
swaps the async `asyncpg` URL for sync `psycopg2` since Alembic itself
runs sync). `app/seed.py` bootstraps the first admin account — the one
deliberate exception to "everyone comes through an invite," since
nothing can generate an invite without an admin. Unit tests for scoring,
security rules, invite-code generation/hashing, and backtesting (all
pure-logic, no DB dependency, most likely to actually pass once
dependencies are installed). `README.md` has setup commands, a
what's-real-vs-gap table, and a security-review checklist for a human
reviewer.

## What was never executed

No network access in the build sandbox means: `pip install` never
completed, `pytest` never actually ran (only `python3 -m py_compile`
against every file, which passed clean), and the DexScreener/GoPlus
adapters were never called against a live API. Treat all of this as
reviewed-but-unverified until it's run somewhere with network access —
see the Quick Start in `README.md`.

## File map

```
crime-pump-detector/
├── app/
│   ├── main.py                       FastAPI app, router mounting
│   ├── seed.py                       bootstraps first admin user
│   ├── core/
│   │   ├── config.py                  all env vars, typed + defaulted
│   │   ├── db.py                      async SQLAlchemy engine/session
│   │   ├── redis_client.py
│   │   ├── logging.py                 JSON structured logging
│   │   ├── security.py                password hashing, JWT, invite codes
│   │   ├── crypto.py                  Fernet encryption for webhook URLs
│   │   ├── rate_limit.py              Redis fixed-window limiter
│   │   └── deps.py                    get_current_user / require_admin
│   ├── models/                        User, Invite, Token, SignalAlert,
│   │                                   DiscordIntegration, PaperTrade, etc.
│   ├── schemas/auth.py                Pydantic request/response models
│   ├── adapters/
│   │   ├── base.py                    ChainDataAdapter interface + notes
│   │   ├── mock.py                    dry-run synthetic data (default)
│   │   ├── dexscreener.py             real, untested against live API
│   │   ├── goplus.py                  real, untested against live API
│   │   └── factory.py                 picks mock vs real by DRY_RUN
│   ├── security/rules.py              deterministic contract-risk filter
│   ├── scoring/engine.py              transparent 0-100 scoring
│   ├── paper_trading/simulation.py    entry/exit friction simulation
│   ├── backtesting/framework.py       methodology, no real historical data
│   ├── workers/
│   │   ├── scanner.py                 shared batch scan (cron-triggered)
│   │   └── discord_delivery.py        retry/backoff webhook delivery
│   ├── api/                           auth, admin_*, tokens, preferences,
│   │                                   paper_trades, internal, health
│   └── tests/                         pure-logic tests (scoring, security,
│                                       invite codes, backtesting) + health
├── alembic/                           migration scaffolding, no migrations
│                                       generated yet (needs `--autogenerate`
│                                       run against a live DB)
├── Dockerfile / docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md                          setup + security-review checklist
```

## Next steps, in priority order

1. Run the Quick Start in `README.md` somewhere with network access; fix
   whatever the first real `pip install` / `pytest` run surfaces.
2. Generate the initial Alembic migration against a live Postgres
   (`alembic revision --autogenerate`) — none exists yet, only the
   scaffolding.
3. Verify the DexScreener and GoPlus adapters against their live APIs.
4. Decide on a real holder/wallet-data source (paid) if smart-money
   tracking is a priority — it's the single biggest functional gap.
5. Build the Next.js frontend against the existing API.
6. Build a real historical dataset for backtesting, sourced honestly —
   this doc explicitly avoided fabricating it.
