"""Market data provider interface.

Providers are thin adapters that return raw canonical bars; they perform no
validation and assign no eligibility — that is the validator's job. Real
providers (EDGAR, FRED, Stooq, …) plug in behind this protocol per the
provider strategy in specification section 7.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from quant_platform.data.contracts import MarketBar


class MarketDataProvider(Protocol):
    """Source of raw daily bars for one or more symbols."""

    @property
    def provider_name(self) -> str:
        """Stable identifier recorded as ``source`` on every bar."""
        ...

    def get_daily_bars(self, symbol: str, start: date, end: date) -> list[MarketBar]:
        """Return raw daily bars for ``symbol`` in ``[start, end]`` inclusive.

        Implementations must not fabricate missing days and must record the
        retrieval timestamp on every bar.
        """
        ...
