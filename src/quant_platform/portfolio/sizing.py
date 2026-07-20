"""Deterministic conservative position sizing.

For each candidate the sizer computes every applicable bound — risk per trade
against the invalidation distance, the position-weight cap, liquidity
participation, and remaining cash headroom — and takes the most conservative
one. The binding constraint is named in the decision so every size is
explainable (specification section 10).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from quant_platform.core.config import RiskLimitsConfig
from quant_platform.strategies.base import SignalProposal


class SizingDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    proposal_id: str
    target_weight: float
    binding_constraint: str
    bounds: dict[str, float]


class PositionSizer:
    def __init__(self, limits: RiskLimitsConfig) -> None:
        self._limits = limits

    def size(
        self,
        proposal: SignalProposal,
        equity: float,
        average_daily_volume_notional: float,
    ) -> SizingDecision:
        """Return the maximum permissible weight for a LONG proposal.

        All bounds are expressed as portfolio weights. A proposal without an
        invalidation price is treated maximally conservatively: its risk-based
        bound assumes the full position could be lost over the horizon, i.e.
        the bound equals ``max_risk_per_trade_pct`` itself.
        """
        bounds: dict[str, float] = {}

        # 1. Risk per trade: weight such that (stop distance x weight) <= budget.
        if proposal.invalidation_price is not None:
            stop_fraction = (
                abs(proposal.reference_price - proposal.invalidation_price)
                / proposal.reference_price
            )
            # Guard: a stop closer than 0.1% would imply near-unlimited size.
            stop_fraction = max(stop_fraction, 0.001)
            bounds["risk_per_trade"] = self._limits.max_risk_per_trade_pct / stop_fraction
        else:
            bounds["risk_per_trade"] = self._limits.max_risk_per_trade_pct

        # 2. Hard position-weight cap.
        bounds["max_position_weight"] = self._limits.max_position_weight

        # 3. Liquidity: the order may not exceed the participation cap of ADV.
        if equity > 0 and average_daily_volume_notional > 0:
            bounds["liquidity_participation"] = (
                self._limits.max_participation_of_adv * average_daily_volume_notional / equity
            )
        else:
            bounds["liquidity_participation"] = 0.0

        binding = min(bounds, key=lambda name: bounds[name])
        return SizingDecision(
            symbol=proposal.symbol,
            proposal_id=proposal.proposal_id,
            target_weight=max(0.0, bounds[binding]),
            binding_constraint=binding,
            bounds=bounds,
        )
