"""End-to-end demonstration of the simulated platform lifecycle.

Runs the full pipeline on synthetic data — validation, research claims,
signals, sizing, allocation, risk review, backtest, walk-forward — and then
executes one intent through the gateway against the simulated broker,
reconciles it, and verifies the audit chain. Everything is deterministic.

Usage: python scripts/run_simulation.py
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from quant_platform.backtesting.costs import CostModel
from quant_platform.backtesting.engine import BacktestConfig, BacktestEngine
from quant_platform.backtesting.walk_forward import WalkForwardRunner, rolling_windows
from quant_platform.core.audit import AuditLedger
from quant_platform.core.clock import FrozenClock
from quant_platform.core.config import ExecutionMode, load_platform_config
from quant_platform.core.logging import configure_logging, get_logger
from quant_platform.core.metadata import new_id
from quant_platform.data.contracts import DataEligibility
from quant_platform.data.store import MarketDataStore
from quant_platform.data.synthetic import SyntheticMarketDataProvider
from quant_platform.data.validation import BarSeriesValidator
from quant_platform.execution.approvals import ApprovalService
from quant_platform.execution.broker import VerifiedCapabilities
from quant_platform.execution.gateway import ExecutionGateway
from quant_platform.execution.intents import IntentLifecycle, IntentState, OrderIntent, OrderSide
from quant_platform.execution.reconciliation import Reconciler
from quant_platform.execution.simulated_broker import SimulatedBroker
from quant_platform.memory.journal import TradeJournal
from quant_platform.portfolio.accounting import PortfolioState
from quant_platform.portfolio.allocator import Allocator
from quant_platform.portfolio.sizing import PositionSizer
from quant_platform.risk.circuit_breakers import CircuitBreaker
from quant_platform.risk.engine import RiskEngine
from quant_platform.strategies import moving_average_trend

UNIVERSE = ("AAA", "BBB", "CCC", "DDD")
DATA_START = date(2024, 1, 1)
DATA_END = date(2025, 6, 30)
INITIAL_CASH = 100_000.0


def main() -> None:
    configure_logging()
    log = get_logger("simulation")
    clock = FrozenClock(datetime(2025, 7, 1, 12, 0, tzinfo=UTC))
    config = load_platform_config(Path(__file__).resolve().parents[1] / "config")
    audit = AuditLedger(clock=clock)
    journal = TradeJournal(clock=clock)
    correlation_id = new_id("case")

    # --- Data: ingest synthetic bars and validate. ------------------------------
    provider = SyntheticMarketDataProvider(seed=42, clock=clock)
    validator = BarSeriesValidator()
    store = MarketDataStore(required_eligibility=DataEligibility.VALID_FOR_BACKTEST)
    for symbol in UNIVERSE:
        series, report = validator.validate(
            symbol, provider.get_daily_bars(symbol, DATA_START, DATA_END)
        )
        store.add(series)
        log.info("validated %s", symbol, extra={"fields": {"eligibility": series.eligibility}})

    # --- Backtest and walk-forward. ---------------------------------------------
    engine = BacktestEngine(
        store=store,
        sizer=PositionSizer(config.risk_limits),
        allocator=Allocator(config.risk_limits),
        risk_engine=RiskEngine(config.risk_limits),
        cost_model=CostModel(config.costs),
    )
    backtest_config = BacktestConfig(
        start=date(2024, 6, 1), end=date(2025, 6, 1), initial_cash=INITIAL_CASH
    )
    spec = moving_average_trend.build_spec(UNIVERSE, fast_window=10, slow_window=30)
    result = engine.run(moving_average_trend.MovingAverageTrendStrategy(spec), backtest_config)
    print("\n=== Backtest (synthetic data) ===")
    print(f"strategy        : {result.strategy_id}@{result.strategy_version}")
    print(f"total return    : {result.metrics.total_return:+.2%}")
    print(f"max drawdown    : {result.metrics.max_drawdown:.2%}")
    print(f"sharpe (rf=0)   : {result.metrics.sharpe_ratio_rf0:.2f}")
    print(f"trades / costs  : {result.metrics.trade_count} / ${result.metrics.total_costs:,.2f}")
    for warning in result.warnings:
        print(f"warning         : {warning}")

    candidates = [
        moving_average_trend.build_spec(UNIVERSE, fast_window=5, slow_window=20),
        moving_average_trend.build_spec(UNIVERSE, fast_window=20, slow_window=60),
    ]
    windows = rolling_windows(date(2024, 3, 1), date(2025, 6, 1), train_days=180, test_days=90)
    wf = WalkForwardRunner(engine).run(
        candidates,
        factory=moving_average_trend.MovingAverageTrendStrategy,
        windows=windows,
        base_config=backtest_config,
    )
    print("\n=== Walk-forward ===")
    print(f"windows         : {len(wf.windows)}")
    print(
        f"objective decay : {wf.objective_decay:+.3f} (train {wf.mean_train_objective:+.3f} "
        f"-> test {wf.mean_test_objective:+.3f})"
    )
    print(f"selection stable: {wf.selection_stable}")

    # --- One intent through the execution plane. --------------------------------
    as_of = DATA_END
    strategy = moving_average_trend.MovingAverageTrendStrategy(spec)
    history = {s: store.bars_as_of(s, as_of) for s in UNIVERSE}
    proposals = strategy.generate_signals(history, as_of)
    prices = {p.symbol: p.reference_price for p in proposals}
    sizer = PositionSizer(config.risk_limits)
    sizings = {
        p.proposal_id: sizer.size(
            p,
            equity=INITIAL_CASH,
            average_daily_volume_notional=store.average_daily_volume(p.symbol, as_of)
            * prices[p.symbol],
        )
        for p in proposals
    }
    targets = Allocator(config.risk_limits).build_targets(proposals, sizings)
    decision = RiskEngine(config.risk_limits).evaluate(
        targets, PortfolioState(cash=INITIAL_CASH), prices, daily_pnl_pct=0.0, drawdown_pct=0.0
    )
    journal.record(correlation_id, "risk_review", {"passed": decision.passed})

    candidates_weights = [(s, w) for s, w in decision.approved_weights.items() if w > 0]
    if not candidates_weights:
        print("\nNo positive-weight target today; no intent created.")
        return
    symbol, weight = max(candidates_weights, key=lambda kv: kv[1])
    intent = OrderIntent(
        correlation_id=correlation_id,
        account_alias="sim-account",
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=round(weight * INITIAL_CASH / prices[symbol], 4),
        rationale=f"ma_trend long {symbol} at approved weight {weight:.3f}",
        max_acceptable_loss=INITIAL_CASH * config.risk_limits.max_risk_per_trade_pct,
        expires_at_utc=clock.now() + timedelta(minutes=10),
        trading_day=as_of,
    )
    lifecycle = IntentLifecycle(audit)
    lifecycle.open(intent)
    lifecycle.transition(intent.intent_id, IntentState.VALIDATED, "pipeline", "schema ok")
    lifecycle.transition(intent.intent_id, IntentState.RISK_APPROVED, "risk_engine", "risk passed")

    approvals = ApprovalService(config.execution_policy, audit, clock)
    approval = approvals.grant(
        intent, decision, ExecutionMode.SIMULATION, "simulation-policy", approver_is_human=False
    )
    broker = SimulatedBroker(clock, initial_cash=INITIAL_CASH)
    broker.set_reference_price(symbol, prices[symbol])
    gateway = ExecutionGateway(
        broker=broker,
        capabilities=VerifiedCapabilities(broker.capabilities(), config.broker_allowlist),
        lifecycle=lifecycle,
        approvals=approvals,
        breaker=CircuitBreaker(audit),
        policy=config.execution_policy,
        audit=audit,
        clock=clock,
        mode=config.execution_policy.default_mode,
    )
    gateway.submit(intent, approval)
    report = Reconciler(broker, lifecycle, audit).reconcile()
    audit.verify_chain()

    print("\n=== Execution (simulated) ===")
    print(f"intent          : {intent.side} {intent.quantity} {intent.symbol}")
    print(f"final state     : {lifecycle.state_of(intent.intent_id)}")
    print(f"reconciliation  : clean={report.clean}")
    print(f"audit records   : {sum(1 for _ in audit.records())} (chain verified)")


if __name__ == "__main__":
    main()
