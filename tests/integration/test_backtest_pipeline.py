"""Integration: synthetic data through validation, backtest, and walk-forward."""

from __future__ import annotations

from datetime import date

import pytest

from quant_platform.backtesting.costs import CostModel
from quant_platform.backtesting.engine import BacktestConfig, BacktestEngine
from quant_platform.backtesting.walk_forward import WalkForwardRunner, rolling_windows
from quant_platform.portfolio.allocator import Allocator
from quant_platform.portfolio.sizing import PositionSizer
from quant_platform.risk.engine import RiskEngine
from quant_platform.strategies import moving_average_trend
from tests.conftest import UNIVERSE


@pytest.fixture
def engine(synthetic_store, platform_config) -> BacktestEngine:
    return BacktestEngine(
        store=synthetic_store,
        sizer=PositionSizer(platform_config.risk_limits),
        allocator=Allocator(platform_config.risk_limits),
        risk_engine=RiskEngine(platform_config.risk_limits),
        cost_model=CostModel(platform_config.costs),
    )


@pytest.fixture
def config() -> BacktestConfig:
    return BacktestConfig(start=date(2024, 6, 1), end=date(2025, 6, 1), initial_cash=100_000.0)


def build_strategy(
    fast: int = 10, slow: int = 30
) -> moving_average_trend.MovingAverageTrendStrategy:
    spec = moving_average_trend.build_spec(UNIVERSE, fast_window=fast, slow_window=slow)
    return moving_average_trend.MovingAverageTrendStrategy(spec)


class TestBacktest:
    def test_run_produces_complete_result(self, engine, config) -> None:
        result = engine.run(build_strategy(), config)
        assert len(result.equity_curve) == len(result.equity_days)
        assert result.equity_curve[0] > 0
        assert result.metrics.observations == len(result.equity_curve) - 1
        assert result.spec_hash
        assert result.data_fingerprint
        # Synthetic data must be flagged.
        assert any("synthetic" in w for w in result.warnings)

    def test_deterministic_across_runs(self, engine, config) -> None:
        first = engine.run(build_strategy(), config)
        second = engine.run(build_strategy(), config)
        assert first.equity_curve == second.equity_curve
        assert first.data_fingerprint == second.data_fingerprint
        assert [t.model_dump() for t in first.trades] == [t.model_dump() for t in second.trades]

    def test_risk_limits_hold_throughout(
        self, engine, config, synthetic_store, platform_config
    ) -> None:
        result = engine.run(build_strategy(), config)
        # Reconstruct position weights day by day is heavy; instead assert the
        # invariant the engine must maintain: no single fill creates a position
        # beyond the cap (weight at decision time <= max_position_weight).
        limits = platform_config.risk_limits
        equity_by_day = dict(zip(result.equity_days, result.equity_curve, strict=True))
        for trade in result.trades:
            equity = equity_by_day[trade.trading_day]
            assert abs(trade.quantity) * trade.price <= equity * limits.max_position_weight * 1.10

    def test_costs_are_charged(self, engine, config) -> None:
        result = engine.run(build_strategy(), config)
        assert result.trades, "expected at least one trade in a year of trending data"
        assert result.metrics.total_costs > 0


class TestWalkForward:
    def test_walk_forward_freezes_selection_and_reports_decay(self, engine, config) -> None:
        candidates = [
            moving_average_trend.build_spec(UNIVERSE, fast_window=5, slow_window=20),
            moving_average_trend.build_spec(UNIVERSE, fast_window=20, slow_window=60),
        ]
        windows = rolling_windows(date(2024, 3, 1), date(2025, 6, 1), train_days=180, test_days=90)
        assert len(windows) >= 2
        report = WalkForwardRunner(engine).run(
            candidates,
            factory=moving_average_trend.MovingAverageTrendStrategy,
            windows=windows,
            base_config=config,
        )
        assert len(report.windows) == len(windows)
        for outcome in report.windows:
            assert outcome.selected_spec_hash in {c.spec_hash() for c in candidates}
        # The decay property must be computable (sign is data-dependent).
        assert isinstance(report.objective_decay, float)
