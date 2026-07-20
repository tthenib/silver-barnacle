"""Target portfolio construction with a full allocation explanation.

The allocator merges sized signal proposals into target weights under the
gross-exposure, position-count, and cash-reserve limits. Conviction only
ranks candidates; it never inflates a size beyond its sized bound. Every
dropped or scaled candidate is recorded with its reason — an allocation that
cannot be explained is a defect (specification section 10).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.core.config import RiskLimitsConfig
from quant_platform.portfolio.sizing import SizingDecision
from quant_platform.strategies.base import SignalDirection, SignalProposal


class DroppedCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    proposal_id: str
    reason: str


class AllocationExplanation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    considered: int
    accepted: int
    dropped: tuple[DroppedCandidate, ...]
    gross_target: float
    scaling_applied: float = Field(description="1.0 means no gross-exposure scaling")
    residual_cash_weight: float


class TargetPortfolio(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: dict[str, float]
    explanation: AllocationExplanation


class Allocator:
    def __init__(self, limits: RiskLimitsConfig) -> None:
        self._limits = limits

    def build_targets(
        self,
        proposals: list[SignalProposal],
        sizings: dict[str, SizingDecision],
    ) -> TargetPortfolio:
        """Combine LONG proposals and their sizing decisions into target weights.

        ``sizings`` is keyed by proposal_id. FLAT proposals contribute a zero
        target (an explicit exit), and symbols absent from proposals keep no
        target at all — the diff against current holdings happens downstream.
        """
        deployable = max(0.0, 1.0 - self._limits.min_cash_reserve_pct)
        max_gross = min(self._limits.max_gross_exposure, deployable)

        dropped: list[DroppedCandidate] = []
        weights: dict[str, float] = {}

        # Explicit exits first: FLAT proposals zero the symbol.
        for proposal in proposals:
            if proposal.direction is SignalDirection.FLAT:
                weights[proposal.symbol] = 0.0

        # SHORT proposals are refused: no short capability is validated yet
        # (broker allowlist covers long equity only).
        long_candidates: list[SignalProposal] = []
        for proposal in proposals:
            if proposal.direction is SignalDirection.SHORT:
                dropped.append(
                    DroppedCandidate(
                        symbol=proposal.symbol,
                        proposal_id=proposal.proposal_id,
                        reason="short selling is not a validated capability",
                    )
                )
            elif proposal.direction is SignalDirection.LONG:
                long_candidates.append(proposal)

        # Rank by conviction; cap the number of positions.
        long_candidates.sort(key=lambda p: (p.conviction, p.symbol), reverse=True)
        for proposal in long_candidates[self._limits.max_positions :]:
            dropped.append(
                DroppedCandidate(
                    symbol=proposal.symbol,
                    proposal_id=proposal.proposal_id,
                    reason=f"max_positions={self._limits.max_positions} reached",
                )
            )
        long_candidates = long_candidates[: self._limits.max_positions]

        for proposal in long_candidates:
            sizing = sizings.get(proposal.proposal_id)
            if sizing is None:
                dropped.append(
                    DroppedCandidate(
                        symbol=proposal.symbol,
                        proposal_id=proposal.proposal_id,
                        reason="no sizing decision supplied",
                    )
                )
                continue
            if sizing.target_weight <= 0.0:
                dropped.append(
                    DroppedCandidate(
                        symbol=proposal.symbol,
                        proposal_id=proposal.proposal_id,
                        reason=f"sized to zero (binding: {sizing.binding_constraint})",
                    )
                )
                continue
            weights[proposal.symbol] = max(
                weights.get(proposal.symbol, 0.0), min(sizing.target_weight, 1.0)
            )

        # Scale down proportionally if gross exceeds the budget. Never scale up.
        gross = sum(abs(w) for w in weights.values())
        scaling = 1.0
        if gross > max_gross and gross > 0:
            scaling = max_gross / gross
            weights = {symbol: weight * scaling for symbol, weight in weights.items()}
            gross = max_gross

        explanation = AllocationExplanation(
            considered=len(proposals),
            accepted=sum(1 for w in weights.values() if w > 0),
            dropped=tuple(dropped),
            gross_target=gross,
            scaling_applied=scaling,
            residual_cash_weight=1.0 - gross,
        )
        return TargetPortfolio(weights=weights, explanation=explanation)
