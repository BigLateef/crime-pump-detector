"""
Deterministic mock adapter used whenever DATA_PROVIDER_MODE=mock (the
default). Lets every downstream piece — scoring, security filtering,
alerts, paper trading — be developed and tested without real API keys or
live market data.

Every field name, symbol, and address generated here is prefixed
"DEMO"/"mock-" and status is always DataStatus.DEMO, so this data can
never be mistaken for a verified live signal anywhere it's displayed
(scanner table, alert payload, frontend badges all key off `status`, not
just `data_source`).
"""
import random
from datetime import datetime, timedelta, timezone

from app.adapters.base import ChainDataAdapter, DataStatus, TokenSnapshot

_ADJECTIVES = ["Solar", "Quantum", "Nova", "Cosmic", "Turbo", "Hyper", "Lunar"]
_NOUNS = ["Fox", "Doge", "Cat", "Frog", "Ape", "Whale", "Rocket"]


class MockChainAdapter(ChainDataAdapter):
    name = "mock"

    async def discover_new_pairs(self, chain: str, limit: int = 50) -> list[TokenSnapshot]:
        return [self._random_snapshot(chain) for _ in range(min(limit, 10))]

    async def get_snapshot(self, chain: str, address: str) -> TokenSnapshot | None:
        return self._random_snapshot(chain, address=address)

    def _random_snapshot(self, chain: str, address: str | None = None) -> TokenSnapshot:
        name = f"DEMO {random.choice(_ADJECTIVES)} {random.choice(_NOUNS)}"
        symbol = "DEMO" + "".join(w[0] for w in name.split()[1:]).upper() + str(random.randint(10, 99))
        liquidity = round(random.uniform(5_000, 250_000), 2)
        market_cap = round(liquidity * random.uniform(2, 15), 2)
        buys = random.randint(5, 400)
        sells = random.randint(5, 300)

        return TokenSnapshot(
            chain=chain,
            address=address or f"mock-{random.randint(100000, 999999)}",
            name=name,
            symbol=symbol,
            pair_address=f"mock-pair-{random.randint(100000, 999999)}",
            dex=random.choice(["raydium", "uniswap-v3", "pancakeswap"]),
            price=round(random.uniform(0.00001, 0.05), 8),
            market_cap=market_cap,
            liquidity=liquidity,
            volume_24h=round(random.uniform(1_000, 500_000), 2),
            buys_24h=buys,
            sells_24h=sells,
            pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=random.randint(5, 1440)),
            unique_buyers_24h=random.randint(3, buys),
            unique_sellers_24h=random.randint(2, sells),
            holder_count=random.randint(20, 3000),
            data_source="mock",
            status=DataStatus.DEMO,
        )
