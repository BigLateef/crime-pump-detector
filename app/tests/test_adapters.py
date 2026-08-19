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
