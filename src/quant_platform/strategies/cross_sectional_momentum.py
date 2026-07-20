"""Cross-sectional momentum strategy (long the top-ranked names).

Assumption (specification section 9, "Momentum"): relative strength persists
briefly. Each rebalance the universe is ranked by trailing return excluding
the most recent ``skip`` days (to avoid short-term reversal contamination);
the top ``top_n`` names get long proposals. Known failure modes: momentum
crashes and crowding — conviction is uniform, and risk limits do the sizing.
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


def build_spec(
    universe: tuple[str, ...],
    lookback: int = 60,
    skip: int = 5,
    top_n: int = 3,
    version: str = "1.0.0",
) -> StrategySpec:
    if skip >= lookback:
        raise ValueError("skip must be shorter than lookback")
    if top_n < 1 or top_n > len(universe):
        raise ValueError("top_n must be within the universe size")
    return StrategySpec(
        strategy_id="xs_momentum",
        version=version,
        family="momentum",
        universe=universe,
        parameters={"lookback": lookback, "skip": skip, "top_n": top_n},
        horizon_days=lookback // 2,
        invalidation_policy="exit when the symbol drops out of the top ranks",
        no_trade_conditions=("insufficient history for lookback",),
    )


class CrossSectionalMomentumStrategy(Strategy):
    def generate_signals(
        self, history: dict[str, list[MarketBar]], as_of: date
    ) -> list[SignalProposal]:
        lookback = int(self.spec.parameters["lookback"])
        skip = int(self.spec.parameters["skip"])
        top_n = int(self.spec.parameters["top_n"])

        scored: list[tuple[str, float, float]] = []  # (symbol, score, last_price)
        for symbol in self.spec.universe:
            bars = history.get(symbol, [])
            if len(bars) < lookback + skip + 1:
                continue  # declared no-trade condition
            series = closes(bars)
            window_end = series[-1 - skip]  # exclude the most recent `skip` days
            window_start = series[-1 - skip - lookback]
            score = window_end / window_start - 1.0
            scored.append((symbol, score, series[-1]))

        ranked = sorted(scored, key=lambda item: item[1], reverse=True)
        winners = {symbol for symbol, _, _ in ranked[:top_n]}

        proposals: list[SignalProposal] = []
        for symbol, score, last_price in ranked:
            is_winner = symbol in winners
            features = {"score": score, "last_price": last_price, "as_of": as_of.isoformat()}
            proposals.append(
                SignalProposal(
                    strategy_id=self.spec.strategy_id,
                    strategy_version=self.spec.version,
                    symbol=symbol,
                    as_of=as_of,
                    direction=SignalDirection.LONG if is_winner else SignalDirection.FLAT,
                    conviction=1.0 / top_n if is_winner else 0.0,
                    uncertainty=0.5,
                    reference_price=last_price,
                    invalidation_price=None,  # rank-based exit; no price stop by design
                    invalidation_condition="symbol drops out of top ranks at next rebalance",
                    feature_snapshot_hash=self._feature_hash(features),
                )
            )
        return proposals
