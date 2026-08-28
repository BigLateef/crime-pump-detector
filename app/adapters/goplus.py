"""
Real adapter against GoPlus Security's free public API
(https://docs.gopluslabs.io/reference/token-security-api). No API key
required for reasonable usage. Server-side only.

Same cache/retry/timeout treatment as dexscreener.py. Returns a
SecurityCheckResult with an explicit status rather than a bare dict, so
callers (app/security/rules.py) can distinguish "confirmed safe",
"confirmed risky", "provider has no data for this contract", and
"provider call failed" instead of treating all four as one thing.

Not exercised against the live API in this sandbox (no network access).
Syntax-checked only — confirm against the real API before enabling
GOPLUS_ENABLED=true / DATA_PROVIDER_MODE=live.
"""
import logging
from dataclasses import dataclass

import httpx

from app.adapters.base import DataStatus
from app.adapters.provider_utils import cached_fetch, fetch_with_retries
from app.core.config import get_settings

logger = logging.getLogger("adapters.goplus")

_CHAIN_ID_MAP = {
    "ethereum": "1",
    "bnb": "56",
    "base": "8453",
    # Solana uses a separate GoPlus endpoint (/solana/token_security), not
    # the EVM chain-id-keyed one — left as a follow-up, not faked here.
}


@dataclass
class SecurityCheckResult:
    status: DataStatus
    raw: dict | None  # GoPlus's raw per-token dict, or None if unavailable/failed
    error: str | None = None


class GoPlusAdapter:
    name = "goplus"

    def __init__(self):
        self._settings = get_settings()
        self._client = httpx.AsyncClient(timeout=self._settings.data_request_timeout_seconds)

    async def get_contract_security(self, chain: str, address: str) -> SecurityCheckResult:
        chain_id = _CHAIN_ID_MAP.get(chain)
        if chain_id is None:
            return SecurityCheckResult(status=DataStatus.UNAVAILABLE, raw=None, error="Chain not supported by GoPlus adapter (Solana needs a separate endpoint).")

        cache_key = f"goplus:security:{chain}:{address.lower()}"

        async def _fetch_raw() -> dict:
            async def _do_request() -> httpx.Response:
                return await self._client.get(
                    f"{self._settings.goplus_base_url}/{chain_id}",
                    params={"contract_addresses": address.lower()},
                )

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
            logger.warning("goplus fetch failed for %s/%s: %s", chain, address, e)
            return SecurityCheckResult(status=DataStatus.FAILED, raw=None, error=str(e))

        result = (raw.get("result") or {}).get(address.lower())
        if result is None:
            return SecurityCheckResult(status=DataStatus.UNAVAILABLE, raw=None, error="GoPlus has no record for this contract.")

        return SecurityCheckResult(
            status=DataStatus.CACHED if from_cache else DataStatus.VERIFIED,
            raw=result,
        )

    async def aclose(self):
        await self._client.aclose()
