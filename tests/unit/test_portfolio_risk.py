"""Portfolio sizing, allocation, accounting, and the risk engine."""

from __future__ import annotations

from datetime import date

import pytest

from quant_platform.core.audit import AuditLedger
from quant_platform.core.config import RiskLimitsConfig
from quant_platform.core.errors import PolicyViolationError
from quant_platform.portfolio.accounting import PortfolioState, Position
from quant_platform.portfolio.allocator import Allocator, TargetPortfolio
from quant_platform.portfolio.sizing import PositionSizer
from quant_platform.risk.circuit_breakers import (
    BreakerState,
    CircuitBreaker,
    KillSwitch,
    TripReason,
)
from quant_platform.risk.engine import RiskEngine, RuleOutcome
from quant_platform.strategies.base import SignalDirection, SignalProposal

LIMITS = RiskLimitsConfig(
    policy_version="test-1",
    max_position_weight=0.10,
    max_gross_exposure=1.0,
    max_risk_per_trade_pct=0.01,
    max_daily_loss_pct=0.03,
    max_drawdown_pct=0.15,
    min_cash_reserve_pct=0.05,
    max_participation_of_adv=0.05,
    max_positions=3,
)


def proposal(
    symbol: str = "AAA",
    direction: SignalDirection = SignalDirection.LONG,
    conviction: float = 0.8,
    reference_price: float = 100.0,
    invalidation_price: float | None = 95.0,
) -> SignalProposal:
    return SignalProposal(
        strategy_id="test",
        strategy_version="1",
        symbol=symbol,
        as_of=date(2025, 6, 30),
        direction=direction,
        conviction=conviction,
        uncertainty=0.5,
        reference_price=reference_price,
        invalidation_price=invalidation_price,
        invalidation_condition="test",
        feature_snapshot_hash="deadbeef",
    )


class TestSizing:
    def test_risk_per_trade_binds_with_wide_stop(self) -> None:
        # 20% stop distance: risk bound = 1% / 20% = 5% < 10% weight cap.
        decision = PositionSizer(LIMITS).size(
            proposal(invalidation_price=80.0), equity=100_000, average_daily_volume_notional=10**9
        )
        assert decision.binding_constraint == "risk_per_trade"
        assert decision.target_weight == pytest.approx(0.05)

    def test_weight_cap_binds_with_tight_stop(self) -> None:
        # 1% stop distance: risk bound = 1.0 > 10% cap.
        decision = PositionSizer(LIMITS).size(
            proposal(invalidation_price=99.0), equity=100_000, average_daily_volume_notional=10**9
        )
        assert decision.binding_constraint == "max_position_weight"
        assert decision.target_weight == pytest.approx(0.10)

    def test_liquidity_binds_for_illiquid_symbol(self) -> None:
        # ADV notional 20k, cap 5% -> 1k -> weight 1% of 100k equity.
        decision = PositionSizer(LIMITS).size(
            proposal(invalidation_price=80.0), equity=100_000, average_daily_volume_notional=20_000
        )
        assert decision.binding_constraint == "liquidity_participation"
        assert decision.target_weight == pytest.approx(0.01)

    def test_missing_invalidation_is_maximally_conservative(self) -> None:
        decision = PositionSizer(LIMITS).size(
            proposal(invalidation_price=None), equity=100_000, average_daily_volume_notional=10**9
        )
        assert decision.target_weight == pytest.approx(LIMITS.max_risk_per_trade_pct)


class TestAllocator:
    def _sizings(self, proposals: list[SignalProposal]) -> dict:
        sizer = PositionSizer(LIMITS)
        return {
            p.proposal_id: sizer.size(p, equity=100_000, average_daily_volume_notional=10**9)
            for p in proposals
        }

    def test_shorts_are_dropped_with_reason(self) -> None:
        proposals = [proposal(symbol="AAA", direction=SignalDirection.SHORT)]
        targets = Allocator(LIMITS).build_targets(proposals, self._sizings(proposals))
        assert targets.weights == {}
        assert "short" in targets.explanation.dropped[0].reason

    def test_max_positions_enforced_by_conviction_rank(self) -> None:
        proposals = [
            proposal(symbol=s, conviction=c)
            for s, c in [("AAA", 0.9), ("BBB", 0.8), ("CCC", 0.7), ("DDD", 0.6)]
        ]
        targets = Allocator(LIMITS).build_targets(proposals, self._sizings(proposals))
        assert set(targets.weights) == {"AAA", "BBB", "CCC"}
        assert targets.explanation.dropped[0].symbol == "DDD"

    def test_flat_proposals_create_explicit_exits(self) -> None:
        proposals = [proposal(symbol="AAA", direction=SignalDirection.FLAT, conviction=0.0)]
        targets = Allocator(LIMITS).build_targets(proposals, {})
        assert targets.weights == {"AAA": 0.0}

    def test_cash_reserve_respected(self) -> None:
        proposals = [proposal(symbol=s) for s in ("AAA", "BBB", "CCC")]
        targets = Allocator(LIMITS).build_targets(proposals, self._sizings(proposals))
        assert targets.explanation.residual_cash_weight >= LIMITS.min_cash_reserve_pct - 1e-9


class TestAccounting:
    def test_buy_then_mark_to_market(self) -> None:
        state = PortfolioState(cash=10_000)
        state = state.apply_fill("AAA", quantity_delta=10, price=100.0, total_cost=5.0)
        assert state.cash == pytest.approx(10_000 - 1_000 - 5)
        assert state.equity({"AAA": 110.0}) == pytest.approx(8_995 + 1_100)

    def test_full_exit_removes_position(self) -> None:
        state = PortfolioState(cash=10_000)
        state = state.apply_fill("AAA", 10, 100.0, 0.0)
        state = state.apply_fill("AAA", -10, 105.0, 0.0)
        assert state.positions == {}
        assert state.cash == pytest.approx(10_000 + 50)


class TestRiskEngine:
    def _targets(self, weights: dict[str, float]) -> TargetPortfolio:
        proposals = [proposal(symbol=s) for s in weights]
        sizer = PositionSizer(LIMITS)
        sizings = {
            p.proposal_id: sizer.size(p, equity=100_000, average_daily_volume_notional=10**9)
            for p in proposals
        }
        built = Allocator(LIMITS).build_targets(proposals, sizings)
        return TargetPortfolio(weights=weights, explanation=built.explanation)

    def test_all_rules_reported(self) -> None:
        decision = RiskEngine(LIMITS).evaluate(
            self._targets({"AAA": 0.05}),
            PortfolioState(cash=100_000),
            prices={"AAA": 100.0},
            daily_pnl_pct=0.0,
            drawdown_pct=0.0,
        )
        assert decision.passed
        assert {e.rule for e in decision.evaluations} >= {
            "max_daily_loss",
            "max_drawdown",
            "max_position_weight",
            "max_gross_exposure",
            "max_positions",
        }

    def test_oversized_position_scaled_to_cap(self) -> None:
        decision = RiskEngine(LIMITS).evaluate(
            self._targets({"AAA": 0.5}),
            PortfolioState(cash=100_000),
            prices={"AAA": 100.0},
            daily_pnl_pct=0.0,
            drawdown_pct=0.0,
        )
        assert decision.approved_weights["AAA"] == pytest.approx(LIMITS.max_position_weight)
        assert any(e.outcome is RuleOutcome.SCALED for e in decision.evaluations)

    def test_daily_loss_breach_blocks_new_risk_but_allows_exits(self) -> None:
        # Currently hold 8% of AAA; targets ask to grow AAA and open BBB.
        state = PortfolioState(
            cash=92_000, positions={"AAA": Position(symbol="AAA", quantity=80, average_cost=100)}
        )
        decision = RiskEngine(LIMITS).evaluate(
            self._targets({"AAA": 0.10, "BBB": 0.05}),
            state,
            prices={"AAA": 100.0, "BBB": 50.0},
            daily_pnl_pct=-0.05,  # beyond the 3% daily loss limit
            drawdown_pct=0.0,
        )
        assert decision.new_risk_blocked
        # AAA may not grow beyond its current weight; BBB may not open.
        assert decision.approved_weights["AAA"] == pytest.approx(0.08)
        assert decision.approved_weights["BBB"] == 0.0


class TestCircuitBreaker:
    def test_trip_blocks_and_reset_requires_human(self) -> None:
        audit = AuditLedger()
        breaker = CircuitBreaker(audit)
        breaker.trip(TripReason.DAILY_LOSS, detail="test", correlation_id="c")
        assert breaker.state is BreakerState.TRIPPED
        with pytest.raises(PolicyViolationError):
            breaker.assert_armed()
        with pytest.raises(PolicyViolationError):
            breaker.reset("", "reason", "c")
        breaker.reset("ops@example.com", "verified losses within tolerance", "c")
        breaker.assert_armed()

    def test_kill_switch_requires_identity(self) -> None:
        audit = AuditLedger()
        breaker = CircuitBreaker(audit)
        switch = KillSwitch(breaker)
        with pytest.raises(PolicyViolationError):
            switch.engage("", "stop", "c")
        switch.engage("ops@example.com", "emergency stop", "c")
        assert breaker.trip_reason is TripReason.MANUAL_KILL_SWITCH
