"""Point-in-time, cost-aware daily backtest engine.

Discipline enforced by construction:

- Signals for day ``t`` see only bars with ``trading_day <= t`` (the store's
  as-of contract), and resulting orders execute at the *next* day's open —
  a decision can never trade on the close it was derived from.
- Every fill pays the shared conservative cost model.
- The risk engine runs between allocation and execution exactly as it does in
  simulation, so a backtest exercises the same controls as live paths.

The result bundle records the strategy spec hash, a data fingerprint, cost
assumptions, and warnings, making the run reproducible and auditable.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.backtesting.costs import CostModel
from quant_platform.backtesting.metrics import BacktestMetrics, compute_metrics, current_drawdown
from quant_platform.core.metadata import content_hash, new_id
from quant_platform.data.store import MarketDataStore
from quant_platform.portfolio.accounting import PortfolioState
from quant_platform.portfolio.allocator import Allocator
from quant_platform.portfolio.sizing import PositionSizer
from quant_platform.risk.engine import RiskEngine
from quant_platform.strategies.base import Strategy


class BacktestConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start: date
    end: date
    initial_cash: float = Field(gt=0)
    rebalance_every_days: int = Field(default=5, gt=0)
    #: Weight changes smaller than this are not traded (turnover control).
    min_rebalance_weight_delta: float = Field(default=0.005, ge=0.0)


class BacktestTrade(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trading_day: date
    symbol: str
    quantity: float
    price: float
    cost: float


class BacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    result_id: str
    strategy_id: str
    strategy_version: str
    spec_hash: str
    data_fingerprint: str
    config: BacktestConfig
    equity_days: tuple[date, ...]
    equity_curve: tuple[float, ...]
    trades: tuple[BacktestTrade, ...]
    metrics: BacktestMetrics
    warnings: tuple[str, ...]


class BacktestEngine:
    """Composable engine; every collaborator is injected, nothing is global."""

    def __init__(
        self,
        store: MarketDataStore,
        sizer: PositionSizer,
        allocator: Allocator,
        risk_engine: RiskEngine,
        cost_model: CostModel,
    ) -> None:
        self._store = store
        self._sizer = sizer
        self._allocator = allocator
        self._risk = risk_engine
        self._costs = cost_model

    def run(self, strategy: Strategy, config: BacktestConfig) -> BacktestResult:
        universe = list(strategy.spec.universe)
        days = self._store.trading_days(config.start, config.end)
        if len(days) < 2:
            raise ValueError("backtest range must contain at least two trading days")

        state = PortfolioState(cash=config.initial_cash)
        equity_days: list[date] = []
        equity_curve: list[float] = []
        trades: list[BacktestTrade] = []
        total_costs = 0.0
        traded_notional = 0.0
        pending_weights: dict[str, float] | None = None
        warnings = self._data_warnings(universe)

        for day_index, day in enumerate(days):
            opens = self._prices(universe, day, field="open")
            closes = self._prices(universe, day, field="close")

            # 1. Execute weights decided on the previous rebalance day at today's open.
            if pending_weights is not None:
                state, day_trades, day_costs, day_notional = self._execute_rebalance(
                    state, pending_weights, opens, day, config
                )
                trades.extend(day_trades)
                total_costs += day_costs
                traded_notional += day_notional
                pending_weights = None

            # 2. Mark to market at the close.
            equity = state.equity(closes)
            equity_days.append(day)
            equity_curve.append(equity)

            # 3. On rebalance days, decide targets from as-of history for
            #    execution at the next open.
            is_last_day = day_index == len(days) - 1
            if day_index % config.rebalance_every_days == 0 and not is_last_day:
                pending_weights = self._decide_targets(
                    strategy, universe, day, closes, equity_curve, state
                )

        metrics = compute_metrics(equity_curve, total_costs, traded_notional, len(trades))
        return BacktestResult(
            result_id=new_id("backtest"),
            strategy_id=strategy.spec.strategy_id,
            strategy_version=strategy.spec.version,
            spec_hash=strategy.spec.spec_hash(),
            data_fingerprint=self._data_fingerprint(universe, config),
            config=config,
            equity_days=tuple(equity_days),
            equity_curve=tuple(equity_curve),
            trades=tuple(trades),
            metrics=metrics,
            warnings=tuple(warnings),
        )

    def _decide_targets(
        self,
        strategy: Strategy,
        universe: list[str],
        day: date,
        closes: dict[str, float],
        equity_curve: list[float],
        state: PortfolioState,
    ) -> dict[str, float]:
        history = {symbol: self._store.bars_as_of(symbol, day) for symbol in universe}
        proposals = strategy.generate_signals(history, day)
        equity = equity_curve[-1]
        sizings = {}
        for proposal in proposals:
            adv_shares = self._store.average_daily_volume(proposal.symbol, day)
            adv_notional = adv_shares * closes.get(proposal.symbol, proposal.reference_price)
            sizings[proposal.proposal_id] = self._sizer.size(proposal, equity, adv_notional)
        targets = self._allocator.build_targets(proposals, sizings)

        daily_pnl_pct = equity_curve[-1] / equity_curve[-2] - 1.0 if len(equity_curve) >= 2 else 0.0
        decision = self._risk.evaluate(
            targets,
            state,
            closes,
            daily_pnl_pct=daily_pnl_pct,
            drawdown_pct=current_drawdown(equity_curve),
        )
        return decision.approved_weights

    def _execute_rebalance(
        self,
        state: PortfolioState,
        weights: dict[str, float],
        opens: dict[str, float],
        day: date,
        config: BacktestConfig,
    ) -> tuple[PortfolioState, list[BacktestTrade], float, float]:
        equity = state.equity(opens)
        trades: list[BacktestTrade] = []
        total_costs = 0.0
        traded_notional = 0.0
        # Sells before buys so freed cash funds the buys.
        deltas = []
        for symbol, target_weight in weights.items():
            price = opens.get(symbol)
            if price is None or price <= 0:
                continue
            current_weight = state.weight_of(symbol, opens)
            delta_weight = target_weight - current_weight
            if abs(delta_weight) < config.min_rebalance_weight_delta:
                continue
            deltas.append((symbol, delta_weight, price))
        deltas.sort(key=lambda item: item[1])  # most negative (sells) first

        for symbol, delta_weight, price in deltas:
            quantity = delta_weight * equity / price
            adv = self._store.average_daily_volume(symbol, day)
            cost = self._costs.estimate(quantity, price, adv).total
            state = state.apply_fill(symbol, quantity, price, cost)
            trades.append(
                BacktestTrade(
                    trading_day=day, symbol=symbol, quantity=quantity, price=price, cost=cost
                )
            )
            total_costs += cost
            traded_notional += abs(quantity) * price
        return state, trades, total_costs, traded_notional

    def _prices(self, universe: list[str], day: date, field: str) -> dict[str, float]:
        prices: dict[str, float] = {}
        for symbol in universe:
            bars = self._store.bars_as_of(symbol, day)
            if bars:
                # Use the day's bar when present, else the latest prior close
                # (a halted symbol is still marked at its last known price).
                bar = bars[-1]
                prices[symbol] = getattr(bar, field) if bar.trading_day == day else bar.close
        return prices

    def _data_fingerprint(self, universe: list[str], config: BacktestConfig) -> str:
        per_symbol = {
            symbol: [b.fingerprint() for b in self._store.bars_as_of(symbol, config.end)]
            for symbol in universe
        }
        return content_hash(per_symbol)

    def _data_warnings(self, universe: list[str]) -> list[str]:
        warnings: list[str] = []
        sources: set[str] = set()
        for symbol in universe:
            bars = self._store.bars_as_of(symbol, date.max)
            sources.update(b.source for b in bars)
        if "synthetic" in sources:
            warnings.append(
                "backtest uses synthetic data; results demonstrate mechanics, not market evidence"
            )
        return warnings
