"""
Tests the retry/timeout/cache behavior of the live adapters using
httpx.MockTransport, so no real network call is ever made — same
technique works in CI as it would here, once dependencies are installed
(this sandbox has no network to install httpx/pytest-asyncio, so these
are syntax-checked only, not executed, in this environment).
"""
import json

import httpx
import pytest

from app.adapters.dexscreener import DexScreenerAdapter
from app.adapters.base import DataStatus
from app.adapters.goplus import GoPlusAdapter


def _dexscreener_ok_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "pairs": [
                    {
                        "chainId": "solana",
                        "baseToken": {"name": "Test Token", "symbol": "TEST"},
                        "pairAddress": "pair123",
                        "dexId": "raydium",
                        "priceUsd": "0.0001",
                        "fdv": 100000,
                        "liquidity": {"usd": 50000},
                        "volume": {"h24": 20000},
                        "txns": {"h24": {"buys": 40, "sells": 20}},
                        "pairCreatedAt": 1700000000000,
                    }
                ]
            },
        )
    return httpx.MockTransport(handler)


def _always_500_transport():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(500, json={"error": "server error"})
    return httpx.MockTransport(handler), calls


@pytest.mark.asyncio
async def test_dexscreener_verified_on_success():
    adapter = DexScreenerAdapter()
    adapter._client = httpx.AsyncClient(transport=_dexscreener_ok_transport())
    snap = await adapter.get_snapshot("solana", "some-address")
    assert snap.status == DataStatus.VERIFIED
    assert snap.symbol == "TEST"
    assert snap.liquidity == 50000
    await adapter.aclose()


@pytest.mark.asyncio
async def test_dexscreener_unsupported_chain_returns_unavailable():
    adapter = DexScreenerAdapter()
    snap = await adapter.get_snapshot("dogecoin", "some-address")
    assert snap.status == DataStatus.UNAVAILABLE
    await adapter.aclose()


@pytest.mark.asyncio
async def test_dexscreener_retries_then_fails_on_persistent_500():
    adapter = DexScreenerAdapter()
    transport, calls = _always_500_transport()
    adapter._client = httpx.AsyncClient(transport=transport)
    adapter._settings.data_max_retries = 2
    snap = await adapter.get_snapshot("solana", "some-address")
    assert snap.status == DataStatus.FAILED
    assert calls["count"] == 3  # 1 initial + 2 retries
    await adapter.aclose()


def _goplus_ok_transport(address: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"result": {address.lower(): {"is_honeypot": "0", "buy_tax": "0.05", "sell_tax": "0.05"}}},
        )
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_goplus_verified_on_success():
    address = "0x" + "a" * 40
    adapter = GoPlusAdapter()
    adapter._client = httpx.AsyncClient(transport=_goplus_ok_transport(address))
    result = await adapter.get_contract_security("ethereum", address)
    assert result.status == DataStatus.VERIFIED
    assert result.raw["is_honeypot"] == "0"
    await adapter.aclose()


@pytest.mark.asyncio
async def test_goplus_unsupported_chain_returns_unavailable():
    adapter = GoPlusAdapter()
    result = await adapter.get_contract_security("solana", "some-address")
    assert result.status == DataStatus.UNAVAILABLE
    await adapter.aclose()


@pytest.mark.asyncio
async def test_mock_adapter_always_returns_demo_status():
    from app.adapters.mock import MockChainAdapter

    adapter = MockChainAdapter()
    snap = await adapter.get_snapshot("solana", "any-address")
    assert snap.status == DataStatus.DEMO
    assert snap.symbol.startswith("DEMO")


# ---- GeckoTerminal (real new-pairs discovery source - see
# app/adapters/geckoterminal.py's module docstring for why this adapter
# exists at all) ----

def _geckoterminal_new_pools_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "eth_0xpool111",
                        "type": "pool",
                        "attributes": {
                            "address": "0xpool111",
                            "pool_created_at": "2026-01-01T00:00:00Z",
                            "base_token_price_usd": "0.0005",
                            "fdv_usd": "120000",
                            "reserve_in_usd": "45000",
                            "volume_usd": {"h24": "18000"},
                            "transactions": {"h24": {"buys": 30, "sells": 10, "buyers": 22, "sellers": 8}},
                        },
                        "relationships": {
                            "base_token": {"data": {"id": "eth_0xTOKENADDR", "type": "token"}},
                            "quote_token": {"data": {"id": "eth_0xWETH", "type": "token"}},
                            "dex": {"data": {"id": "uniswap_v3", "type": "dex"}},
                        },
                    }
                ],
                "included": [
                    {
                        "id": "eth_0xTOKENADDR",
                        "type": "token",
                        "attributes": {"name": "Test Gecko Token", "symbol": "GTEST"},
                    }
                ],
            },
        )
    return httpx.MockTransport(handler)


def _geckoterminal_missing_base_token_transport():
    """Simulates a pool record with no base_token relationship at all -
    the adapter must skip it (return None from _parse_pool), not crash."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "eth_0xpool222", "type": "pool", "attributes": {}, "relationships": {}}]},
        )
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_geckoterminal_discover_new_pairs_parses_real_response_shape():
    from app.adapters.geckoterminal import GeckoTerminalAdapter

    adapter = GeckoTerminalAdapter()
    adapter._client = httpx.AsyncClient(transport=_geckoterminal_new_pools_transport())
    snapshots = await adapter.discover_new_pairs("ethereum", limit=10)

    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.status == DataStatus.VERIFIED
    assert snap.address == "0xTOKENADDR"  # composite id prefix stripped correctly
    assert snap.symbol == "GTEST"
    assert snap.dex == "uniswap_v3"
    assert snap.liquidity == 45000.0
    # The whole point of this adapter over DexScreener: real unique
    # buyer/seller counts, not just aggregate buy/sell transaction counts.
    assert snap.unique_buyers_24h == 22
    assert snap.unique_sellers_24h == 8
    await adapter.aclose()


@pytest.mark.asyncio
async def test_geckoterminal_unsupported_chain_returns_empty_list():
    from app.adapters.geckoterminal import GeckoTerminalAdapter

    adapter = GeckoTerminalAdapter()
    snapshots = await adapter.discover_new_pairs("dogecoin", limit=10)
    assert snapshots == []
    await adapter.aclose()


@pytest.mark.asyncio
async def test_geckoterminal_skips_pool_with_no_base_token_instead_of_crashing():
    from app.adapters.geckoterminal import GeckoTerminalAdapter

    adapter = GeckoTerminalAdapter()
    adapter._client = httpx.AsyncClient(transport=_geckoterminal_missing_base_token_transport())
    snapshots = await adapter.discover_new_pairs("ethereum", limit=10)
    assert snapshots == []  # skipped, not raised
    await adapter.aclose()


def test_strip_chain_prefix_handles_expected_and_unexpected_shapes():
    from app.adapters.geckoterminal import _strip_chain_prefix

    assert _strip_chain_prefix("eth_0xabc123", "eth") == "0xabc123"
    assert _strip_chain_prefix("solana_Ep2ib6dYdEeq", "solana") == "Ep2ib6dYdEeq"
    # Unexpected shape (prefix doesn't match) - returned as-is rather than
    # mangled, per the function's own documented behavior.
    assert _strip_chain_prefix("unexpected_format", "eth") == "unexpected_format"
    assert _strip_chain_prefix(None, "eth") is None


@pytest.mark.asyncio
async def test_geckoterminal_factory_prefers_geckoterminal_over_dexscreener():
    """When both GECKOTERMINAL_ENABLED and DEXSCREENER_ENABLED are true,
    get_chain_adapter() must return GeckoTerminalAdapter - DexScreener's
    free tier can't discover pairs at all, so GeckoTerminal should always
    win when both are available (see factory.py's own docstring)."""
    from unittest.mock import patch

    from app.adapters.factory import get_chain_adapter
    from app.adapters.geckoterminal import GeckoTerminalAdapter
    from app.core.config import get_settings

    settings = get_settings()
    with patch.object(settings, "data_provider_mode", "live"), \
         patch.object(settings, "geckoterminal_enabled", True), \
         patch.object(settings, "dexscreener_enabled", True):
        adapter = get_chain_adapter()
    assert isinstance(adapter, GeckoTerminalAdapter)
