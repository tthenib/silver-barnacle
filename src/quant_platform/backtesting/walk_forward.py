"""Walk-forward validation.

Parameter selection is frozen on each training window and evaluated on the
immediately following unseen window (specification section 12). The report
preserves every window's selection and both in-sample and out-of-sample
metrics so performance decay is measurable — a large decay or an unstable
selection across windows is a rejection signal, not a tuning opportunity.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict

from quant_platform.backtesting.engine import BacktestConfig, BacktestEngine, BacktestResult
from quant_platform.strategies.base import Strategy, StrategySpec

#: Builds a runnable strategy from a candidate spec.
StrategyFactory = Callable[[StrategySpec], Strategy]

#: Scores a backtest result; higher is better. Kept explicit so the selection
#: criterion is versioned with the caller, not buried in the engine.
Objective = Callable[[BacktestResult], float]


def drawdown_penalized_sharpe(result: BacktestResult) -> float:
    """Default objective: Sharpe minus a drawdown penalty.

    Penalizing drawdown biases selection toward robustness over peak
    performance, in line with the "robust, not peak, parameters" mandate.
    """
    return result.metrics.sharpe_ratio_rf0 - 2.0 * result.metrics.max_drawdown


class WalkForwardWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    train_start: date
    train_end: date
    test_start: date
    test_end: date


class WindowOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    window: WalkForwardWindow
    selected_spec_hash: str
    selected_parameters: dict[str, object]
    train_objective: float
    test_objective: float
    train_result_id: str
    test_result_id: str


class WalkForwardReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    windows: tuple[WindowOutcome, ...]
    mean_train_objective: float
    mean_test_objective: float

    @property
    def objective_decay(self) -> float:
        """Train-to-test objective drop; large positive decay signals overfitting."""
        return self.mean_train_objective - self.mean_test_objective

    @property
    def selection_stable(self) -> bool:
        """True when every window selected the same parameters."""
        return len({w.selected_spec_hash for w in self.windows}) <= 1


def rolling_windows(
    start: date, end: date, train_days: int, test_days: int
) -> list[WalkForwardWindow]:
    """Contiguous, non-overlapping test windows preceded by rolling train windows."""
    windows: list[WalkForwardWindow] = []
    cursor = start
    while True:
        train_start = cursor
        train_end = train_start + timedelta(days=train_days - 1)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days - 1)
        if test_end > end:
            break
        windows.append(
            WalkForwardWindow(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
        cursor = cursor + timedelta(days=test_days)
    return windows


class WalkForwardRunner:
    def __init__(self, engine: BacktestEngine, objective: Objective | None = None) -> None:
        self._engine = engine
        self._objective = objective or drawdown_penalized_sharpe

    def run(
        self,
        candidates: Sequence[StrategySpec],
        factory: StrategyFactory,
        windows: Sequence[WalkForwardWindow],
        base_config: BacktestConfig,
    ) -> WalkForwardReport:
        if not candidates:
            raise ValueError("walk-forward requires at least one candidate spec")
        if not windows:
            raise ValueError("walk-forward requires at least one window")

        outcomes: list[WindowOutcome] = []
        for window in windows:
            # Freeze selection on the training window only.
            best_spec: StrategySpec | None = None
            best_train: BacktestResult | None = None
            best_score = float("-inf")
            for spec in candidates:
                result = self._engine.run(
                    factory(spec),
                    self._window_config(base_config, window.train_start, window.train_end),
                )
                score = self._objective(result)
                if score > best_score:
                    best_score = score
                    best_spec = spec
                    best_train = result
            assert best_spec is not None and best_train is not None

            # Evaluate the frozen selection on the unseen test window.
            test_result = self._engine.run(
                factory(best_spec),
                self._window_config(base_config, window.test_start, window.test_end),
            )
            outcomes.append(
                WindowOutcome(
                    window=window,
                    selected_spec_hash=best_spec.spec_hash(),
                    selected_parameters=dict(best_spec.parameters),
                    train_objective=best_score,
                    test_objective=self._objective(test_result),
                    train_result_id=best_train.result_id,
                    test_result_id=test_result.result_id,
                )
            )

        return WalkForwardReport(
            strategy_id=candidates[0].strategy_id,
            windows=tuple(outcomes),
            mean_train_objective=sum(o.train_objective for o in outcomes) / len(outcomes),
            mean_test_objective=sum(o.test_objective for o in outcomes) / len(outcomes),
        )

    @staticmethod
    def _window_config(base: BacktestConfig, start: date, end: date) -> BacktestConfig:
        return base.model_copy(update={"start": start, "end": end})
