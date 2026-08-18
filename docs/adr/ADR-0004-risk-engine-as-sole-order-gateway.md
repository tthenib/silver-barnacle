# ADR-0004 — The risk engine is a mandatory chokepoint, enforced by build invariant

Status: **accepted**  ·  Date: 2026-08-18

## Context

The brief requires that the risk engine be able to override strategy signals and that no
strategy can bypass the global risk layer. Every source document describes risk management as a
layer that is *consulted* before trading — which means it can be forgotten, skipped in a hurry,
or bypassed by a future contributor with a deadline.

Source document D2 demonstrates the failure precisely: its `CheckPreTrade` reads a `static double
todayPL = 0` that is never updated, so its daily loss limit can never trigger. The control looks
present, passes review, and does nothing.

## Decision

Enforce the chokepoint **structurally**, not by convention:

1. `<Trade/Trade.mqh>` may be included by exactly one file:
   `Execution/TradeGateway.mqh`. Enforced by `tools/lint_invariants.py` in CI.
2. `ExecutionEngine::Submit()` accepts only an `ApprovedOrder`.
3. `ApprovedOrder` is produced only by `CRiskEngine::Evaluate()`.
4. Files under `Strategy/Strategies/` may not include `Execution/`, `Risk/`, `Telemetry/` or
   `Capital/`, and may not call trade or account functions (invariant I3).
5. Every risk check has a mandatory test that **trips** it (G2.4) — a limit without a firing
   test is assumed non-functional.

## Consequences

**Positive.** A strategy cannot place an order even by mistake. The bypass path does not exist
rather than being discouraged. Rule 5 catches D2's exact defect class. Strategies become safe to
write quickly and safe to delete, because they are incapable of side effects.

**Negative.** Some indirection: a strategy wanting a different stop expresses it in the `Signal`
rather than acting on it. Genuinely intrabar execution tactics need explicit support in the
execution layer instead of being written ad hoc.

Both costs are small and are exactly the friction intended.
