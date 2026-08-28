"""
Picks which adapters back the app, driven by DATA_PROVIDER_MODE and the
per-provider *_ENABLED flags — never mixed. mode=mock always returns the
mock adapter regardless of the enabled flags (mock stays available for
dev/test even when live credentials exist). mode=live requires the
specific provider's *_ENABLED flag too, so enabling live mode doesn't
silently turn on a provider nobody configured.

GECKOTERMINAL_ENABLED takes priority over DEXSCREENER_ENABLED when both
are set: DexScreener's free tier has no real-pair-discovery endpoint at
all (see dexscreener.py), so if GeckoTerminal is available, it's
strictly the better choice for get_chain_adapter() - this app only ever
uses ONE chain adapter at a time for both discovery and snapshot lookups
(see scanner.py), so this is a straight either/or, not a
compose-both-adapters situation.
"""
from app.adapters.base import ChainDataAdapter
from app.adapters.dexscreener import DexScreenerAdapter
from app.adapters.geckoterminal import GeckoTerminalAdapter
from app.adapters.goplus import GoPlusAdapter
from app.adapters.mock import MockChainAdapter
from app.core.config import get_settings


def get_chain_adapter() -> ChainDataAdapter:
    settings = get_settings()
    if settings.data_provider_mode != "live":
        return MockChainAdapter()
    if settings.geckoterminal_enabled:
        return GeckoTerminalAdapter()
    if settings.dexscreener_enabled:
        return DexScreenerAdapter()
    return MockChainAdapter()


def get_security_adapter() -> GoPlusAdapter | None:
    settings = get_settings()
    if settings.data_provider_mode != "live" or not settings.goplus_enabled:
        return None  # caller falls back to evaluate_security(None) — fails closed
    return GoPlusAdapter()
