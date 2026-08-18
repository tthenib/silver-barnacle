# ADR-0005 — The 80/20 capital allocation is paper accounting, and it caps risk growth

Status: **accepted**  ·  Date: 2026-08-18

## Context

The brief requires roughly 80% of profits retained in trading capital and 20% reserved
externally, implemented as a paper accounting rule with a configurable percentage, and requires
that compounding must not silently increase risk beyond what the risk engine permits.

## Decision

`CapitalLedger` is pure accounting, entirely separate from the broker account. The EA never
attempts a transfer — it cannot, and pretending otherwise would be a category error.

Three rules govern it:

**1. High-water-mark allocation.** Reserve 20% only of *new* profit above the previous
high-water mark. Without this, a system that gains £100, loses it, and regains it reserves £40
against £100 of profit — steadily draining trading capital during a flat period.

**2. One-way reserves.** Reserved capital never returns to trading capital. Un-reserving during
a drawdown would increase risk *because* the system is losing, which is martingale in accounting
clothing — and the brief forbids martingale.

**3. Capped compounding.**

```
SizingBasis = min( account_equity,
                   retained_capital,
                   initial_capital × max_capital_scale )
```

- `min(equity, retained)` — reserved profit stops sizing positions, as intended.
- `equity` in the `min` — a drawdown reduces size immediately, without waiting for a period-end
  allocation event.
- `initial_capital × max_capital_scale` (default 2.0) — risk cannot more than double without a
  human changing a parameter.

## Why the third rule exists

A strategy validated at £2,000 position sizes has not been validated at £20,000 ones. Market
impact, margin behaviour, and the lot quantisation grid all change with size, and the
quantisation grid changes *favourably*, which means larger accounts can take risks the validated
system could not express. Unbounded compounding would silently move the system outside the
regime in which its evidence was gathered.

## Consequences

**Positive.** All four quantities the brief requires are separately tracked. Growth beyond 2× is
a deliberate, reviewable decision. Drawdowns reduce size immediately.

**Negative.** Compounding is capped, so long-run growth is slower than unconstrained
reinvestment. Accepted: this is a research system, and validity outside the tested regime is not
something to assume.
