"""Acceptance: the full simulated lifecycle from data to reconciled fill.

Exercises the pipeline the specification's section 6 defines — data →
validation → research claims → signal → sizing → allocation → risk → intent
→ approval → gateway preflight → simulated broker → reconciliation → journal
— and the failure paths that matter most: ambiguous broker responses,
tripped breakers, and unapproved submissions.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from quant_platform.agents.base import TechnicalStateAgent
from quant_platform.core.audit import AuditLedger
from quant_platform.core.clock import FrozenClock
from quant_platform.core.config import ExecutionMode, PlatformConfig
from quant_platform.core.errors import PolicyViolationError
from quant_platform.core.metadata import new_id
from quant_platform.data.contracts import DataEligibility
from quant_platform.data.store import MarketDataStore
from quant_platform.data.synthetic import SyntheticMarketDataProvider
from quant_platform.data.validation import BarSeriesValidator
from quant_platform.execution.approvals import ApprovalService
from quant_platform.execution.broker import VerifiedCapabilities
from quant_platform.execution.gateway import ExecutionGateway
from quant_platform.execution.intents import (
    IntentLifecycle,
    IntentState,
    OrderIntent,
    OrderSide,
)
from quant_platform.execution.reconciliation import Reconciler
from quant_platform.execution.simulated_broker import InjectedFault, SimulatedBroker
from quant_platform.memory.journal import TradeJournal
from quant_platform.portfolio.allocator import Allocator
from quant_platform.portfolio.sizing import PositionSizer
from quant_platform.risk.circuit_breakers import CircuitBreaker, TripReason
from quant_platform.risk.engine import RiskEngine
from quant_platform.strategies import moving_average_trend
from tests.conftest import DATA_END, DATA_START, UNIVERSE

pytestmark = pytest.mark.acceptance

INITIAL_CASH = 100_000.0


class Harness:
    """Wires the whole platform together the way a composition root would."""

    def __init__(self, clock: FrozenClock, config: PlatformConfig) -> None:
        self.clock = clock
        self.config = config
        self.audit = AuditLedger(clock=clock)
        self.journal = TradeJournal(clock=clock)

        provider = SyntheticMarketDataProvider(seed=42, clock=clock)
        validator = BarSeriesValidator()
        self.store = MarketDataStore(required_eligibility=DataEligibility.VALID_FOR_BACKTEST)
        self.series = {}
        for symbol in UNIVERSE:
            bars = provider.get_daily_bars(symbol, DATA_START, DATA_END)
            series, _ = validator.validate(symbol, bars)
            self.series[symbol] = series
            self.store.add(series)

        self.sizer = PositionSizer(config.risk_limits)
        self.allocator = Allocator(config.risk_limits)
        self.risk = RiskEngine(config.risk_limits)
        self.lifecycle = IntentLifecycle(self.audit)
        self.approvals = ApprovalService(config.execution_policy, self.audit, clock)
        self.breaker = CircuitBreaker(self.audit)
        self.broker = SimulatedBroker(clock, initial_cash=INITIAL_CASH)
        self.gateway = ExecutionGateway(
            broker=self.broker,
            capabilities=VerifiedCapabilities(self.broker.capabilities(), config.broker_allowlist),
            lifecycle=self.lifecycle,
            approvals=self.approvals,
            breaker=self.breaker,
            policy=config.execution_policy,
            audit=self.audit,
            clock=clock,
            mode=config.execution_policy.default_mode,
        )
        self.reconciler = Reconciler(self.broker, self.lifecycle, self.audit)


@pytest.fixture
def harness(clock: FrozenClock, platform_config: PlatformConfig) -> Harness:
    return Harness(clock, platform_config)


def drive_to_approved_intent(harness: Harness, correlation_id: str) -> tuple[OrderIntent, object]:
    """Run data → research → signal → sizing → allocation → risk → intent → approval."""
    as_of = DATA_END
    clock = harness.clock

    # Research: the deterministic agent must produce cited claims.
    agent_output = TechnicalStateAgent(harness.series["AAA"]).run(correlation_id, clock.now())
    assert not agent_output.abstained
    harness.journal.record(correlation_id, "research", {"claims": len(agent_output.claims)})

    # Signals.
    spec = moving_average_trend.build_spec(UNIVERSE, fast_window=10, slow_window=30)
    strategy = moving_average_trend.MovingAverageTrendStrategy(spec)
    history = {s: harness.store.bars_as_of(s, as_of) for s in UNIVERSE}
    proposals = strategy.generate_signals(history, as_of)
    longs = [p for p in proposals if p.direction.value == "LONG"]
    assert longs, "synthetic drift should produce at least one long signal"
    harness.journal.record(correlation_id, "signals", {"count": len(proposals)})

    # Sizing and allocation.
    prices = {p.symbol: p.reference_price for p in proposals}
    sizings = {
        p.proposal_id: harness.sizer.size(
            p,
            equity=INITIAL_CASH,
            average_daily_volume_notional=harness.store.average_daily_volume(p.symbol, as_of)
            * prices[p.symbol],
        )
        for p in proposals
    }
    targets = harness.allocator.build_targets(proposals, sizings)
    harness.journal.record(correlation_id, "allocation", targets.explanation.model_dump())

    # Risk review.
    from quant_platform.portfolio.accounting import PortfolioState

    decision = harness.risk.evaluate(
        targets, PortfolioState(cash=INITIAL_CASH), prices, daily_pnl_pct=0.0, drawdown_pct=0.0
    )
    assert decision.passed
    harness.journal.record(
        correlation_id, "risk_review", {"rules": [e.rule for e in decision.evaluations]}
    )

    # Build the intent for the highest-weight target.
    symbol, weight = max(
        ((s, w) for s, w in decision.approved_weights.items() if w > 0), key=lambda kv: kv[1]
    )
    price = prices[symbol]
    quantity = round(weight * INITIAL_CASH / price, 4)
    intent = OrderIntent(
        correlation_id=correlation_id,
        account_alias="sim-account",
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        rationale=f"ma_trend long {symbol} at weight {weight:.3f}",
        max_acceptable_loss=INITIAL_CASH * harness.config.risk_limits.max_risk_per_trade_pct,
        expires_at_utc=clock.now() + timedelta(minutes=10),
        trading_day=as_of,
    )
    harness.lifecycle.open(intent)
    harness.lifecycle.transition(
        intent.intent_id, IntentState.VALIDATED, actor="pipeline", reason="schema ok"
    )
    harness.lifecycle.transition(
        intent.intent_id, IntentState.RISK_APPROVED, actor="risk_engine", reason="risk passed"
    )

    approval = harness.approvals.grant(
        intent,
        decision,
        ExecutionMode.SIMULATION,
        approver="simulation-policy",
        approver_is_human=False,
    )
    harness.journal.record(correlation_id, "approval", {"approval_id": approval.approval_id})
    harness.broker.set_reference_price(symbol, price)
    return intent, approval


class TestFullLifecycle:
    def test_signal_to_reconciled_fill(self, harness: Harness) -> None:
        correlation_id = new_id("case")
        intent, approval = drive_to_approved_intent(harness, correlation_id)

        harness.gateway.submit(intent, approval)
        assert harness.lifecycle.state_of(intent.intent_id) is IntentState.ACKNOWLEDGED

        report = harness.reconciler.reconcile()
        assert intent.intent_id in report.confirmed_fills
        assert harness.lifecycle.state_of(intent.intent_id) is IntentState.FILLED
        assert report.clean

        # The journal tells the whole story and the audit chain is intact.
        stages = harness.journal.stages_for(correlation_id)
        assert stages == ["research", "signals", "allocation", "risk_review", "approval"]
        harness.audit.verify_chain()
        audit_events = [r.event_type for r in harness.audit.records_for(correlation_id)]
        assert "intent.opened" in audit_events
        assert audit_events.count("intent.transition") >= 4

    def test_ambiguous_submission_blocks_then_reconciles_to_fill(self, harness: Harness) -> None:
        correlation_id = new_id("case")
        intent, approval = drive_to_approved_intent(harness, correlation_id)

        harness.broker.inject_fault(InjectedFault.AMBIGUOUS_THEN_FILLED)
        harness.gateway.submit(intent, approval)
        assert (
            harness.lifecycle.state_of(intent.intent_id)
            is IntentState.BLOCKED_PENDING_RECONCILIATION
        )

        # Reconciliation discovers the broker actually filled it.
        report = harness.reconciler.reconcile()
        assert intent.intent_id in report.confirmed_fills
        assert harness.lifecycle.state_of(intent.intent_id) is IntentState.FILLED
        harness.audit.verify_chain()

    def test_ambiguous_lost_order_reconciles_to_cancelled(self, harness: Harness) -> None:
        correlation_id = new_id("case")
        intent, approval = drive_to_approved_intent(harness, correlation_id)

        harness.broker.inject_fault(InjectedFault.AMBIGUOUS_THEN_NOTHING)
        harness.gateway.submit(intent, approval)
        report = harness.reconciler.reconcile()
        assert intent.intent_id in report.resolved_cancellations
        assert harness.lifecycle.state_of(intent.intent_id) is IntentState.CANCELLED

    def test_tripped_breaker_blocks_submission(self, harness: Harness) -> None:
        correlation_id = new_id("case")
        intent, approval = drive_to_approved_intent(harness, correlation_id)
        harness.breaker.trip(TripReason.DATA_QUALITY, "stale feed", correlation_id)
        with pytest.raises(PolicyViolationError):
            harness.gateway.submit(intent, approval)
        # The intent never reached the broker.
        assert harness.broker.executions() == []

    def test_paused_mode_blocks_submission(self, harness: Harness) -> None:
        correlation_id = new_id("case")
        intent, approval = drive_to_approved_intent(harness, correlation_id)
        harness.gateway.set_mode(
            ExecutionMode.EXECUTION_PAUSED, actor="ops@example.com", reason="deploy window"
        )
        with pytest.raises(PolicyViolationError):
            harness.gateway.submit(intent, approval)

    def test_duplicate_intent_is_suppressed(self, harness: Harness) -> None:
        correlation_id = new_id("case")
        intent, approval = drive_to_approved_intent(harness, correlation_id)
        harness.gateway.submit(intent, approval)

        # A second intent with identical economics shares the fingerprint;
        # while the first is still live the gateway must refuse it.
        duplicate = intent.model_copy(update={"intent_id": new_id("intent")})
        harness.lifecycle.open(duplicate)
        harness.lifecycle.transition(
            duplicate.intent_id, IntentState.VALIDATED, actor="pipeline", reason="schema ok"
        )
        harness.lifecycle.transition(
            duplicate.intent_id, IntentState.RISK_APPROVED, actor="risk_engine", reason="risk ok"
        )
        with pytest.raises(PolicyViolationError):
            harness.gateway.submit(duplicate, approval)
