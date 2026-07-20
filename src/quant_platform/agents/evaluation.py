"""Agent output evaluation harness.

Computes the mandatory agent quality metrics from specification section 5.1
over a corpus of outputs: schema-valid rate, citation coverage, and
abstention rate. Model-backed agents must pass this harness on an evaluation
corpus before any prompt or model change ships (specification section 18).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from quant_platform.agents.contracts import AgentOutput


class AgentEvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outputs_evaluated: int
    schema_valid_rate: float
    citation_coverage: float
    abstention_rate: float


def evaluate_outputs(raw_outputs: list[dict[str, object]]) -> AgentEvaluationReport:
    """Evaluate raw (untrusted) agent output payloads.

    ``raw_outputs`` are dicts as they would arrive from a model; validation
    happens here so the harness measures the real schema-valid rate rather
    than assuming inputs are already parsed.
    """
    if not raw_outputs:
        return AgentEvaluationReport(
            outputs_evaluated=0,
            schema_valid_rate=0.0,
            citation_coverage=0.0,
            abstention_rate=0.0,
        )

    valid: list[AgentOutput] = []
    for payload in raw_outputs:
        try:
            valid.append(AgentOutput.model_validate(payload))
        except ValidationError:
            continue

    claims = [claim for output in valid for claim in output.claims]
    cited = sum(1 for claim in claims if claim.sources)
    abstentions = sum(1 for output in valid if output.abstained)

    return AgentEvaluationReport(
        outputs_evaluated=len(raw_outputs),
        schema_valid_rate=len(valid) / len(raw_outputs),
        citation_coverage=cited / len(claims) if claims else 1.0,
        abstention_rate=abstentions / len(valid) if valid else 0.0,
    )
