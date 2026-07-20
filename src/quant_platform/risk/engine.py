"""Deterministic pre-trade risk engine.

Evaluates a target portfolio against the hard limits and reports *every* rule
with its outcome and headroom — a risk decision that cannot show its work is
a defect. On breach the engine either scales targets down (exposure rules) or
blocks new risk entirely (loss/drawdown rules). It never scales up.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from quant_platform.core.config import RiskLimitsConfig
from quant_platform.portfolio.accounting import PortfolioState
from quant_platform.portfolio.allocator import TargetPortfolio


class RuleOutcome(StrEnum):
    PASS = "PASS"
    SCALED = "SCALED"  # targets reduced to comply
    BLOCKED = "BLOCKED"  # new risk refused entirely


class RuleEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str
    outcome: RuleOutcome
    observed: float
    limit: float
    detail: str = ""


class RiskDecision(BaseModel):
    """The full, auditable result of a pre-trade risk evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str
    approved_weights: dict[str, float]
    evaluations: tuple[RuleEvaluation, ...]
    new_risk_blocked: bool

    @property
    def passed(self) -> bool:
        return not self.new_risk_blocked


class RiskEngine:
    def __init__(self, limits: RiskLimitsConfig) -> None:
        self._limits = limits

    def evaluate(
        self,
        targets: TargetPortfolio,
        state: PortfolioState,
        prices: dict[str, float],
        daily_pnl_pct: float,
        drawdown_pct: float,
    ) -> RiskDecision:
        """Evaluate targets against every hard limit.

        ``daily_pnl_pct`` is today's return (negative = loss); ``drawdown_pct``
        is the current peak-to-trough drawdown as a positive fraction.
        """
        evaluations: list[RuleEvaluation] = []
        weights = dict(targets.weights)
        new_risk_blocked = False

        # --- Loss limits: breach blocks all new risk (only exits survive). ---
        daily_loss = max(0.0, -daily_pnl_pct)
        if daily_loss >= self._limits.max_daily_loss_pct:
            new_risk_blocked = True
            evaluations.append(
                RuleEvaluation(
                    rule="max_daily_loss",
                    outcome=RuleOutcome.BLOCKED,
                    observed=daily_loss,
                    limit=self._limits.max_daily_loss_pct,
                    detail="daily loss limit breached; new risk blocked, exits allowed",
                )
            )
        else:
            evaluations.append(
                RuleEvaluation(
                    rule="max_daily_loss",
                    outcome=RuleOutcome.PASS,
                    observed=daily_loss,
                    limit=self._limits.max_daily_loss_pct,
                )
            )

        if drawdown_pct >= self._limits.max_drawdown_pct:
            new_risk_blocked = True
            evaluations.append(
                RuleEvaluation(
                    rule="max_drawdown",
                    outcome=RuleOutcome.BLOCKED,
                    observed=drawdown_pct,
                    limit=self._limits.max_drawdown_pct,
                    detail="drawdown limit breached; new risk blocked, exits allowed",
                )
            )
        else:
            evaluations.append(
                RuleEvaluation(
                    rule="max_drawdown",
                    outcome=RuleOutcome.PASS,
                    observed=drawdown_pct,
                    limit=self._limits.max_drawdown_pct,
                )
            )

        if new_risk_blocked:
            # Only risk-reducing targets survive: each symbol may go no higher
            # than its current weight (exits and reductions are always allowed).
            reduced = {
                symbol: min(weight, state.weight_of(symbol, prices))
                for symbol, weight in weights.items()
            }
            weights = reduced

        # --- Per-position cap: scale any oversized target down. ---
        cap = self._limits.max_position_weight
        oversized = {s: w for s, w in weights.items() if w > cap}
        if oversized:
            for symbol in oversized:
                weights[symbol] = cap
            evaluations.append(
                RuleEvaluation(
                    rule="max_position_weight",
                    outcome=RuleOutcome.SCALED,
                    observed=max(oversized.values()),
                    limit=cap,
                    detail=f"capped: {sorted(oversized)}",
                )
            )
        else:
            evaluations.append(
                RuleEvaluation(
                    rule="max_position_weight",
                    outcome=RuleOutcome.PASS,
                    observed=max(weights.values(), default=0.0),
                    limit=cap,
                )
            )

        # --- Gross exposure: proportional scale-down. ---
        gross = sum(abs(w) for w in weights.values())
        gross_limit = self._limits.max_gross_exposure
        if gross > gross_limit and gross > 0:
            factor = gross_limit / gross
            weights = {s: w * factor for s, w in weights.items()}
            evaluations.append(
                RuleEvaluation(
                    rule="max_gross_exposure",
                    outcome=RuleOutcome.SCALED,
                    observed=gross,
                    limit=gross_limit,
                    detail=f"scaled by {factor:.4f}",
                )
            )
        else:
            evaluations.append(
                RuleEvaluation(
                    rule="max_gross_exposure",
                    outcome=RuleOutcome.PASS,
                    observed=gross,
                    limit=gross_limit,
                )
            )

        # --- Position count (post-scaling; zero targets are exits, not positions).
        count = sum(1 for w in weights.values() if w > 1e-9)
        evaluations.append(
            RuleEvaluation(
                rule="max_positions",
                outcome=RuleOutcome.PASS
                if count <= self._limits.max_positions
                else RuleOutcome.BLOCKED,
                observed=float(count),
                limit=float(self._limits.max_positions),
            )
        )
        if count > self._limits.max_positions:
            new_risk_blocked = True

        return RiskDecision(
            policy_version=self._limits.policy_version,
            approved_weights=weights,
            evaluations=tuple(evaluations),
            new_risk_blocked=new_risk_blocked,
        )
