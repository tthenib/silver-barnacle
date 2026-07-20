"""Strategy framework: signal correctness, no-trade conditions, lifecycle registry."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from quant_platform.core.audit import AuditLedger
from quant_platform.core.errors import StateTransitionError
from quant_platform.data.contracts import MarketBar
from quant_platform.strategies import cross_sectional_momentum, mean_reversion, moving_average_trend
from quant_platform.strategies.base import SignalDirection
from quant_platform.strategies.registry import StrategyLifecycle, StrategyRegistry
from tests.conftest import make_bar

AS_OF = date(2025, 6, 30)


def trending_series(count: int, daily_move: float, start_price: float = 100.0) -> list[MarketBar]:
    bars = []
    day = date(2025, 1, 6)
    price = start_price
    while len(bars) < count:
        if day.weekday() < 5:
            bars.append(make_bar(trading_day=day, close=price))
            price *= 1.0 + daily_move
        day += timedelta(days=1)
    return bars


class TestMovingAverageTrend:
    def test_uptrend_yields_long(self) -> None:
        spec = moving_average_trend.build_spec(("AAA",), fast_window=5, slow_window=20)
        strategy = moving_average_trend.MovingAverageTrendStrategy(spec)
        signals = strategy.generate_signals({"AAA": trending_series(40, +0.01)}, AS_OF)
        assert len(signals) == 1
        assert signals[0].direction is SignalDirection.LONG
        assert signals[0].invalidation_price is not None

    def test_downtrend_yields_flat(self) -> None:
        spec = moving_average_trend.build_spec(("AAA",), fast_window=5, slow_window=20)
        strategy = moving_average_trend.MovingAverageTrendStrategy(spec)
        signals = strategy.generate_signals({"AAA": trending_series(40, -0.01)}, AS_OF)
        assert signals[0].direction is SignalDirection.FLAT

    def test_insufficient_history_is_no_trade(self) -> None:
        spec = moving_average_trend.build_spec(("AAA",), fast_window=5, slow_window=20)
        strategy = moving_average_trend.MovingAverageTrendStrategy(spec)
        assert strategy.generate_signals({"AAA": trending_series(10, 0.01)}, AS_OF) == []

    def test_invalid_windows_rejected(self) -> None:
        with pytest.raises(ValueError):
            moving_average_trend.build_spec(("AAA",), fast_window=50, slow_window=20)


class TestMeanReversion:
    def test_oversold_yields_long_with_stop(self) -> None:
        # A single drop on a flat window lands at z ≈ -4.36; with stop_z=5
        # that is inside the (-stop_z, -entry_z] entry band.
        bars = trending_series(30, 0.0)
        crash_day = bars[-1].trading_day + timedelta(days=1)
        bars.append(make_bar(trading_day=crash_day, close=bars[-1].close * 0.90))
        spec = mean_reversion.build_spec(("AAA",), lookback=20, entry_z=2.0, stop_z=5.0)
        strategy = mean_reversion.ZScoreMeanReversionStrategy(spec)
        signals = strategy.generate_signals({"AAA": bars}, AS_OF)
        assert signals[0].direction is SignalDirection.LONG
        assert signals[0].invalidation_price is not None
        assert signals[0].invalidation_price < signals[0].reference_price

    def test_deviation_beyond_stop_is_pre_invalidated(self) -> None:
        # Same crash, but with the default stop_z=3.5 the z ≈ -4.36 deviation
        # is beyond the stop: no entry may be proposed.
        bars = trending_series(30, 0.0)
        crash_day = bars[-1].trading_day + timedelta(days=1)
        bars.append(make_bar(trading_day=crash_day, close=bars[-1].close * 0.90))
        spec = mean_reversion.build_spec(("AAA",), lookback=20, entry_z=2.0, stop_z=3.5)
        strategy = mean_reversion.ZScoreMeanReversionStrategy(spec)
        signals = strategy.generate_signals({"AAA": bars}, AS_OF)
        assert signals[0].direction is SignalDirection.FLAT

    def test_flat_market_yields_flat(self) -> None:
        # Slight drift avoids the zero-variance no-trade condition.
        spec = mean_reversion.build_spec(("AAA",), lookback=20)
        strategy = mean_reversion.ZScoreMeanReversionStrategy(spec)
        signals = strategy.generate_signals({"AAA": trending_series(30, 0.0005)}, AS_OF)
        assert signals[0].direction is SignalDirection.FLAT

    def test_zero_variance_is_no_trade(self) -> None:
        spec = mean_reversion.build_spec(("AAA",), lookback=20)
        strategy = mean_reversion.ZScoreMeanReversionStrategy(spec)
        assert strategy.generate_signals({"AAA": trending_series(30, 0.0)}, AS_OF) == []


class TestCrossSectionalMomentum:
    def test_top_ranked_symbols_are_long(self) -> None:
        universe = ("AAA", "BBB", "CCC")
        spec = cross_sectional_momentum.build_spec(universe, lookback=20, skip=2, top_n=1)
        strategy = cross_sectional_momentum.CrossSectionalMomentumStrategy(spec)
        history = {
            "AAA": trending_series(30, +0.02),
            "BBB": trending_series(30, +0.001),
            "CCC": trending_series(30, -0.01),
        }
        signals = strategy.generate_signals(history, AS_OF)
        by_symbol = {s.symbol: s for s in signals}
        assert by_symbol["AAA"].direction is SignalDirection.LONG
        assert by_symbol["BBB"].direction is SignalDirection.FLAT
        assert by_symbol["CCC"].direction is SignalDirection.FLAT


class TestRegistry:
    def _registry(self) -> tuple[StrategyRegistry, object]:
        audit = AuditLedger()
        registry = StrategyRegistry(audit)
        spec = moving_average_trend.build_spec(("AAA",))
        strategy = moving_average_trend.MovingAverageTrendStrategy(spec)
        registry.register(strategy, StrategyLifecycle.RESEARCH)
        return registry, strategy

    def test_stepwise_promotion(self) -> None:
        registry, strategy = self._registry()
        registry.promote(strategy, StrategyLifecycle.BACKTESTED, evidence="backtest-123")
        assert registry.state_of(strategy) is StrategyLifecycle.BACKTESTED

    def test_skipping_states_is_rejected(self) -> None:
        registry, strategy = self._registry()
        with pytest.raises(StateTransitionError):
            registry.promote(strategy, StrategyLifecycle.PAPER, evidence="x")

    def test_promotion_requires_evidence(self) -> None:
        registry, strategy = self._registry()
        with pytest.raises(StateTransitionError):
            registry.promote(strategy, StrategyLifecycle.BACKTESTED, evidence="  ")

    def test_demotion_always_allowed(self) -> None:
        registry, strategy = self._registry()
        registry.demote(strategy, StrategyLifecycle.REJECTED, reason="failed review")
        assert registry.state_of(strategy) is StrategyLifecycle.REJECTED

    def test_simulation_eligibility(self) -> None:
        registry, strategy = self._registry()
        assert registry.eligible_for_simulation() == []
        registry.promote(strategy, StrategyLifecycle.BACKTESTED, evidence="backtest-123")
        assert registry.eligible_for_simulation() == [strategy]
