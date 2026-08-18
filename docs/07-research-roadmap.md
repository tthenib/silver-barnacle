# 07 — Advanced Research Roadmap

Status: **accepted**  ·  Last reviewed: 2026-08-18

Every item below is a **hypothesis with preconditions**, not a planned feature. Nothing here is
scheduled; each becomes eligible only when its preconditions are met, and each can be
permanently abandoned. The ordering reflects dependency and expected value per unit of
overfitting risk, not enthusiasm.

---

## How an item advances

```
  1. Preconditions met (checked against the registry, not against memory)
  2. Pre-registration written and COMMITTED
        · hypothesis · why it might work · how it will be tested
        · what result removes it            ← mandatory
  3. Implemented behind the interface it targets
  4. Tested as a DELTA on the validated baseline, never in isolation
  5. Gates re-run for the COMBINED system
  6. Retained only if it improves OOS performance after costs AND after
     deflation for the trials its own existence created
```

**Step 4 is the one that gets skipped in practice.** A component is not evaluated on whether it
works; it is evaluated on whether it improves *the system that already exists*. A regime filter
that is profitable standalone but adds nothing to the baseline has earned no place.

**Step 6 is the one that gets forgotten.** Adding a component that requires testing 12
configurations adds 12 trials to the deflation calculation. A component must clear the higher
bar it creates for itself, and a marginal improvement bought with a large trial count is a net
loss.

---

## Tier 1 — Eligible once the baseline has a verdict

### R-101 · Second strategy family: volatility breakout

**Preconditions:** H-001 through gate 6 (pass or fail); S4 complete.

**Hypothesis:** volatility compression precedes expansion; entering on a range break after a
low-volatility period captures the expansion.

**Why it might work:** genuinely distinct from trend following — it conditions on *volatility
state* rather than on price direction, so its return stream may be weakly correlated with H-001
even though both trade breakouts.

**Test:** identical panel, identical gates, standalone first, then as a portfolio addition.

**Removal criterion:** fails gate 4 standalone, **or** correlation with H-001 returns > 0.6
(in which case it is not a second source of return, it is the same bet with extra parameters).

### R-102 · Second strategy family: short-horizon mean reversion

**Preconditions:** as R-101.

**Hypothesis:** short-horizon overextension against a moving baseline partially reverts in FX
majors during range conditions.

**Why it might work:** liquidity provision — a rapid move against no news is often inventory
imbalance rather than information.

**Honest concern, recorded up front:** mean reversion trades more frequently than trend
following, so it is far more cost-sensitive, and CFD costs are the binding constraint here. The
cost tolerance test is expected to be the hard gate, not the signal test.

**Removal criterion:** cost tolerance < 2 SD of measured spread. Given the frequency, this is a
likely outcome and should not be treated as a surprise.

### R-103 · Execution improvement: limit entries

**Preconditions:** H-001 past gate 5; measured slippage from S5.

**Hypothesis:** replacing market-on-next-open with a limit order at or inside the prior close
reduces cost without materially reducing fill rate.

**Why interesting:** it improves *net* performance without touching the signal, which means it
adds no alpha parameters. Improvements of this kind are strictly preferable to signal changes
because they do not consume statistical budget.

**Removal criterion:** fill rate drops enough that missed-trade opportunity cost exceeds the
spread saved. This requires modelling the missed trades explicitly — an unfilled limit is not a
free option.

---

## Tier 2 — Requires ≥2 validated strategies

### R-201 · Portfolio construction layer

**Preconditions:** ≥2 strategies past gate 5; sufficient overlapping history to estimate
cross-strategy correlation with a usable confidence interval.

**Hypothesis:** allocating risk across weakly-correlated strategies improves risk-adjusted
return beyond the sum of the parts.

**Design constraint:** start with **equal risk weighting**. It has zero estimated parameters
and is a genuinely hard benchmark to beat — mean-variance optimisation over noisy correlation
estimates routinely underperforms it out-of-sample while looking superior in-sample.

**Removal criterion:** any weighting scheme that fails to beat equal-weight out-of-sample is
discarded and equal-weight is retained.

### R-202 · Correlation-aware position limits

**Preconditions:** R-201; ≥3 years of live-equivalent correlation data.

**Hypothesis:** *measured* rolling correlation improves on the static factor model from stage 1.

**Honest prior:** the static factor model may well win. It encodes structural truth (EURUSD and
USDCHF are both USD bets) that does not need estimating, while rolling correlation estimates are
unstable and lag regime changes. This is a real contest, not a formality.

**Removal criterion:** does not beat the static factor model out-of-sample.

---

## Tier 3 — High overfitting risk; high evidentiary bar

### R-301 · Regime detection

**Preconditions:** ≥2 validated strategies; ≥500 OOS trades total (so partitioning leaves usable
subsamples); a pre-registered, **causal** classifier whose parameters are fixed before evaluation.

**Hypothesis:** a small number of observable market states predict which strategy family
performs better.

**Mandatory design constraints:**
- **At most 3 regimes.** More fragments the sample beyond usefulness.
- **Causal only** — classified from data available at time *t*, never with hindsight labels.
- **Classifier parameters fixed in TRAIN**, never re-fitted per window.
- **Every regime × strategy combination counts as a trial.**
- Report performance **within each regime** with per-regime confidence intervals, not just the
  aggregate. An aggregate improvement built on one regime with 11 trades is not evidence.

**Removal criterion:** conditional allocation does not beat unconditional allocation OOS after
deflating for the regime × strategy trial count. Given the sample-size arithmetic, this is a
genuinely difficult bar and failure is the expected outcome.

### R-302 · Ensemble / meta-strategy

**Preconditions:** R-201 complete; ≥2 strategies past gate 6 individually.

**Hypothesis:** dynamic weighting on recent validated performance beats static weighting.

**The brief's warning applies with full force**, and the safeguards are non-negotiable:
- Hard turnover cap on weight changes (e.g. maximum 10% weight shift per month).
- Minimum lookback long enough that the weighting cannot chase noise.
- Weights bounded away from 0 and 1 — no strategy can be switched fully off by the meta-layer.
- Tested with **trade-order randomisation**, which is where performance-chasing schemes usually
  collapse, since their apparent benefit comes from the specific realised sequence.

**Removal criterion:** fails to beat equal-weight OOS, or its advantage disappears under
trade-order randomisation.

### R-303 · Confidence-weighted sizing

**Preconditions:** a strategy past gate 6 emitting a meaningful `confidence`.

**Hypothesis:** the strategy's self-assessed confidence predicts realised per-trade expectancy.

**Test:** this is testable *without implementing anything* — bucket historical trades by
confidence and compare realised expectancy across buckets. Only if a monotone relationship
exists out-of-sample is sizing wired to it.

Doing the analysis before the implementation is the pattern to follow generally: many
"enhancements" can be falsified from data already collected, at no engineering cost.

**Removal criterion:** no monotone relationship OOS.

---

## Tier 4 — Deferred, possibly indefinitely

### R-401 · Machine learning via ONNX

**Technically available:** MQL5 supports ONNX inference natively (`OnnxCreate`, `OnnxRun`), and
models can be exercised inside the Strategy Tester. Capability is not the constraint.

**Preconditions — all of them:**
1. ≥3 validated strategies (so there is a real benchmark to beat).
2. ≥2,000 OOS trades of accumulated evidence.
3. A specific hypothesis about **what** the model learns that a linear rule cannot — "ML might
   find patterns" is not a hypothesis.
4. A pre-registered feature set of ≤10 features, fixed before training.
5. Purged, embargoed cross-validation to prevent leakage across overlapping labels.
6. The model must beat the linear baseline **after** deflating for the model-selection trials.

**Honest assessment:** with the sample sizes available, these preconditions are unlikely ever to
be met. That is the correct outcome. The realistic path to ML in this project is not "train a
model on price history" but "use a model to improve a specific, isolated sub-decision that has
its own large sample" — for example, execution-price prediction, which generates an observation
per order rather than per trade.

### R-402 · Statistical arbitrage / cointegration

**Preconditions:** demonstrated cross-symbol timestamp reliability on the target broker; ≥2,000
observations of the candidate relationship; a *structural* reason for the relationship
(triangular arbitrage relationships among FX crosses are the only genuinely defensible case
here — a currency triangle must hold by construction, unlike a fitted equity pair).

**Concern:** cointegration estimated over a few thousand daily observations is unstable, and
retail CFD execution costs are likely larger than the mispricings a triangle produces.

### R-403 · Alternative data / sentiment / order flow

**Preconditions:** a point-in-time, survivorship-free source with verified as-of timestamps.

**Assessment:** no such source is available inside MT5. Deferred indefinitely rather than
approximated, because an approximated point-in-time source is worse than none — it produces
confident results contaminated by look-ahead that is very hard to detect after the fact.

---

## Standing research practices

These apply continuously, not at a stage:

- **Hypothesis register** — every idea, including abandoned ones, recorded with its reasoning
  and outcome under `experiments/`. Prevents rediscovering dead ideas as though new.
- **Negative-result discipline** — failures are written up with the same care as successes.
- **Trial-count hygiene** — the registry is the authority; nobody estimates from memory.
- **Periodic re-validation** — a validated strategy is re-tested on new data quarterly. Edges
  decay, and a strategy that stops working should be detected by measurement rather than by
  drawdown.
- **Complexity audit** — every quarter, each component is checked against R10: what is the
  evidence this improves out-of-sample performance? Components that cannot answer are removed.
  Removing a component is a normal, expected outcome of this audit, not an admission of failure.
