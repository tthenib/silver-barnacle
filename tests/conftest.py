"""Shared fixtures: frozen clock, audit ledger, real platform config, synthetic data."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from quant_platform.core.audit import AuditLedger
from quant_platform.core.clock import FrozenClock
from quant_platform.core.config import PlatformConfig, load_platform_config
from quant_platform.data.contracts import DataEligibility, MarketBar
from quant_platform.data.store import MarketDataStore
from quant_platform.data.synthetic import SyntheticMarketDataProvider
from quant_platform.data.validation import BarSeriesValidator

REPO_ROOT = Path(__file__).resolve().parents[1]

UNIVERSE = ("AAA", "BBB", "CCC", "DDD")
DATA_START = date(2024, 1, 1)
DATA_END = date(2025, 6, 30)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2025, 7, 1, 12, 0, tzinfo=UTC))


@pytest.fixture
def audit(clock: FrozenClock) -> AuditLedger:
    return AuditLedger(clock=clock)


@pytest.fixture(scope="session")
def platform_config() -> PlatformConfig:
    """The real committed configuration — tests validate what ships."""
    return load_platform_config(REPO_ROOT / "config")


@pytest.fixture(scope="session")
def synthetic_store() -> MarketDataStore:
    """Validated synthetic data for the shared test universe."""
    session_clock = FrozenClock(datetime(2025, 7, 1, tzinfo=UTC))
    provider = SyntheticMarketDataProvider(seed=42, clock=session_clock)
    validator = BarSeriesValidator()
    store = MarketDataStore(required_eligibility=DataEligibility.VALID_FOR_BACKTEST)
    for symbol in UNIVERSE:
        bars = provider.get_daily_bars(symbol, DATA_START, DATA_END)
        series, _report = validator.validate(symbol, bars)
        store.add(series)
    return store


def make_bar(
    symbol: str = "AAA",
    trading_day: date = date(2025, 1, 6),
    close: float = 100.0,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: float = 1_000_000.0,
    source: str = "test",
) -> MarketBar:
    """Hand-built bar with consistent OHLC around the given close."""
    open_price = open_ if open_ is not None else close
    return MarketBar(
        symbol=symbol,
        trading_day=trading_day,
        open=open_price,
        high=high if high is not None else max(open_price, close) * 1.01,
        low=low if low is not None else min(open_price, close) * 0.99,
        close=close,
        volume=volume,
        source=source,
        ingested_at_utc=datetime(2025, 7, 1, tzinfo=UTC),
    )
