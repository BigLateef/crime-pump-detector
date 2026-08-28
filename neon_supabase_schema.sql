-- ============================================================
-- Crime Pump Early Detector -- initial schema (migrations 0001 + 0002)
-- Generated directly from app/models/*.py via AST parsing, matching
-- the corrected alembic/versions/0001_*.py + 0002_*.py exactly.
-- Paste this entire file into the Neon or Supabase SQL editor and run it
-- once, against an empty database.
-- ============================================================

BEGIN;

CREATE TABLE users (
    id UUID NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    email_verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_login_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
);


CREATE TABLE invites (
    id UUID NOT NULL,
    code_hash VARCHAR(64) NOT NULL UNIQUE,
    created_by UUID NOT NULL,
    recipient_label VARCHAR(100),
    recipient_email VARCHAR(255),
    max_uses INTEGER NOT NULL,
    use_count INTEGER NOT NULL,
    is_used BOOLEAN NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    first_used_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);


CREATE TABLE invite_redemptions (
    id UUID NOT NULL,
    invite_id UUID NOT NULL,
    user_id UUID NOT NULL,
    redeemed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ip_hash VARCHAR(64),
    user_agent_hash VARCHAR(64),
    PRIMARY KEY (id),
    FOREIGN KEY (invite_id) REFERENCES invites(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);


CREATE TABLE user_preferences (
    id UUID NOT NULL,
    user_id UUID NOT NULL UNIQUE,
    alert_threshold INTEGER NOT NULL,
    selected_chains JSON NOT NULL,
    watchlists JSON NOT NULL,
    discord_preferences JSON NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);


CREATE TABLE tokens (
    id UUID NOT NULL,
    chain VARCHAR(30) NOT NULL,
    address VARCHAR(100) NOT NULL,
    name VARCHAR(200),
    symbol VARCHAR(30),
    pair_address VARCHAR(100),
    dex VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_token_chain_address UNIQUE (chain, address)
);

CREATE INDEX ix_tokens_address ON tokens (address);

CREATE TABLE token_metrics (
    id UUID NOT NULL,
    token_id UUID NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    price DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,
    liquidity DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    buys INTEGER,
    sells INTEGER,
    unique_buyers INTEGER,
    unique_sellers INTEGER,
    holder_count INTEGER,
    security_score INTEGER,
    data_status VARCHAR(20) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (token_id) REFERENCES tokens(id)
);

CREATE INDEX ix_token_metrics_token_id ON token_metrics (token_id);
CREATE INDEX ix_token_metrics_timestamp ON token_metrics (timestamp);

CREATE TABLE signal_alerts (
    id UUID NOT NULL,
    token_id UUID NOT NULL,
    signal_type VARCHAR(30) NOT NULL,
    signal_fingerprint VARCHAR(64) NOT NULL,
    score INTEGER NOT NULL,
    confidence VARCHAR(20) NOT NULL,
    payload_json JSON NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    FOREIGN KEY (token_id) REFERENCES tokens(id)
);

CREATE INDEX ix_signal_alerts_token_id ON signal_alerts (token_id);
CREATE INDEX ix_signal_alerts_signal_fingerprint ON signal_alerts (signal_fingerprint);
CREATE INDEX ix_signal_alerts_detected_at ON signal_alerts (detected_at);

CREATE TABLE discord_integrations (
    id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    encrypted_webhook_url VARCHAR(500) NOT NULL,
    channel_label VARCHAR(100),
    enabled BOOLEAN NOT NULL,
    minimum_score INTEGER NOT NULL,
    allowed_chains JSON NOT NULL,
    alert_types JSON NOT NULL,
    created_by UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);


CREATE TABLE discord_deliveries (
    id UUID NOT NULL,
    signal_alert_id UUID,
    alert_type VARCHAR(30) NOT NULL,
    token_id UUID,
    fingerprint VARCHAR(64) NOT NULL,
    payload_json JSON NOT NULL,
    discord_integration_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempt_count INTEGER NOT NULL,
    discord_message_id VARCHAR(100),
    last_error VARCHAR(500),
    sent_at TIMESTAMP WITH TIME ZONE,
    next_retry_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (signal_alert_id) REFERENCES signal_alerts(id),
    FOREIGN KEY (token_id) REFERENCES tokens(id),
    FOREIGN KEY (discord_integration_id) REFERENCES discord_integrations(id)
);


CREATE TABLE paper_trades (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    token_id UUID NOT NULL,
    signal_alert_id UUID,
    status VARCHAR(20) NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE NOT NULL,
    simulated_entry_delay_seconds INTEGER NOT NULL,
    simulated_slippage_pct DOUBLE PRECISION NOT NULL,
    simulated_fees_pct DOUBLE PRECISION NOT NULL,
    stop_loss_pct DOUBLE PRECISION,
    take_profit_pct DOUBLE PRECISION,
    max_holding_minutes INTEGER,
    exit_price DOUBLE PRECISION,
    exit_time TIMESTAMP WITH TIME ZONE,
    exit_reason VARCHAR(30),
    position_size_usd DOUBLE PRECISION NOT NULL,
    realized_return_pct DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (token_id) REFERENCES tokens(id),
    FOREIGN KEY (signal_alert_id) REFERENCES signal_alerts(id)
);

CREATE INDEX ix_paper_trades_user_id ON paper_trades (user_id);
CREATE INDEX ix_paper_trades_token_id ON paper_trades (token_id);

CREATE TABLE historical_datasets (
    id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    data_quality VARCHAR(20) NOT NULL,
    uploaded_by UUID NOT NULL,
    source_filename VARCHAR(300),
    importer_version VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    row_count INTEGER NOT NULL,
    valid_row_count INTEGER NOT NULL,
    error_row_count INTEGER NOT NULL,
    duplicate_row_count INTEGER NOT NULL,
    validation_errors JSON NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    imported_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    FOREIGN KEY (uploaded_by) REFERENCES users(id)
);


CREATE TABLE historical_snapshots (
    id UUID NOT NULL,
    dataset_id UUID NOT NULL,
    token_address VARCHAR(100) NOT NULL,
    chain VARCHAR(30) NOT NULL,
    symbol VARCHAR(30),
    snapshot_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    minutes_before_major_move INTEGER NOT NULL,
    price DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,
    liquidity DOUBLE PRECISION,
    volume_1m DOUBLE PRECISION,
    volume_5m DOUBLE PRECISION,
    volume_15m DOUBLE PRECISION,
    volume_1h DOUBLE PRECISION,
    buy_count INTEGER,
    sell_count INTEGER,
    unique_buyers INTEGER,
    unique_sellers INTEGER,
    holder_count INTEGER,
    top_holder_concentration DOUBLE PRECISION,
    deployer_balance DOUBLE PRECISION,
    security_flags JSON NOT NULL,
    source VARCHAR(200) NOT NULL,
    source_url VARCHAR(500),
    data_quality VARCHAR(20) NOT NULL,
    notes VARCHAR(1000),
    outcome VARCHAR(20) NOT NULL,
    major_move_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    maximum_drawdown_pct DOUBLE PRECISION,
    maximum_gain_pct DOUBLE PRECISION,
    dataset_split VARCHAR(20) NOT NULL,
    imported_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (dataset_id) REFERENCES historical_datasets(id)
);

CREATE INDEX ix_historical_snapshots_dataset_id ON historical_snapshots (dataset_id);
CREATE INDEX ix_historical_snapshots_token_address ON historical_snapshots (token_address);

-- migrations 0002+0003: durable idempotency guarantee for Discord
-- delivery. 0002 originally added a UNIQUE(signal_alert_id,
-- discord_integration_id) constraint; 0003 replaced it with this
-- fingerprint-based one once signal_alert_id became nullable (some
-- alert types, like SECURITY_RISK and SCANNER_FAILURE, have no
-- SignalAlert to attach to - see app/core/discord_alert_types.py). This
-- file represents a fresh build, so it goes straight to the final
-- 0003 state rather than creating then dropping the 0002 constraint.
ALTER TABLE discord_deliveries
    ADD CONSTRAINT uq_discord_delivery_fingerprint_integration
    UNIQUE (fingerprint, discord_integration_id);

COMMIT;
