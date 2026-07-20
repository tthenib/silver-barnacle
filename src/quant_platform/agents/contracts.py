"""Typed contracts for agent inputs and outputs.

Everything an agent emits is either a :class:`ResearchClaim` bundle or an
explicit abstention. Claims must cite sources and state confidence and
expiry; an unsupported claim is invalid at the schema level, which is the
first line of the "evidence first" defence.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quant_platform.core.metadata import new_id


class EvidenceSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(default_factory=lambda: new_id("source"))
    description: str = Field(min_length=1)
    reference: str = Field(min_length=1, description="URL, dataset ID, or artifact ID")
    as_of_utc: datetime


class ResearchClaim(BaseModel):
    """A falsifiable, cited, time-bounded statement (specification section 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str = Field(default_factory=lambda: new_id("claim"))
    statement: str = Field(min_length=1)
    falsification_test: str = Field(min_length=1, description="How this claim could be shown wrong")
    sources: tuple[EvidenceSource, ...] = Field(min_length=1)
    contrary_evidence: tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    valid_from_utc: datetime
    valid_until_utc: datetime

    @model_validator(mode="after")
    def _check_validity_window(self) -> ResearchClaim:
        if self.valid_until_utc <= self.valid_from_utc:
            raise ValueError("claim validity window must have positive duration")
        return self


class AgentCard(BaseModel):
    """Static description of an agent role (specification section 5.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    purpose: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    constraints: tuple[str, ...]
    failure_conditions: tuple[str, ...]
    metrics: tuple[str, ...]
    memory_usage: str


class AgentOutput(BaseModel):
    """Envelope for one agent invocation: claims or a reasoned abstention.

    An agent that lacks sufficient evidence abstains — it never compensates
    with speculation. ``abstained`` and ``claims`` are mutually exclusive.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    output_id: str = Field(default_factory=lambda: new_id("agentout"))
    agent_name: str
    agent_version: str
    correlation_id: str
    as_of_utc: datetime
    claims: tuple[ResearchClaim, ...] = ()
    abstained: bool = False
    abstention_reason: str = ""

    @model_validator(mode="after")
    def _check_abstention_consistency(self) -> AgentOutput:
        if self.abstained and self.claims:
            raise ValueError("an abstaining output must not carry claims")
        if self.abstained and not self.abstention_reason.strip():
            raise ValueError("abstention requires a reason")
        if not self.abstained and not self.claims:
            raise ValueError("a non-abstaining output must carry at least one claim")
        return self
