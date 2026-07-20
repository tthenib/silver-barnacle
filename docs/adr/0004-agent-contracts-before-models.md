# ADR-0004: Agent contracts and evaluation harness before any LLM binding

**Status:** accepted · **Review by:** before the first model-backed agent ships

## Context

Specification section 5 catalogs 30 agent roles, and section 18 makes prompt
evaluation suites a release gate. Model output is untrusted by design: it must
be schema-validated, cited, uncertainty-bearing, and refusable.

## Decision

The agent plane ships as typed contracts first:

- `ResearchClaim` — statement, falsification test, ≥1 cited source,
  contrary evidence, confidence, validity window (enforced by schema).
- `AgentOutput` — claims **xor** an explicit abstention with a reason;
  an output with neither is invalid.
- `AgentCard` — the specification's mandatory card elements.
- `evaluate_outputs` — measures schema-valid rate, citation coverage, and
  abstention rate over raw (untrusted) payloads.
- `TechnicalStateAgent` — a fully deterministic reference agent that proves
  the contract end-to-end (emits descriptive, cited claims; abstains on
  quarantined or short data) with zero model dependency.

LLM-backed agents implement the same `Agent` protocol later, and may not ship
until an evaluation corpus with benign, adversarial, stale, contradictory,
and prompt-injection-like inputs exists and gates their release.

## Consequences

The pipeline's research stage is exercisable and testable in CI today. The
30-role catalog becomes a registry roadmap rather than a big-bang deliverable.
Cost: no generative research synthesis yet — accepted, because ungoverned
model output would violate the platform's own trust model.
