# Product Specification — Crime Pump Early Detector

Private, invite-only research and alerting platform for early-stage
low-cap crypto token momentum on Solana, Base, Ethereum, and BNB Chain.

## Non-negotiable constraints

These apply to every feature, in every phase, with no exceptions:

- **Research alerts only — not financial advice.**
- **No automated trading.** Paper trading is fully simulated; no wallet
  connection, no real orders, ever.
- **No market manipulation.**
- **No guaranteed-profit claims**, anywhere in the product.
- **Invite-only access.** No public signup path exists or should ever
  exist.
- **No fabricated data.** Mock/demo data is always explicitly labeled as
  such (`DataStatus.DEMO`, `data_quality: "DEMO"`) and is never presented
  as live or verified. Historical backtesting data for real tokens is
  never invented — only real, sourced data may be marked `VERIFIED`.
- **Wallet addresses are never exposed in alerts** — smart-money/insider
  activity is summarized only as category counts ("early wallets",
  "deployer-linked wallets").
- **Low-cost, shared-worker architecture.** No worker per user, per
  token, per watchlist, or per alert. One shared, batched, cron-triggered
  scanner. See `README.md`'s "Low-cost mode" section for the full list of
  controls (adaptive intervals, cooldowns, batch caps).

## Core features (by phase)

1. **Foundation** — FastAPI + PostgreSQL + Redis, Docker Compose, health
   checks.
2. **Auth + invites** — Argon2id passwords, JWT access/refresh, atomic
   invite redemption, admin invite/user management.
3. **Token discovery** — swappable chain-data adapters (mock, DexScreener,
   GoPlus), `Token`/`TokenMetric` models.
4. **Security filtering + scoring** — deterministic, transparent 0–100
   score (see `app/scoring/engine.py` for the exact point breakdown);
   fails closed when security data is unavailable.
5. **Discord alerts + low-cost scanning** — encrypted webhooks, retry
   with backoff, per-token cooldowns, durable DB-level duplicate
   prevention independent of Redis, a Redis-locked shared scanner
   triggered by an external cron ping (`POST /internal/scanner/run`),
   never an always-on worker.
6. **Dashboard API** — tokens, alerts, preferences.
7. **Paper trading** — simulated entry/exit with realistic friction
   (slippage, fees, delay), never a real trade.
8. **Backtesting** — time-ordered train/test split, no-lookahead
   evaluation, baseline comparison, a real CSV/JSON import pipeline with
   validation (required fields, address format, duplicate/leakage
   rejection) and VERIFIED/DEMO/ESTIMATED/UNAVAILABLE data-quality
   separation enforced in code, not just convention.
9. **Frontend** — Next.js 18-page dashboard covering every feature above,
   with explicit loading/empty/error/unauthorized/stale-data states and
   DEMO-vs-VERIFIED labeling everywhere data quality is shown.

## Deployment model

Next.js frontend on Vercel; FastAPI backend on a separate Python-capable
host; managed PostgreSQL (Neon/Supabase) and Redis (Upstash); scanning
triggered by an external scheduler (cron-job.org) hitting a protected
endpoint — no workers inside Vercel. Full details in `DEPLOYMENT.md`.

## What "done" does not mean here

This spec has been implemented across many phases in a sandbox with no
network access. Every phase's actual verification status — what compiled,
what pure-logic tests actually ran and passed, and what still requires a
real network/database/Redis/browser to verify — is tracked in
`README.md`'s verification checklist and `HANDOFF.md`. Do not treat
"implemented" as "verified in production" without re-checking those.
