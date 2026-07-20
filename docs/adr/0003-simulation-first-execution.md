# ADR-0003: Simulation-first execution; no live broker adapter yet

**Status:** accepted · **Review by:** before any read-only broker integration

## Context

The specification targets Robinhood Trading MCP but requires runtime
capability discovery, a reviewed allowlist, account binding, idempotent
reconciliation, and staged rollout (read-only before trading). No Robinhood
connector is configured in the development environment (per the bundled
research notes), so a live adapter could not be exercised or tested honestly.

## Decision

1. The broker boundary is the `BrokerGateway` protocol plus
   `VerifiedCapabilities` (the intersection of the adapter's reported
   capabilities and the reviewed YAML allowlist). Nothing above the gateway
   knows which broker exists.
2. The only implementation is `SimulatedBroker`: deterministic fills,
   broker-side idempotency by client order ID, and scripted fault injection —
   including the "response lost but order executed" case that motivates
   reconciliation.
3. `SUBMITTING_MODES` contains only `SIMULATION` and `PAPER`; live modes are
   defined (so policy files and UIs can reference them) but unreachable: no
   adapter exists that the allowlist would verify, and paper mode already
   requires a human approval record the platform cannot fabricate.

## Consequences

Execution logic — preflight, state machine, idempotency, reconciliation — is
fully testable today, including its failure paths (76-test suite exercises
ambiguous submissions, duplicate suppression, tripped breakers, stale
snapshots). The future Robinhood adapter is an implementation of an already
hardened contract, entering in read-only reconciliation mode first per the
specification's phase 5.

## Rollback

None needed; this is the specification's own staging order made explicit.
