"""
Picks which adapters back the app, driven by DATA_PROVIDER_MODE and the
per-provider *_ENABLED flags — never mixed. mode=mock always returns the
mock adapter regardless of the enabled flags (mock stays available for
dev/test even when live credentials exist). mode=live requires the
specific provider's *_ENABLED flag too, so enabling live mode doesn't
silently turn on a provider nobody configured.
"""
from app.adapters.base import ChainDataAdapter
from app.adapters.dexscreener import DexScreenerAdapter
from app.adapters.goplus import GoPlusAdapter
from app.adapters.mock import MockChainAdapter
from app.core.config import get_settings


def get_chain_adapter() -> ChainDataAdapter:
    settings = get_settings()
    if settings.data_provider_mode != "live" or not settings.dexscreener_enabled:
        return MockChainAdapter()
    return DexScreenerAdapter()


def get_security_adapter() -> GoPlusAdapter | None:
    settings = get_settings()
    if settings.data_provider_mode != "live" or not settings.goplus_enabled:
        return None  # caller falls back to evaluate_security(None) — fails closed
    return GoPlusAdapter()
