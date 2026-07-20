# Runbook: Emergency stop and recovery

**Owner:** platform operator · **Applies to:** all execution modes

## When to use

Any of: unexplained positions or fills, reconciliation discrepancies
(`reconciliation.discrepancy` audit events), data-quality collapse on symbols
with open exposure, suspected credential compromise, or any situation where
you are unsure what the platform is doing.

## Stop (in order, stop when contained)

1. **Engage the kill switch** — `KillSwitch.engage(<your identity>, <reason>,
   <correlation id>)`. This trips the global circuit breaker: the gateway
   refuses every new submission while reconciliation and monitoring continue.
   The action is audited; identity and reason are mandatory.
2. **Drop the mode** — `ExecutionGateway.set_mode(ExecutionMode.EMERGENCY_STOP,
   actor, reason)`. Mode changes are audited. `EMERGENCY_STOP` is outside
   `SUBMITTING_MODES`, so this is a second, independent block.
3. **Broker-side stop (live modes only, when they exist):** disconnect the
   agent connection at the broker per the broker's own controls, so the stop
   does not depend on this platform functioning.

## While stopped

- Run `Reconciler.reconcile()` until `report.clean` is true; blocked intents
  resolve to FILLED or CANCELLED from broker truth, never from guesses.
- Run `AuditLedger.verify_chain()`; a failure is a security incident, not an
  operational one — preserve the ledger file and escalate.
- Journal a summary entry per affected correlation ID.

## Resume

Resumption is deliberately harder than stopping:

1. Reconciliation clean, audit chain verified, and the root cause written up.
2. `CircuitBreaker.reset(<named human>, <reason>, <correlation id>)` — the
   reset refuses blank identities or reasons.
3. Re-raise the mode explicitly with `set_mode`, one level at a time. The
   default after any restart or incident is the safest mode; nothing
   auto-resumes.
