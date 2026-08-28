"""
Adapter interface for on-chain/DEX data providers. Every chain data source
plugs in behind this interface so a provider can be swapped without
touching the scanner or scoring engine (Section 4 requirement).

Provider notes (researched before writing any adapter code, per spec):

- DexScreener public API: free, keyless, no published hard rate limit but
  undocumented — treat conservatively (this adapter self-limits via
  MAX_API_REQUESTS_PER_MINUTE). Good for: price, liquidity, volume, pair
  age, DEX/pair address. Missing: holder counts, unique buyer/seller
  counts, wallet-level data, AND a real new-pairs discovery endpoint —
  its free tier only supports lookups by known token address.
- GeckoTerminal public API (app/adapters/geckoterminal.py): free,
  keyless, has a real `/networks/{network}/new_pools` discovery endpoint
  DexScreener's free tier lacks, and genuinely does expose unique
  buyer/seller counts (`transactions.h24.buyers`/`.sellers`) — one part
  of the gap below turned out to have a free source after all once this
  was actually looked into, not assumed unavailable indefinitely.
- On-chain holder count (distinct from unique buyers/sellers above) and
  wallet-level clustering/deployer tracking still has no free, reliable,
  cross-chain source found. Every option checked for that specifically
  (Birdeye, Nansen, Arkham, Moralis) gates it behind a paid plan. This
  remains the one field on TokenSnapshot (holder_count) populated only
  by the mock adapter — wiring a real source is still a genuine "next
  step", not something faked as live.
- Biggest causes of false positives identified from the research pass:
  wash trading between two wallets inflating volume without real buyer
  diversity; a single large buy misread as "momentum" when unique_buyers
  is actually 1; liquidity that is unlocked and gets pulled right after a
  volume spike; bot-driven Telegram/Twitter mention spikes with no
  corresponding on-chain buyer growth.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DataStatus(str, Enum):
    """
    Every adapter call returns one of these, explicitly — never left to be
    inferred from "is some field None". This is what lets the rest of the
    app (and the frontend) tell verified live data, demo data, and a
    provider that's simply down apart, instead of quietly treating
    missing data as zero/safe.
    """

    VERIFIED = "verified"      # real provider data, fetched successfully
    CACHED = "cached"          # real provider data, served from cache (still verified, just not fresh this instant)
    DEMO = "demo"              # mock adapter — clearly fictional, never to be shown as live
    UNAVAILABLE = "unavailable"  # provider has no data for this token (not an error)
    FAILED = "failed"          # provider call errored (timeout, rate limit exhausted, 5xx)


@dataclass
class TokenSnapshot:
    chain: str
    address: str
    name: str | None
    symbol: str | None
    pair_address: str | None
    dex: str | None
    price: float | None
    market_cap: float | None
    liquidity: float | None
    volume_24h: float | None
    buys_24h: int | None
    sells_24h: int | None
    pair_created_at: datetime | None
    # Known gap — see module docstring. None from every adapter except mock
    # until a paid indexer is wired in.
    unique_buyers_24h: int | None = None
    unique_sellers_24h: int | None = None
    holder_count: int | None = None
    data_source: str = "unknown"
    status: DataStatus = DataStatus.UNAVAILABLE
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    error: str | None = None  # set when status is FAILED


class ChainDataAdapter(ABC):
    """Every concrete adapter (real or mock) implements this interface."""

    name: str = "base"

    @abstractmethod
    async def discover_new_pairs(self, chain: str, limit: int = 50) -> list[TokenSnapshot]:
        """Return recently created pairs/tokens for a chain."""
        raise NotImplementedError

    @abstractmethod
    async def get_snapshot(self, chain: str, address: str) -> TokenSnapshot | None:
        """Return a current snapshot for one known token."""
        raise NotImplementedError
