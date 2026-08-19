"""
Central settings object. Every environment variable the app depends on is
declared here with a type and a safe default, so a missing .env fails loudly
at startup instead of surfacing as a mysterious runtime error later.
"""
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "Crime Pump Early Detector"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "dev-only-change-me"
    allowed_origins: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://cped:cped@postgres:5432/cped"
    # Managed Postgres providers (Neon, Supabase, etc.) require TLS.
    # asyncpg doesn't read "sslmode" from the URL the way psycopg2 does, so
    # this is a separate flag consumed by app/core/db.py's connect_args
    # instead of relying on a query string the driver would silently
    # ignore. Set true in production against a managed provider.
    database_ssl_required: bool = False

    @field_validator("database_url")
    @classmethod
    def _force_asyncpg_driver(cls, v: str) -> str:
        # Render, Railway, and most managed Postgres providers inject
        # DATABASE_URL as a plain "postgresql://" or "postgresql+psycopg2://"
        # string — the sync driver scheme. The app's engine is async
        # (app/core/db.py uses create_async_engine), so no matter what
        # scheme the platform hands us, force it to asyncpg here, once,
        # in the one place every other module reads the URL from. Without
        # this, create_async_engine raises InvalidRequestError at import
        # time — which is fatal for alembic/env.py too, since it imports
        # app.core.db just to reach Base.metadata, before it gets a chance
        # to swap the driver back to psycopg2 for its own sync connection.
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        if v.startswith("postgresql+psycopg2://"):
            return "postgresql+asyncpg://" + v[len("postgresql+psycopg2://"):]
        return v

    # Discord alert-all-signals mode (Section 12 spec addendum). When
    # true, every valid signal the scanner constructs gets a Discord
    # delivery regardless of score - DISCORD_ALERT_MIN_SCORE is ignored
    # entirely in that case. When false (default), behavior is unchanged
    # from before this setting existed: each DiscordIntegration's own
    # per-integration minimum_score still gates delivery, same as ever.
    discord_alert_all_signals: bool = False
    # Only takes effect as the default minimum_score assigned to
    # newly-created DiscordIntegration rows (see app/api/admin_discord.py)
    # - existing integrations keep whatever minimum_score an admin
    # already set for them. Does not retroactively change existing rows,
    # and has no effect at all while discord_alert_all_signals is True.
    discord_alert_min_score: int = 55
    # Discord-delivery-specific cooldown, independent of the scanner's
    # own signal-creation cooldown (settings.alert_cooldown_minutes,
    # which still governs whether a SignalAlert gets created at all).
    # This one additionally rate-limits Discord *delivery* itself per
    # (token, alert_type) pair - relevant once DISCORD_ALERT_ALL_SIGNALS
    # is on and low-score WATCH signals can be created much more often,
    # since without a second cooldown here a token oscillating right at
    # a score boundary could otherwise re-alert on every scan pass.
    discord_alert_cooldown_minutes: int = 30

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Auth
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    login_rate_limit_per_minute: int = 5

    # Invites
    invite_code_length: int = 9

    # Discord
    discord_webhook_encryption_key: str = "dev-only-change-me-32-bytes!!"

    # Worker / low-cost controls
    scanner_interval_seconds: int = 60
    high_activity_scan_interval_seconds: int = 15
    low_activity_scan_interval_seconds: int = 300
    social_scan_interval_seconds: int = 900
    max_tokens_per_batch: int = 50
    max_api_requests_per_minute: int = 60
    alert_cooldown_minutes: int = 30
    enable_social_analysis: bool = False
    enable_ai_analysis: bool = False
    low_cost_mode: bool = True

    # Safety
    dry_run: bool = True
    enable_live_data: bool = False

    # Data provider mode/config (live-adapter phase)
    data_provider_mode: str = "mock"  # mock | live
    dexscreener_enabled: bool = False
    goplus_enabled: bool = False
    dexscreener_base_url: str = "https://api.dexscreener.com/latest/dex"
    goplus_base_url: str = "https://api.gopluslabs.io/api/v1/token_security"
    data_cache_ttl_seconds: int = 30
    data_request_timeout_seconds: float = 10.0
    data_max_retries: int = 3

    # Shared secret an external cron pinger (e.g. cron-job.org) must send
    # to trigger a scan — avoids running an always-on worker process.
    scan_trigger_secret: str = "dev-only-change-me"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
