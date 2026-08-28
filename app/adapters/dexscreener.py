"""
Real adapter against DexScreener's free public API (https://docs.dexscreener.com).
No API key required. All requests are server-side only — never called from
the browser (see frontend's lib/api.ts, which only talks to this app's own
backend).

Every call goes through: Redis cache (DATA_CACHE_TTL_SECONDS) -> retry with
backoff on timeout/429/5xx (DATA_MAX_RETRIES) -> a fixed request timeout
(DATA_REQUEST_TIMEOUT_SECONDS). Missing fields are left None and reported
with status=UNAVAILABLE or FAILED — never fabricated or defaulted to 0.

Known gap: DexScreener does not expose unique buyer/seller counts or
holder data, only aggregate buys/sells counts and volume. Those fields on
TokenSnapshot stay None from this adapter — see base.py docstring.

Not exercised against the live API in this sandbox (no network access).
Syntax-checked only — confirm against the real API before enabling
DEXSCREENER_ENABLED=true / DATA_PROVIDER_MODE=live.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.adapters.base import ChainDataAdapter, DataStatus, TokenSnapshot
from app.adapters.provider_utils import cached_fetch, fetch_with_retries
from app.core.config import get_settings

logger = logging.getLogger("adapters.dexscreener")

_CHAIN_MAP = {
    "solana": "solana",
    "base": "base",
    "ethereum": "ethereum",
    "bnb": "bsc",
}


class DexScreenerAdapter(ChainDataAdapter):
    name = "dexscreener"

    def __init__(self):
        self._settings = get_settings()
        self._client = httpx.AsyncClient(timeout=self._settings.data_request_timeout_seconds)

    async def discover_new_pairs(self, chain: str, limit: int = 50) -> list[TokenSnapshot]:
        # DexScreener's free tier has no dedicated "newest pairs" endpoint.
        # Documented gap for Phase 3 continuation rather than faked with a
        # guessed endpoint — see get_snapshot() for known-address lookups.
        raise NotImplementedError(
            "DexScreener free tier has no dedicated new-pairs endpoint; "
            "use get_snapshot() for known addresses, or pair this adapter "
            "with a chain-specific new-pair websocket/indexer."
        )

    async def get_snapshot(self, chain: str, address: str) -> TokenSnapshot | None:
        mapped_chain = _CHAIN_MAP.get(chain)
        if mapped_chain is None:
            return self._unavailable(chain, address, "Chain not supported by this adapter.")

        cache_key = f"dexscreener:snapshot:{chain}:{address}"

        async def _fetch_raw() -> dict:
            async def _do_request() -> httpx.Response:
                return await self._client.get(f"{self._settings.dexscreener_base_url}/tokens/{address}")

            resp = await fetch_with_retries(
                _do_request,
                max_retries=self._settings.data_max_retries,
                timeout_seconds=self._settings.data_request_timeout_seconds,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            raw, from_cache = await cached_fetch(cache_key, _fetch_raw, self._settings.data_cache_ttl_seconds)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.warning("dexscreener fetch failed for %s/%s: %s", chain, address, e)
            return self._failed(chain, address, str(e))

        pairs = raw.get("pairs") or []
        pair = next((p for p in pairs if p.get("chainId") == mapped_chain), None)
        if pair is None:
            return self._unavailable(chain, address, "No matching pair returned by DexScreener.")

        created_at = None
        if pair.get("pairCreatedAt"):
            created_at = datetime.fromtimestamp(pair["pairCreatedAt"] / 1000, tz=timezone.utc)

        return TokenSnapshot(
            chain=chain,
            address=address,
            name=pair.get("baseToken", {}).get("name"),
            symbol=pair.get("baseToken", {}).get("symbol"),
            pair_address=pair.get("pairAddress"),
            dex=pair.get("dexId"),
            price=float(pair["priceUsd"]) if pair.get("priceUsd") else None,
            market_cap=pair.get("fdv"),
            liquidity=pair.get("liquidity", {}).get("usd"),
            volume_24h=pair.get("volume", {}).get("h24"),
            buys_24h=pair.get("txns", {}).get("h24", {}).get("buys"),
            sells_24h=pair.get("txns", {}).get("h24", {}).get("sells"),
            pair_created_at=created_at,
            data_source="dexscreener",
            status=DataStatus.CACHED if from_cache else DataStatus.VERIFIED,
        )

    def _unavailable(self, chain: str, address: str, reason: str) -> TokenSnapshot:
        return TokenSnapshot(
            chain=chain, address=address, name=None, symbol=None, pair_address=None, dex=None,
            price=None, market_cap=None, liquidity=None, volume_24h=None, buys_24h=None, sells_24h=None,
            pair_created_at=None, data_source="dexscreener", status=DataStatus.UNAVAILABLE, error=reason,
        )

    def _failed(self, chain: str, address: str, reason: str) -> TokenSnapshot:
        return TokenSnapshot(
            chain=chain, address=address, name=None, symbol=None, pair_address=None, dex=None,
            price=None, market_cap=None, liquidity=None, volume_24h=None, buys_24h=None, sells_24h=None,
            pair_created_at=None, data_source="dexscreener", status=DataStatus.FAILED, error=reason,
        )

    async def aclose(self):
        await self._client.aclose()
