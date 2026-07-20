"""Injectable time source.

All components take a :class:`Clock` instead of calling ``datetime.now`` so
that backtests, simulations, and tests control time deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current UTC time."""

    def now(self) -> datetime:
        """Return the current time as a timezone-aware UTC datetime."""
        ...


class WallClock:
    """Real system clock. Use only at composition roots, never in pure logic."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Deterministic clock for tests, backtests, and simulation.

    Time only moves when the owner advances it, which makes staleness and
    expiry logic testable.
    """

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware datetime")
        self._now = moment.astimezone(UTC)

    def advance(self, *, seconds: float = 0.0, days: float = 0.0) -> None:
        from datetime import timedelta

        self._now += timedelta(seconds=seconds, days=days)
