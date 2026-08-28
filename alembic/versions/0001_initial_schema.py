"""initial schema

Revision ID: 0001
Revises: 
Create Date: regenerated from app/models/*.py via AST extraction.
This version fixes two real gaps found in the previous version, before
this file was ever run against a live database:
  1. NOT NULL was only applied when nullable=False was explicit; it now
     also correctly infers NOT NULL from SQLAlchemy 2.0 Mapped[] type
     annotations (Mapped[str] vs Mapped[str | None]), fixing 62 columns.
  2. tokens(chain, address) had a UniqueConstraint in the model that was
     never captured in any migration - added here.
  3. index=True columns now get real indexes (previously silently
     dropped by the migration generator).
The discord_deliveries(signal_alert_id, discord_integration_id) unique
constraint is deliberately NOT included here even though it's in the
current model - it's added by migration 0002 to preserve the real
history of when it was added (see that file for why).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_table(
        'invites',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recipient_label', sa.String(100), nullable=True),
        sa.Column('recipient_email', sa.String(255), nullable=True),
        sa.Column('max_uses', sa.Integer, nullable=False),
        sa.Column('use_count', sa.Integer, nullable=False),
        sa.Column('is_used', sa.Boolean, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_invites_code_hash', 'invites', ['code_hash'], unique=True)
    op.create_table(
        'invite_redemptions',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('invite_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('invites.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ip_hash', sa.String(64), nullable=True),
        sa.Column('user_agent_hash', sa.String(64), nullable=True),
    )
    op.create_table(
        'user_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('alert_threshold', sa.Integer, nullable=False),
        sa.Column('selected_chains', sa.JSON, nullable=False),
        sa.Column('watchlists', sa.JSON, nullable=False),
        sa.Column('discord_preferences', sa.JSON, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'tokens',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('chain', sa.String(30), nullable=False),
        sa.Column('address', sa.String(100), nullable=False),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('symbol', sa.String(30), nullable=True),
        sa.Column('pair_address', sa.String(100), nullable=True),
        sa.Column('dex', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('chain', 'address', name='uq_token_chain_address'),
    )
    op.create_index('ix_tokens_address', 'tokens', ['address'])
    op.create_table(
        'token_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('token_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('tokens.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('price', sa.Float, nullable=True),
        sa.Column('market_cap', sa.Float, nullable=True),
        sa.Column('liquidity', sa.Float, nullable=True),
        sa.Column('volume', sa.Float, nullable=True),
        sa.Column('buys', sa.Integer, nullable=True),
        sa.Column('sells', sa.Integer, nullable=True),
        sa.Column('unique_buyers', sa.Integer, nullable=True),
        sa.Column('unique_sellers', sa.Integer, nullable=True),
        sa.Column('holder_count', sa.Integer, nullable=True),
        sa.Column('security_score', sa.Integer, nullable=True),
        sa.Column('data_status', sa.String(20), nullable=False),
    )
    op.create_index('ix_token_metrics_token_id', 'token_metrics', ['token_id'])
    op.create_index('ix_token_metrics_timestamp', 'token_metrics', ['timestamp'])
    op.create_table(
        'signal_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('token_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('tokens.id'), nullable=False),
        sa.Column('signal_type', sa.String(30), nullable=False),
        sa.Column('signal_fingerprint', sa.String(64), nullable=False),
        sa.Column('score', sa.Integer, nullable=False),
        sa.Column('confidence', sa.String(20), nullable=False),
        sa.Column('payload_json', sa.JSON, nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_signal_alerts_token_id', 'signal_alerts', ['token_id'])
    op.create_index('ix_signal_alerts_signal_fingerprint', 'signal_alerts', ['signal_fingerprint'])
    op.create_index('ix_signal_alerts_detected_at', 'signal_alerts', ['detected_at'])
    op.create_table(
        'discord_integrations',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('encrypted_webhook_url', sa.String(500), nullable=False),
        sa.Column('channel_label', sa.String(100), nullable=True),
        sa.Column('enabled', sa.Boolean, nullable=False),
        sa.Column('minimum_score', sa.Integer, nullable=False),
        sa.Column('allowed_chains', sa.JSON, nullable=False),
        sa.Column('alert_types', sa.JSON, nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'discord_deliveries',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('signal_alert_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('signal_alerts.id'), nullable=False),
        sa.Column('discord_integration_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('discord_integrations.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempt_count', sa.Integer, nullable=False),
        sa.Column('discord_message_id', sa.String(100), nullable=True),
        sa.Column('last_error', sa.String(500), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'paper_trades',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('token_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('tokens.id'), nullable=False),
        sa.Column('signal_alert_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('signal_alerts.id'), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('entry_price', sa.Float, nullable=False),
        sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('simulated_entry_delay_seconds', sa.Integer, nullable=False),
        sa.Column('simulated_slippage_pct', sa.Float, nullable=False),
        sa.Column('simulated_fees_pct', sa.Float, nullable=False),
        sa.Column('stop_loss_pct', sa.Float, nullable=True),
        sa.Column('take_profit_pct', sa.Float, nullable=True),
        sa.Column('max_holding_minutes', sa.Integer, nullable=True),
        sa.Column('exit_price', sa.Float, nullable=True),
        sa.Column('exit_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_reason', sa.String(30), nullable=True),
        sa.Column('position_size_usd', sa.Float, nullable=False),
        sa.Column('realized_return_pct', sa.Float, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_paper_trades_user_id', 'paper_trades', ['user_id'])
    op.create_index('ix_paper_trades_token_id', 'paper_trades', ['token_id'])
    op.create_table(
        'historical_datasets',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('data_quality', sa.String(20), nullable=False),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_filename', sa.String(300), nullable=True),
        sa.Column('importer_version', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('row_count', sa.Integer, nullable=False),
        sa.Column('valid_row_count', sa.Integer, nullable=False),
        sa.Column('error_row_count', sa.Integer, nullable=False),
        sa.Column('duplicate_row_count', sa.Integer, nullable=False),
        sa.Column('validation_errors', sa.JSON, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        'historical_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('dataset_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('historical_datasets.id'), nullable=False),
        sa.Column('token_address', sa.String(100), nullable=False),
        sa.Column('chain', sa.String(30), nullable=False),
        sa.Column('symbol', sa.String(30), nullable=True),
        sa.Column('snapshot_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('minutes_before_major_move', sa.Integer, nullable=False),
        sa.Column('price', sa.Float, nullable=True),
        sa.Column('market_cap', sa.Float, nullable=True),
        sa.Column('liquidity', sa.Float, nullable=True),
        sa.Column('volume_1m', sa.Float, nullable=True),
        sa.Column('volume_5m', sa.Float, nullable=True),
        sa.Column('volume_15m', sa.Float, nullable=True),
        sa.Column('volume_1h', sa.Float, nullable=True),
        sa.Column('buy_count', sa.Integer, nullable=True),
        sa.Column('sell_count', sa.Integer, nullable=True),
        sa.Column('unique_buyers', sa.Integer, nullable=True),
        sa.Column('unique_sellers', sa.Integer, nullable=True),
        sa.Column('holder_count', sa.Integer, nullable=True),
        sa.Column('top_holder_concentration', sa.Float, nullable=True),
        sa.Column('deployer_balance', sa.Float, nullable=True),
        sa.Column('security_flags', sa.JSON, nullable=False),
        sa.Column('source', sa.String(200), nullable=False),
        sa.Column('source_url', sa.String(500), nullable=True),
        sa.Column('data_quality', sa.String(20), nullable=False),
        sa.Column('notes', sa.String(1000), nullable=True),
        sa.Column('outcome', sa.String(20), nullable=False),
        sa.Column('major_move_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('maximum_drawdown_pct', sa.Float, nullable=True),
        sa.Column('maximum_gain_pct', sa.Float, nullable=True),
        sa.Column('dataset_split', sa.String(20), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_historical_snapshots_dataset_id', 'historical_snapshots', ['dataset_id'])
    op.create_index('ix_historical_snapshots_token_address', 'historical_snapshots', ['token_address'])

def downgrade() -> None:
    op.drop_table('historical_snapshots')
    op.drop_table('historical_datasets')
    op.drop_table('paper_trades')
    op.drop_table('discord_deliveries')
    op.drop_table('discord_integrations')
    op.drop_table('signal_alerts')
    op.drop_table('token_metrics')
    op.drop_table('tokens')
    op.drop_table('user_preferences')
    op.drop_table('invite_redemptions')
    op.drop_table('invites')
    op.drop_table('users')
