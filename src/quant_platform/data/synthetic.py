"""Deterministic synthetic market data for tests, backtest fixtures, and simulation.

The generator is a seeded geometric random walk with weekday-only calendar.
It exists so the entire platform can be exercised end-to-end with zero
external dependencies and perfectly reproducible results. Synthetic data is
clearly labelled by its ``source`` and must never be treated as real market
history for decision-making.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date, datetime, timedelta

from quant_platform.core.clock import Clock, WallClock
from quant_platform.data.contracts import MarketBar


def _weekdays(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


class SyntheticMarketDataProvider:
    """Seeded synthetic daily bars; identical inputs always produce identical bars."""

    def __init__(
        self,
        seed: int = 0,
        annual_drift: float = 0.05,
        annual_volatility: float = 0.20,
        base_volume: float = 1_000_000.0,
        clock: Clock | None = None,
    ) -> None:
        self._seed = seed
        self._annual_drift = annual_drift
        self._annual_volatility = annual_volatility
        self._base_volume = base_volume
        self._clock = clock or WallClock()

    @property
    def provider_name(self) -> str:
        return "synthetic"

    def get_daily_bars(self, symbol: str, start: date, end: date) -> list[MarketBar]:
        rng = random.Random(self._symbol_seed(symbol))
        ingested_at: datetime = self._clock.now()
        daily_drift = self._annual_drift / 252.0
        daily_vol = self._annual_volatility / math.sqrt(252.0)

        # Walk the price from a symbol-dependent base so different symbols
        # have different levels and paths but remain fully reproducible.
        price = 20.0 + (self._symbol_seed(symbol) % 400) / 4.0
        bars: list[MarketBar] = []
        for trading_day in _weekdays(start, end):
            log_return = rng.gauss(daily_drift, daily_vol)
            open_price = price
            close_price = price * math.exp(log_return)
            intraday_range = abs(rng.gauss(0.0, daily_vol / 2.0))
            high = max(open_price, close_price) * (1.0 + intraday_range)
            low = min(open_price, close_price) * (1.0 - intraday_range)
            volume = self._base_volume * (0.5 + rng.random())
            bars.append(
                MarketBar(
                    symbol=symbol,
                    trading_day=trading_day,
                    open=round(open_price, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close_price, 4),
                    volume=round(volume, 0),
                    source=self.provider_name,
                    ingested_at_utc=ingested_at,
                    adjustment_policy="unadjusted",
                )
            )
            price = close_price
        return bars

    def _symbol_seed(self, symbol: str) -> int:
        digest = hashlib.sha256(f"{self._seed}:{symbol}".encode()).hexdigest()
        return int(digest[:12], 16)
