"""Performance metrics over an equity curve.

Pure functions; every metric documents its convention. Annualization assumes
252 trading days. The Sharpe ratio uses a zero risk-free rate — a documented
simplification, not an oversight — and is reported with the sample size so
readers can judge its uncertainty.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict

TRADING_DAYS_PER_YEAR = 252


def daily_returns(equity_curve: list[float]) -> list[float]:
    """Simple daily returns from an equity curve (length n-1)."""
    return [
        equity_curve[i] / equity_curve[i - 1] - 1.0
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] > 0
    ]


def total_return(equity_curve: list[float]) -> float:
    if len(equity_curve) < 2 or equity_curve[0] <= 0:
        return 0.0
    return equity_curve[-1] / equity_curve[0] - 1.0


def annualized_volatility(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)


def sharpe_ratio(returns: list[float]) -> float:
    """Annualized Sharpe with risk-free rate 0. Unstable below ~1y of data."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    vol = annualized_volatility(returns)
    if vol == 0.0:
        return 0.0
    return mean * TRADING_DAYS_PER_YEAR / vol


def max_drawdown(equity_curve: list[float]) -> float:
    """Largest peak-to-trough decline as a positive fraction."""
    peak = float("-inf")
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, 1.0 - value / peak)
    return worst


def current_drawdown(equity_curve: list[float]) -> float:
    """Drawdown of the latest point from the running peak (positive fraction)."""
    if not equity_curve:
        return 0.0
    peak = max(equity_curve)
    if peak <= 0:
        return 0.0
    return max(0.0, 1.0 - equity_curve[-1] / peak)


class BacktestMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observations: int
    total_return: float
    annualized_volatility: float
    sharpe_ratio_rf0: float
    max_drawdown: float
    total_costs: float
    turnover: float
    trade_count: int


def compute_metrics(
    equity_curve: list[float],
    total_costs: float,
    traded_notional: float,
    trade_count: int,
) -> BacktestMetrics:
    returns = daily_returns(equity_curve)
    average_equity = sum(equity_curve) / len(equity_curve) if equity_curve else 0.0
    return BacktestMetrics(
        observations=len(returns),
        total_return=total_return(equity_curve),
        annualized_volatility=annualized_volatility(returns),
        sharpe_ratio_rf0=sharpe_ratio(returns),
        max_drawdown=max_drawdown(equity_curve),
        total_costs=total_costs,
        turnover=traded_notional / average_equity if average_equity > 0 else 0.0,
        trade_count=trade_count,
    )
