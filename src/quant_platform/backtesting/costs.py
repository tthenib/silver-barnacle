"""Conservative execution cost model shared by backtests and simulation.

Total cost of a fill = commission + notional fees + half-spread slippage +
market impact scaled by participation of average daily volume. Parameters are
policy (config/policies/costs.yaml); deliberately pessimistic defaults are a
bias control, because understated costs are a release-blocking defect.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from quant_platform.core.config import CostModelConfig


class CostBreakdown(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    commission: float
    fees: float
    slippage: float
    impact: float

    @property
    def total(self) -> float:
        return self.commission + self.fees + self.slippage + self.impact


class CostModel:
    def __init__(self, config: CostModelConfig) -> None:
        self._config = config

    def estimate(self, quantity: float, price: float, average_daily_volume: float) -> CostBreakdown:
        """Estimate all-in friction for trading ``quantity`` shares at ``price``.

        ``average_daily_volume`` is in shares; zero ADV means impact is
        assessed at the full-participation rate (the conservative branch).
        """
        shares = abs(quantity)
        notional = shares * price
        participation = shares / average_daily_volume if average_daily_volume > 0 else 1.0
        participation = min(participation, 1.0)
        return CostBreakdown(
            commission=shares * self._config.commission_per_share,
            fees=notional * self._config.fee_bps / 10_000.0,
            slippage=notional * self._config.half_spread_bps / 10_000.0,
            impact=notional
            * self._config.impact_bps_at_full_participation
            * participation
            / 10_000.0,
        )
