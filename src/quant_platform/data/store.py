"""Point-in-time market data store.

The store holds validated series and serves history strictly *as of* a date,
which is the platform's primary defence against look-ahead bias: a backtest
running day ``t`` can only ever see bars with ``trading_day <= t``.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date

from quant_platform.core.errors import DataValidationError
from quant_platform.data.contracts import (
    DataEligibility,
    MarketBar,
    ValidatedSeries,
    eligibility_satisfies,
)


class MarketDataStore:
    """In-memory catalog of validated series with as-of retrieval.

    The storage medium is replaceable (ADR-0005); the as-of contract is not.
    """

    def __init__(self, required_eligibility: DataEligibility) -> None:
        self._required = required_eligibility
        self._series: dict[str, ValidatedSeries] = {}
        self._days: dict[str, list[date]] = {}

    def add(self, series: ValidatedSeries) -> None:
        """Register a validated series; refuses data below the store's bar."""
        if not eligibility_satisfies(series.eligibility, self._required):
            raise DataValidationError(
                f"{series.symbol}: eligibility {series.eligibility} does not satisfy "
                f"required {self._required} (validation report {series.validation_report_id})"
            )
        self._series[series.symbol] = series
        self._days[series.symbol] = [b.trading_day for b in series.bars]

    @property
    def symbols(self) -> list[str]:
        return sorted(self._series)

    def bars_as_of(self, symbol: str, as_of: date) -> list[MarketBar]:
        """All bars for ``symbol`` with ``trading_day <= as_of`` (chronological)."""
        series = self._series.get(symbol)
        if series is None:
            raise KeyError(f"symbol not in store: {symbol}")
        cutoff = bisect_right(self._days[symbol], as_of)
        return list(series.bars[:cutoff])

    def trading_days(self, start: date, end: date) -> list[date]:
        """Union of all trading days across stored symbols within ``[start, end]``."""
        days: set[date] = set()
        for series_days in self._days.values():
            days.update(d for d in series_days if start <= d <= end)
        return sorted(days)

    def average_daily_volume(self, symbol: str, as_of: date, window: int = 20) -> float:
        """Trailing average volume, used by liquidity-aware sizing."""
        bars = self.bars_as_of(symbol, as_of)
        if not bars:
            return 0.0
        tail = bars[-window:]
        return sum(b.volume for b in tail) / len(tail)
