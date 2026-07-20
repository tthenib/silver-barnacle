"""Z-score mean-reversion strategy (long-only entries on oversold overshoot).

Assumption (specification section 9, "Mean reversion"): temporary deviations
revert. The strategy proposes a long when the close falls into the band
between ``entry_z`` and ``stop_z`` standard deviations below its rolling
mean; a deviation already beyond ``stop_z`` is treated as pre-invalidated
(structural repricing, the known failure mode) and produces no entry. Flat
is proposed once price recovers to the mean.
"""

from __future__ import annotations

import math
from datetime import date

from quant_platform.data.contracts import MarketBar
from quant_platform.strategies.base import (
    SignalDirection,
    SignalProposal,
    Strategy,
    StrategySpec,
    closes,
)


def build_spec(
    universe: tuple[str, ...],
    lookback: int = 20,
    entry_z: float = 2.0,
    stop_z: float = 3.5,
    version: str = "1.0.0",
) -> StrategySpec:
    if stop_z <= entry_z:
        raise ValueError("stop_z must lie beyond entry_z")
    return StrategySpec(
        strategy_id="zscore_reversion",
        version=version,
        family="mean_reversion",
        universe=universe,
        parameters={"lookback": lookback, "entry_z": entry_z, "stop_z": stop_z},
        horizon_days=lookback,
        invalidation_policy="stop out beyond stop_z; thesis is wrong if deviation extends",
        no_trade_conditions=("insufficient history", "zero variance window"),
    )


class ZScoreMeanReversionStrategy(Strategy):
    def generate_signals(
        self, history: dict[str, list[MarketBar]], as_of: date
    ) -> list[SignalProposal]:
        lookback = int(self.spec.parameters["lookback"])
        entry_z = float(self.spec.parameters["entry_z"])
        stop_z = float(self.spec.parameters["stop_z"])
        proposals: list[SignalProposal] = []
        for symbol in self.spec.universe:
            bars = history.get(symbol, [])
            if len(bars) < lookback:
                continue  # declared no-trade condition
            window = closes(bars)[-lookback:]
            mean = sum(window) / lookback
            variance = sum((p - mean) ** 2 for p in window) / lookback
            if variance == 0.0:
                continue  # declared no-trade condition
            std = math.sqrt(variance)
            last_price = window[-1]
            z = (last_price - mean) / std
            # Enter only inside the band (-stop_z, -entry_z]: a deviation
            # already beyond stop_z means the thesis is pre-invalidated —
            # proposing a long there would place the stop above the entry.
            oversold = -stop_z < z <= -entry_z
            features = {
                "mean": mean,
                "std": std,
                "z": z,
                "last_price": last_price,
                "as_of": as_of.isoformat(),
            }
            proposals.append(
                SignalProposal(
                    strategy_id=self.spec.strategy_id,
                    strategy_version=self.spec.version,
                    symbol=symbol,
                    as_of=as_of,
                    direction=SignalDirection.LONG if oversold else SignalDirection.FLAT,
                    conviction=min(1.0, (abs(z) - entry_z) / entry_z) if oversold else 0.0,
                    uncertainty=0.6,
                    reference_price=last_price,
                    invalidation_price=mean - stop_z * std if oversold else None,
                    invalidation_condition=f"z-score extends beyond -{stop_z}",
                    feature_snapshot_hash=self._feature_hash(features),
                )
            )
        return proposals
