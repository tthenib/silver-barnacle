"""Agent protocol and a deterministic reference implementation.

The protocol is deliberately narrow: an agent maps validated inputs to an
:class:`AgentOutput` and does nothing else — no I/O, no state mutation, no
broker access. :class:`TechnicalStateAgent` is a fully deterministic
reference implementation proving the contract end-to-end without an LLM;
model-backed agents plug in behind the same protocol later (ADR-0004).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from quant_platform.agents.contracts import (
    AgentCard,
    AgentOutput,
    EvidenceSource,
    ResearchClaim,
)
from quant_platform.data.contracts import ValidatedSeries


class Agent(Protocol):
    """Propose-only agent: validated inputs in, schema-valid output out."""

    @property
    def card(self) -> AgentCard: ...

    def run(self, correlation_id: str, as_of_utc: datetime) -> AgentOutput: ...


class TechnicalStateAgent:
    """Emits cited claims about observable price state (no prediction).

    The agent computes trailing return and range position from a validated
    series and reports them as claims whose sources are the validation report
    itself. If the series is quarantined or too short it abstains — the
    reference behaviour for "insufficient evidence".
    """

    VERSION = "1.0.0"
    MIN_BARS = 20
    CLAIM_VALIDITY = timedelta(days=1)

    def __init__(self, series: ValidatedSeries) -> None:
        self._series = series

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            name="technical_state",
            purpose="Report reproducible price-volume context for one symbol",
            inputs=("ValidatedSeries",),
            outputs=("AgentOutput with descriptive ResearchClaims",),
            constraints=(
                "no prediction",
                "no order proposals",
                "abstain when data is quarantined or insufficient",
            ),
            failure_conditions=("missing series", "quarantined data", "short history"),
            metrics=("schema_valid_rate", "abstention_quality"),
            memory_usage="none (stateless reference implementation)",
        )

    def run(self, correlation_id: str, as_of_utc: datetime) -> AgentOutput:
        if self._series.eligibility.value in ("QUARANTINED", "EXPIRED"):
            return self._abstain(
                correlation_id, as_of_utc, f"series eligibility is {self._series.eligibility}"
            )
        bars = self._series.bars
        if len(bars) < self.MIN_BARS:
            return self._abstain(
                correlation_id,
                as_of_utc,
                f"only {len(bars)} bars available, {self.MIN_BARS} required",
            )

        window = bars[-self.MIN_BARS :]
        closes = [b.close for b in window]
        trailing_return = closes[-1] / closes[0] - 1.0
        high = max(b.high for b in window)
        low = min(b.low for b in window)
        range_position = (closes[-1] - low) / (high - low) if high > low else 0.5

        source = EvidenceSource(
            description=f"validated series for {self._series.symbol}",
            reference=self._series.validation_report_id,
            as_of_utc=as_of_utc,
        )
        claims = (
            ResearchClaim(
                statement=(
                    f"{self._series.symbol} trailing {self.MIN_BARS}-bar return is "
                    f"{trailing_return:+.2%}"
                ),
                falsification_test="recompute from the referenced validated series",
                sources=(source,),
                confidence=self._series.quality_score,
                valid_from_utc=as_of_utc,
                valid_until_utc=as_of_utc + self.CLAIM_VALIDITY,
            ),
            ResearchClaim(
                statement=(
                    f"{self._series.symbol} sits at {range_position:.0%} of its "
                    f"{self.MIN_BARS}-bar high-low range"
                ),
                falsification_test="recompute from the referenced validated series",
                sources=(source,),
                confidence=self._series.quality_score,
                valid_from_utc=as_of_utc,
                valid_until_utc=as_of_utc + self.CLAIM_VALIDITY,
            ),
        )
        return AgentOutput(
            agent_name=self.card.name,
            agent_version=self.VERSION,
            correlation_id=correlation_id,
            as_of_utc=as_of_utc,
            claims=claims,
        )

    def _abstain(self, correlation_id: str, as_of_utc: datetime, reason: str) -> AgentOutput:
        return AgentOutput(
            agent_name=self.card.name,
            agent_version=self.VERSION,
            correlation_id=correlation_id,
            as_of_utc=as_of_utc,
            abstained=True,
            abstention_reason=reason,
        )
