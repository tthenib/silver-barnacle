# ADR-0003 — One parameter set shared across all instruments

Status: **accepted**  ·  Date: 2026-08-18

## Context

The obvious approach is to tune each instrument separately: EURUSD gets its own lookback, gold
gets another. It improves in-sample results on every instrument, essentially by construction.

## The statistical argument against it

From [`00-consolidated-understanding.md`](../00-consolidated-understanding.md) §5, the standard
error of an annualised Sharpe over `T` years is `sqrt((1 + SR²/2)/T)`. Over 10 years with a true
Sharpe of 0.5, the 95% confidence interval is roughly `[-0.16, 1.16]` — the estimate cannot be
distinguished from zero.

Applying **one rule across `k` weakly-correlated instruments** accumulates evidence far faster
than adding years to a single instrument, because it adds partly-independent observations rather
than more of the same.

Per-instrument tuning destroys exactly that. It:

- multiplies the parameter count by `k` (5 parameters × 6 instruments = 30);
- converts `k` partly-independent tests of one hypothesis into `k` separate single-instrument
  hypotheses, each with the original tiny sample;
- guarantees improved in-sample results whether or not any edge exists, since with 6 instruments
  and a handful of parameters there is always a combination that looks good;
- removes the strongest available evidence that an effect is real — that the *same* rule works
  across markets that have no reason to share an idiosyncrasy.

## Decision

**All instruments in a panel share one parameter set.** Introducing a per-instrument parameter
requires a pre-registered *structural* argument for why that instrument differs — different
trading hours, different tick structure, a different volatility regime by construction — and
"it backtests better" is explicitly not such an argument.

Volatility *normalisation* (ATR-based stops and sizing) is not per-instrument tuning: it is one
rule that adapts to a measured quantity, with no additional free parameters.

## Consequences

**Positive.** Parameter count stays at 5 rather than 30. Cross-instrument consistency becomes
usable evidence. In-sample results will look worse than tuned ones — which is the point, since
the gap between them is a direct estimate of how much the tuned version was overfitting.

**Negative.** Genuinely instrument-specific effects will be missed. Accepted: with the available
sample, an instrument-specific effect cannot be distinguished from noise anyway, so the
capability would be illusory.
