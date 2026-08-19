"""add unique constraint on discord_deliveries(signal_alert_id, discord_integration_id)

Revision ID: 0002
Revises: 0001
Create Date: hand-written — adds the real DB-level idempotency guarantee
for Discord alert delivery, requested in a post-deployment-prep security
audit. Not run against a live database — see README.md's verification
checklist before trusting this against production.
"""
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # If any duplicate (signal_alert_id, discord_integration_id) rows
    # already exist from before this constraint was added, this migration
    # will fail loudly rather than silently drop data — that's
    # deliberate. Deduplicate manually first if it does:
    #   DELETE FROM discord_deliveries a USING discord_deliveries b
    #   WHERE a.id < b.id
    #     AND a.signal_alert_id = b.signal_alert_id
    #     AND a.discord_integration_id = b.discord_integration_id;
    op.create_unique_constraint(
        'uq_discord_delivery_alert_integration',
        'discord_deliveries',
        ['signal_alert_id', 'discord_integration_id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_discord_delivery_alert_integration',
        'discord_deliveries',
        type_='unique',
    )
