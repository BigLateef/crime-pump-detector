"""extend discord_deliveries for typed, all-signal Discord alerts

Revision ID: 0003
Revises: 0002
Create Date: hand-written — supports the "send every valid signal,
regardless of score" feature plus dedicated non-score alert types
(SECURITY_RISK, SCANNER_FAILURE, etc.) that have no SignalAlert row to
attach to. Not run against a live database yet — verify with the same
checklist used for 0001/0002 before trusting this against production.

Changes:
  1. discord_deliveries.signal_alert_id becomes nullable — SECURITY_RISK
     and SCANNER_FAILURE alerts fire for a token/scan-run, not a
     SignalAlert, since the whole point of a security-risk alert is that
     scoring never got that far.
  2. discord_deliveries.alert_type — the seven types from the spec
     (SIGNAL_DETECTED, SECURITY_RISK, LIQUIDITY_WARNING,
     DEPLOYER_SELLING, MOMENTUM_FAILURE, MOMENTUM_RECOVERY,
     SCANNER_FAILURE). Defaults to 'SIGNAL_DETECTED' so every existing
     row (all of which came from the old signal-alert-only path) is
     correctly backfilled without needing a data migration pass.
  3. discord_deliveries.token_id — nullable FK, populated for
     token-scoped alert types that don't have a signal_alert_id to reach
     the token through.
  4. discord_deliveries.fingerprint — the canonical dedup key for ALL
     alert types now, not just signal-linked ones (SignalAlert already
     has its own signal_fingerprint; this lets SECURITY_RISK/
     SCANNER_FAILURE dedupe the same way without one).
  5. discord_deliveries.payload_json — per-delivery embed content,
     independent of any SignalAlert.payload_json, since SECURITY_RISK/
     SCANNER_FAILURE alerts have no SignalAlert to read a payload from.
  6. Unique constraint swapped from (signal_alert_id, discord_integration_id)
     to (fingerprint, discord_integration_id) — the old constraint can't
     serve as the idempotency guarantee once signal_alert_id is
     nullable, since Postgres treats every NULL as distinct from every
     other NULL in a unique index (two SECURITY_RISK rows for the same
     token would NOT collide on signal_alert_id alone). fingerprint is
     backfilled from the existing signal_fingerprint for old rows in the
     same migration, so this is a like-for-like swap, not a loosening.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('discord_deliveries', 'signal_alert_id', nullable=True)

    op.add_column(
        'discord_deliveries',
        sa.Column('alert_type', sa.String(length=30), nullable=False, server_default='SIGNAL_DETECTED'),
    )
    op.add_column(
        'discord_deliveries',
        sa.Column('token_id', postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        'fk_discord_deliveries_token_id', 'discord_deliveries', 'tokens', ['token_id'], ['id']
    )
    op.add_column('discord_deliveries', sa.Column('fingerprint', sa.String(length=64), nullable=True))
    op.add_column(
        'discord_deliveries',
        sa.Column('payload_json', sa.JSON(), nullable=False, server_default='{}'),
    )

    # Backfill fingerprint for every existing row from the SignalAlert it
    # points at, so the new unique constraint below has real values to
    # enforce against instead of a column full of NULLs.
    op.execute(
        """
        UPDATE discord_deliveries d
        SET fingerprint = sa.signal_fingerprint
        FROM signal_alerts sa
        WHERE d.signal_alert_id = sa.id AND d.fingerprint IS NULL
        """
    )

    op.drop_constraint('uq_discord_delivery_alert_integration', 'discord_deliveries', type_='unique')
    op.create_unique_constraint(
        'uq_discord_delivery_fingerprint_integration',
        'discord_deliveries',
        ['fingerprint', 'discord_integration_id'],
    )

    # Drop the server_default on alert_type after backfill - new inserts
    # must specify it explicitly going forward (mirrors how the rest of
    # this codebase avoids relying on implicit defaults for anything that
    # changes behavior, per app/core/config.py's own stated philosophy).
    op.alter_column('discord_deliveries', 'alert_type', server_default=None)
    op.alter_column('discord_deliveries', 'payload_json', server_default=None)


def downgrade() -> None:
    op.create_unique_constraint(
        'uq_discord_delivery_alert_integration',
        'discord_deliveries',
        ['signal_alert_id', 'discord_integration_id'],
    )
    op.drop_constraint('uq_discord_delivery_fingerprint_integration', 'discord_deliveries', type_='unique')
    op.drop_column('discord_deliveries', 'payload_json')
    op.drop_column('discord_deliveries', 'fingerprint')
    op.drop_constraint('fk_discord_deliveries_token_id', 'discord_deliveries', type_='foreignkey')
    op.drop_column('discord_deliveries', 'token_id')
    op.drop_column('discord_deliveries', 'alert_type')
    op.alter_column('discord_deliveries', 'signal_alert_id', nullable=False)
