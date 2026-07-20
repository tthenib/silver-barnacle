"""Strategy contracts.

A strategy is a versioned declaration (:class:`StrategySpec`) plus a pure
signal function. Signals are proposals with explicit direction, conviction,
uncertainty, and an invalidation condition; converting them into positions is
someone else's job. A spec missing its cost assumptions or invalidation
policy is research-only by construction (the registry enforces lifecycle).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.core.metadata import content_hash, new_id
from quant_platform.data.contracts import MarketBar


class SignalDirection(StrEnum):
    LONG = "LONG"
    FLAT = "FLAT"
    SHORT = "SHORT"


class StrategySpec(BaseModel):
    """Versioned strategy declaration.

    ``parameters`` are the full set of tunables — no magic numbers may hide in
    strategy code. ``spec_hash`` identifies the exact configuration in
    backtest reports and the experiment registry.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    family: str
    universe: tuple[str, ...] = Field(min_length=1)
    parameters: dict[str, Any]
    horizon_days: int = Field(gt=0)
    invalidation_policy: str = Field(min_length=1)
    no_trade_conditions: tuple[str, ...] = ()

    def spec_hash(self) -> str:
        return content_hash(self.model_dump(mode="json"))


class SignalProposal(BaseModel):
    """One strategy's proposal for one symbol at one as-of date.

    ``conviction`` is a relative preference in [0, 1] used by the allocator;
    it is not a probability and never bypasses sizing or risk limits.
    ``invalidation_price`` (where the thesis is wrong) feeds risk-per-trade
    sizing; strategies that cannot state one produce unpriced-risk signals,
    which sizing treats maximally conservatively.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str = Field(default_factory=lambda: new_id("signal"))
    strategy_id: str
    strategy_version: str
    symbol: str
    as_of: date
    direction: SignalDirection
    conviction: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    reference_price: float = Field(gt=0)
    invalidation_price: float | None = Field(default=None, gt=0)
    invalidation_condition: str
    feature_snapshot_hash: str


class Strategy(ABC):
    """Pure signal generator bound to a :class:`StrategySpec`.

    Implementations must be deterministic functions of their inputs: no I/O,
    no wall-clock access, no randomness without a seed recorded in the spec.
    """

    def __init__(self, spec: StrategySpec) -> None:
        self.spec = spec

    @abstractmethod
    def generate_signals(
        self, history: dict[str, list[MarketBar]], as_of: date
    ) -> list[SignalProposal]:
        """Produce proposals from as-of history (one entry per universe symbol).

        ``history[symbol]`` contains only bars with ``trading_day <= as_of``;
        callers guarantee point-in-time discipline, implementations must not
        assume future bars exist.
        """
        raise NotImplementedError

    def _feature_hash(self, payload: dict[str, Any]) -> str:
        """Hash the exact feature values a signal was computed from."""
        return content_hash(payload)


def closes(bars: list[MarketBar]) -> list[float]:
    """Convenience accessor used by concrete strategies."""
    return [b.close for b in bars]
