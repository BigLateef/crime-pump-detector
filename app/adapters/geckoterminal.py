"""
Real adapter against GeckoTerminal's free public API
(https://apiguide.geckoterminal.com/). No API key required.

Why this adapter exists at all: DexScreener's free tier (see
dexscreener.py) has no "newest pairs" endpoint, so discover_new_pairs()
there deliberately raises NotImplementedError rather than fake one. This
adapter fills exactly that gap using GeckoTerminal's dedicated
`/networks/{network}/new_pools` endpoint, confirmed via GeckoTerminal's
own public docs and changelog to be a real, currently-documented,
free/keyless endpoint (verified via web search at the time this was
written, not assumed from training data - endpoint availability on a
third-party API can and does change, so re-verify against
apiguide.geckoterminal.com if this ever starts failing broadly).

Bonus capability, not just a gap-filler: GeckoTerminal's pool response
includes `transactions.h24.buyers` / `.sellers` - genuine unique
buyer/seller counts, not just aggregate buy/sell transaction counts.
DexScreener's free tier cannot provide this at all (see base.py's
module docstring "Known gap" section) - this adapter can, and populates
TokenSnapshot.unique_buyers_24h / unique_sellers_24h accordingly. This
directly reduces one of the false-positive risks base.py's own research
notes call out: "a single large buy misread as momentum when
unique_buyers is actually 1" - with a real adapter, that's now a
distinguishable signal instead of an unavoidable blind spot.

Every call goes through the same cached_fetch/fetch_with_retries
pipeline as every other adapter (Redis cache, retry+backoff on
timeout/429/5xx, fixed request timeout) - see provider_utils.py.
holder_count stays None from this adapter: GeckoTerminal's pool/token
responses don't expose it (unlike buyer/seller counts, this genuinely
isn't in their data) - the base.py module docstring's holder-data gap
still stands for that one field specifically.

Not exercised against the live API in this sandbox (no network access).
Syntax-checked only - confirm against the real API before enabling
GECKOTERMINAL_ENABLED=true / DATA_PROVIDER_MODE=live, same standing
caveat as every other real adapter in this codebase.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.adapters.base import ChainDataAdapter, DataStatus, TokenSnapshot
from app.adapters.provider_utils import cached_fetch, fetch_with_retries
from app.core.config import get_settings

logger = logging.getLogger("adapters.geckoterminal")

# GeckoTerminal's own network slugs - confirmed via their docs/FAQ, which
# explicitly warns "eth not ethereum, bsc not binance". Do not assume
# these match this app's internal chain names (they mostly do, except
# ethereum/bnb) or DexScreener's chainId values (dexscreener.py has its
# own separate _CHAIN_MAP for exactly this reason - two providers, two
# different naming conventions, kept as two separate maps rather than
# one "smart" shared one that could silently drift if either provider
# changes their slugs independently).
_CHAIN_MAP = {
    "solana": "solana",
    "base": "base",
    "ethereum": "eth",
    "bnb": "bsc",
}

# Free-tier rate limit is commonly cited around 30 req/min, but sources
# on this are not fully consistent and third-party-documented limits
# drift over time - fetch_with_retries' existing 429 backoff is the real
# safety net, this cap on pages-per-discovery-call is just a
# self-imposed ceiling to avoid routinely brushing up against whatever
# the actual current limit is across 4 chains on a tight scan interval.
_MAX_PAGES_PER_DISCOVERY_CALL = 2
_POOLS_PER_PAGE = 20  # fixed by GeckoTerminal, not configurable


def _strip_chain_prefix(composite_id: str | None, mapped_chain: str) -> str | None:
    """GeckoTerminal ids look like 'eth_0xabc...' or 'solana_Ep2ib6d...' -
    the network slug prefix plus underscore, then the real address. Strip
    only the confirmed prefix rather than splitting on the first
    underscore blindly, since some addresses could themselves contain
    characters that make a naive split ambiguous."""
    if composite_id is None:
        return None
    prefix = f"{mapped_chain}_"
    if composite_id.startswith(prefix):
        return composite_id[len(prefix):]
    return composite_id  # unexpected shape - return as-is rather than mangling it


class GeckoTerminalAdapter(ChainDataAdapter):
    name = "geckoterminal"

    def __init__(self):
        self._settings = get_settings()
        self._client = httpx.AsyncClient(timeout=self._settings.data_request_timeout_seconds)

    async def discover_new_pairs(self, chain: str, limit: int = 50) -> list[TokenSnapshot]:
        mapped_chain = _CHAIN_MAP.get(chain)
        if mapped_chain is None:
            return []

        snapshots: list[TokenSnapshot] = []
        pages_needed = min(_MAX_PAGES_PER_DISCOVERY_CALL, max(1, -(-limit // _POOLS_PER_PAGE)))  # ceil div

        for page in range(1, pages_needed + 1):
            cache_key = f"geckoterminal:new_pools:{mapped_chain}:page{page}"

            async def _fetch_raw(page=page) -> dict:
                async def _do_request() -> httpx.Response:
                    return await self._client.get(
                        f"{self._settings.geckoterminal_base_url}/networks/{mapped_chain}/new_pools",
                        params={"page": page, "include": "base_token,quote_token,dex"},
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
                logger.warning("geckoterminal discovery fetch failed for chain=%s page=%d: %s", chain, page, e)
                break  # partial results from earlier pages (if any) still returned below

            included = {item["id"]: item for item in raw.get("included", [])}

            for pool in raw.get("data", []):
                snap = self._parse_pool(chain, mapped_chain, pool, included, from_cache)
                if snap is not None:
                    snapshots.append(snap)
                if len(snapshots) >= limit:
                    return snapshots

        return snapshots

    def _parse_pool(self, chain: str, mapped_chain: str, pool: dict, included: dict, from_cache: bool) -> TokenSnapshot | None:
        attrs = pool.get("attributes", {})
        relationships = pool.get("relationships", {})

        base_token_id = relationships.get("base_token", {}).get("data", {}).get("id")
        token_address = _strip_chain_prefix(base_token_id, mapped_chain)
        if token_address is None:
            return None  # can't build a TokenSnapshot without a token address

        base_token_record = included.get(base_token_id, {}).get("attributes", {})
        dex_id = relationships.get("dex", {}).get("data", {}).get("id")

        created_at = None
        if attrs.get("pool_created_at"):
            try:
                created_at = datetime.fromisoformat(attrs["pool_created_at"].replace("Z", "+00:00"))
            except ValueError:
                created_at = None  # malformed timestamp - leave None rather than guess

        h24 = attrs.get("transactions", {}).get("h24", {}) or {}
        volume_h24 = attrs.get("volume_usd", {}).get("h24")

        return TokenSnapshot(
            chain=chain,
            address=token_address,
            name=base_token_record.get("name"),
            symbol=base_token_record.get("symbol"),
            pair_address=attrs.get("address"),
            dex=dex_id,
            price=float(attrs["base_token_price_usd"]) if attrs.get("base_token_price_usd") else None,
            market_cap=float(attrs["fdv_usd"]) if attrs.get("fdv_usd") else None,
            liquidity=float(attrs["reserve_in_usd"]) if attrs.get("reserve_in_usd") else None,
            volume_24h=float(volume_h24) if volume_h24 else None,
            buys_24h=h24.get("buys"),
            sells_24h=h24.get("sells"),
            # Real unique buyer/seller counts - see module docstring.
            # DexScreener's free tier cannot provide these at all.
            unique_buyers_24h=h24.get("buyers"),
            unique_sellers_24h=h24.get("sellers"),
            pair_created_at=created_at,
            data_source="geckoterminal",
            status=DataStatus.CACHED if from_cache else DataStatus.VERIFIED,
        )

    async def get_snapshot(self, chain: str, address: str) -> TokenSnapshot | None:
        mapped_chain = _CHAIN_MAP.get(chain)
        if mapped_chain is None:
            return self._unavailable(chain, address, "Chain not supported by this adapter.")

        cache_key = f"geckoterminal:token_pools:{mapped_chain}:{address}"

        async def _fetch_raw() -> dict:
            async def _do_request() -> httpx.Response:
                return await self._client.get(
                    f"{self._settings.geckoterminal_base_url}/networks/{mapped_chain}/tokens/{address}/pools",
                    params={"include": "base_token,quote_token,dex"},
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
            logger.warning("geckoterminal snapshot fetch failed for %s/%s: %s", chain, address, e)
            return self._failed(chain, address, str(e))

        pools = raw.get("data") or []
        if not pools:
            return self._unavailable(chain, address, "No pools returned by GeckoTerminal for this token.")

        # Pick the highest-liquidity pool, same "best pool for this
        # token" intent as DexScreener's get_snapshot picking a matching
        # pair - a token can have several pools (different DEXes / fee
        # tiers), the deepest one is the most representative.
        included = {item["id"]: item for item in raw.get("included", [])}

        def _liquidity(p: dict) -> float:
            try:
                return float(p.get("attributes", {}).get("reserve_in_usd") or 0)
            except (TypeError, ValueError):
                return 0.0

        best_pool = max(pools, key=_liquidity)
        snap = self._parse_pool(chain, mapped_chain, best_pool, included, from_cache)
        if snap is None:
            return self._unavailable(chain, address, "GeckoTerminal pool data missing a token address.")
        return snap

    def _unavailable(self, chain: str, address: str, reason: str) -> TokenSnapshot:
        return TokenSnapshot(
            chain=chain, address=address, name=None, symbol=None, pair_address=None, dex=None,
            price=None, market_cap=None, liquidity=None, volume_24h=None, buys_24h=None, sells_24h=None,
            pair_created_at=None, data_source="geckoterminal", status=DataStatus.UNAVAILABLE, error=reason,
        )

    def _failed(self, chain: str, address: str, reason: str) -> TokenSnapshot:
        return TokenSnapshot(
            chain=chain, address=address, name=None, symbol=None, pair_address=None, dex=None,
            price=None, market_cap=None, liquidity=None, volume_24h=None, buys_24h=None, sells_24h=None,
            pair_created_at=None, data_source="geckoterminal", status=DataStatus.FAILED, error=reason,
        )

    async def aclose(self):
        await self._client.aclose()
