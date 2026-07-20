"""Dual moving-average trend strategy (long/flat).

Assumption (specification section 9, "Trend"): price persistence can exceed
noise. The strategy is long a symbol while its fast moving average is above
its slow moving average, flat otherwise. Known failure mode: whipsaws in
range-bound markets — the invalidation condition is the cross-back.
"""

from __future__ import annotations

from datetime import date

from quant_platform.data.contracts import MarketBar
from quant_platform.strategies.base import (
    SignalDirection,
    SignalProposal,
    Strategy,
    StrategySpec,
    closes,
)

REQUIRED_PARAMETERS = ("fast_window", "slow_window")


def build_spec(
    universe: tuple[str, ...],
    fast_window: int = 20,
    slow_window: int = 50,
    version: str = "1.0.0",
) -> StrategySpec:
    if fast_window >= slow_window:
        raise ValueError("fast_window must be shorter than slow_window")
    return StrategySpec(
        strategy_id="ma_trend",
        version=version,
        family="trend",
        universe=universe,
        parameters={"fast_window": fast_window, "slow_window": slow_window},
        horizon_days=slow_window,
        invalidation_policy="exit when fast MA crosses back below slow MA",
        no_trade_conditions=("insufficient history for slow window",),
    )


class MovingAverageTrendStrategy(Strategy):
    def generate_signals(
        self, history: dict[str, list[MarketBar]], as_of: date
    ) -> list[SignalProposal]:
        fast_window = int(self.spec.parameters["fast_window"])
        slow_window = int(self.spec.parameters["slow_window"])
        proposals: list[SignalProposal] = []
        for symbol in self.spec.universe:
            bars = history.get(symbol, [])
            if len(bars) < slow_window:
                continue  # declared no-trade condition: insufficient history
            price_series = closes(bars)
            fast_ma = sum(price_series[-fast_window:]) / fast_window
            slow_ma = sum(price_series[-slow_window:]) / slow_window
            last_price = price_series[-1]
            is_long = fast_ma > slow_ma
            # Conviction scales with the normalized MA spread, capped at 1.
            spread = abs(fast_ma - slow_ma) / slow_ma
            features = {
                "fast_ma": fast_ma,
                "slow_ma": slow_ma,
                "last_price": last_price,
                "as_of": as_of.isoformat(),
            }
            proposals.append(
                SignalProposal(
                    strategy_id=self.spec.strategy_id,
                    strategy_version=self.spec.version,
                    symbol=symbol,
                    as_of=as_of,
                    direction=SignalDirection.LONG if is_long else SignalDirection.FLAT,
                    conviction=min(1.0, spread * 20.0) if is_long else 0.0,
                    uncertainty=0.5,
                    reference_price=last_price,
                    invalidation_price=slow_ma if is_long else None,
                    invalidation_condition="fast MA crosses below slow MA",
                    feature_snapshot_hash=self._feature_hash(features),
                )
            )
        return proposals
