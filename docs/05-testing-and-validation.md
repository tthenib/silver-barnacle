# 05 — Testing and Validation Strategy

Status: **accepted**  ·  Last reviewed: 2026-08-18

Two distinct activities share the word "testing" and must not share a process:

- **Software testing** — does the code do what it says? Deterministic, binary, automated.
- **Statistical validation** — does the strategy have an edge? Probabilistic, gated, and
  capable of returning "no".

A bug in the first produces wrong numbers in the second, which is why the software testing
layer is the more urgent of the two.

---

# Part 1 — Software testing

## 1.1 Layers

| Layer | Scope | Where | When |
|-------|-------|-------|------|
| Unit | Single class, no I/O | `mql5/Tests/`, `research/tests/` | Every build |
| Golden-vector | MQL5 features vs independent Python references | `mql5/Tests/golden/` | Every build |
| Integration | Module chains via injected signals | Strategy Tester, scripted | Pre-push |
| Property | Invariants over generated inputs | Both tiers | Every build |
| Invariant lint | Architectural rules I1/I2/I3 | `tools/lint_invariants.py` | CI |
| Determinism | Two identical runs, byte-identical output | Harness | Per stage gate |
| Known-answer | Harness must reject pure noise | Harness | Per stage gate |

## 1.2 What gets a unit test, without exception

Anything where a silent numerical error produces a plausible but wrong result:

- **Position sizing and lot quantisation** — golden table across 5-digit FX, JPY pairs
  (different pip scale), gold, and an index. Assertions: never rounds up; achieved risk never
  exceeds intended; sub-minimum returns `ok=false`.
- **Cost model** — hand-computed round-turn cost per instrument class; swap accrual across
  weekends.
- **Capital ledger** — high-water-mark logic across gain → loss → regain; one-way reserve
  property; the identity `retained + reserved == initial + total_profit` after every event.
- **Risk limit evaluation** — one tripping and one passing case per check; first-binding-reason
  ordering.
- **Feature calculations** — golden vectors to 1e-9; short-history fixtures asserting
  `valid == false`.
- **Clock / session arithmetic** — server↔UTC conversion across DST boundaries in both
  hemispheres; daily reset at the configured UTC hour.
- **Order state machine** — legal transitions succeed, illegal ones assert.
- **All harness metrics** — Sharpe, Sortino, Calmar, drawdown, DSR against series with known
  analytic answers.

## 1.3 Property-based tests

Cheap, and they find the cases nobody thinks to write:

```
∀ (equity, risk%, stop_distance, symbol_spec):
      achieved_risk ≤ intended_risk                       # rounding is down
      lots ∈ {0} ∪ [vol_min, vol_max] and lots % vol_step == 0

∀ sequences of (signal, fill, price) events:
      Σ journalled position deltas == broker position      # reconciliation identity
      risk_engine never emits ApprovedOrder when any limit is breached

∀ ledger event sequences:
      reserved_capital is monotonically non-decreasing      # one-way property
```

## 1.4 The golden-vector cross-check

Python computes ATR and Donchian bounds over a fixed exported price series; the values are
committed to `mql5/Tests/golden/` and asserted by the MQL5 tests to 1e-9.

This is the only place two implementations of the same calculation are permitted to exist, and
it is permitted precisely because the second one *never generates a result* — it exists to
disagree. Two implementations that agree to nine decimal places over ten years of data are
unlikely to share a bug; the cross-check is what buys confidence that the MQL5 feature layer is
correct, without ever letting the Python version near a reported number.

## 1.5 The known-answer test for the harness

**Feed the validation pipeline a seeded random walk.**

A strategy trading pure noise must produce a Sharpe statistically indistinguishable from zero
and must **fail** gates 3–6. If it passes any of them, the harness is broken and every result it
has ever produced is void.

This runs as a permanent regression test at every stage gate. It is the single most important
test in the project, because it is the only one that can catch the failure mode where
*everything looks fine and the conclusions are wrong*.

A second variant: feed the harness a synthetic series with a *deliberately injected* edge of
known size, and confirm the harness detects it and estimates it approximately correctly. Between
them, these establish that the apparatus has neither false positives nor total insensitivity.

---

# Part 2 — Statistical validation

## 2.1 Data partitioning

Defined once in `config/splits.yaml`; changing it requires an ADR.

```
├──────────── TRAIN ────────────┼──── VALIDATION ────┼──── HOLDOUT ────┤
   ~60% earliest                   ~20%                 ~20% latest
   development, parameter          gate 4 evaluation    gates 6 & 8 ONLY
   exploration, unlimited runs     limited runs         ONE unlock, ever
```

Rules:

1. **TRAIN** — unlimited exploration. Every run still counts as a trial.
2. **VALIDATION** — used at gate 4. Repeated use is permitted but *each use increments the trial
   count*, so it degrades in value with reuse, which is the correct incentive.
3. **HOLDOUT** — one unlock per hypothesis, recorded in an append-only committed file. A second
   unlock for the same hypothesis is refused by the harness. If a hypothesis fails on the
   holdout, the honest options are: abandon it, or treat any modified version as a *new*
   hypothesis whose trial count inherits the parent's.

Walk-forward (gate 5) operates entirely within TRAIN + VALIDATION.

**Embargo.** Because positions span multiple bars, a split boundary can leak: a trade opened
before the boundary and closed after it uses information from both sides. An embargo period of
at least the strategy's maximum holding period is applied at every boundary, and trades
straddling a boundary are excluded rather than truncated.

## 2.2 Walk-forward analysis

```
Window 1:  [══ optimise 3y ══][ test 1y ]
Window 2:            [══ optimise 3y ══][ test 1y ]
Window 3:                      [══ optimise 3y ══][ test 1y ]
```

Anchored (expanding) and rolling (fixed-length) variants are both run; a strategy that works
under only one of them is reported as such, since the difference indicates whether the edge
requires recent data or benefits from long history.

Reported: **walk-forward efficiency** (aggregate OOS return ÷ aggregate IS return), the
distribution of per-window Sharpe, **parameter stability across windows** (a strategy whose
optimal parameters jump between windows is fitting noise, regardless of its aggregate result),
and per-window trade counts.

## 2.3 Parameter sensitivity

For each parameter, sweep a range around the candidate value and map the metric surface.

What is being looked for is a **plateau**, not a peak. Concretely:

> Perturb every parameter simultaneously by ±20%, in all sign combinations. The **worst-case**
> Sharpe across that neighbourhood must remain above the gate threshold.

Reporting the *worst corner* rather than the average is deliberate. Averaging over the
neighbourhood lets one excellent corner mask several terrible ones, which is precisely the
signature of a fitted peak.

A strategy that works only at one exact parameter value is classified unreliable and rejected —
the brief says this explicitly and the harness enforces it numerically.

## 2.4 Monte Carlo and bootstrap

Four distinct perturbations, each answering a different question:

| Method | Question |
|--------|----------|
| **Trade-order randomisation** | Does the result depend on the lucky *sequence* of outcomes? |
| **Block bootstrap of returns** | What is the sampling distribution of the performance metrics? |
| **Execution perturbation** (slippage, spread, fill price) | Does the edge survive worse execution? |
| **Trade removal** (drop a random 10%) | Does the result depend on a small subset of trades? |

Block bootstrap (rather than i.i.d. resampling) preserves autocorrelation, which matters for
trend strategies whose returns are serially dependent by construction — i.i.d. resampling would
systematically overstate their statistical significance.

Reported from ≥10,000 paths: 5th/50th/95th percentile terminal equity; distribution of maximum
drawdown; probability of exceeding the drawdown limit; probability of ruin; drawdown duration
distribution.

## 2.5 Multiple testing and the Deflated Sharpe Ratio

The trial count comes from the registry, not from memory:

```sql
SELECT COUNT(*) FROM runs WHERE hypothesis_id = ? AND counted_as_trial = 1;
```

The **Deflated Sharpe Ratio** (Bailey & López de Prado) adjusts the observed Sharpe for the
number of trials, the length of the sample, and the skew and kurtosis of the return
distribution. It answers the question that actually matters: *given that I tried N
configurations, what is the probability that this one's true Sharpe exceeds zero?*

The non-normality terms matter more than they might appear. Trend-following returns are
positively skewed with fat tails, and the standard Sharpe standard error understates uncertainty
for such distributions — so the naive test is optimistic exactly where these strategies live.

## 2.6 Concentration analysis

The brief asks specifically whether profitability depends on a few exceptional trades. Three
measures:

- **Top-N dependency**: net profit excluding the best 5 trades ÷ total net profit.
  Below 0.5 ⇒ the result rests on outliers.
- **Gini coefficient of trade P&L** — overall concentration.
- **Largest single-trade contribution** as a fraction of total profit.

For trend following, some positive skew is *expected and desirable* — the strategy's premise is
a few large winners paying for many small losses. So the criterion is not "no concentration"
but "not so concentrated that the result is unfalsifiable". A strategy whose entire profit comes
from two trades has an effective sample size of two, whatever its trade count says.

## 2.7 Cost stress

Beyond the perturbations above, the harness solves for the **cost tolerance** described in
[`03-module-specifications.md`](03-module-specifications.md) §10 and compares it to the
*measured* spread distribution from `ExportTickStats.mq5` — not to an assumed one.

## 2.8 Backtest-vs-forward comparison (gate 8)

The prediction interval is computed from the backtest bootstrap **before** the forward test
begins, and committed. Then the forward result is compared against it.

Compared: trade-return distribution (two-sample Kolmogorov–Smirnov), realised vs modelled
slippage, realised vs modelled spread, trade frequency, average holding period, and the rejection
mix from `RejectJournal`.

**A forward result *better* than the prediction interval is investigated as seriously as a worse
one.** Outperformance usually means the backtest was pessimistic in a way that indicates a
modelling error — and a modelling error that currently flatters the system is still a modelling
error.

---

## 3. The gate system

| Gate | Question | Where |
|------|----------|-------|
| G1 | Does the code compile, lint, and satisfy its invariants? | S0–S2 |
| G2 | Do unit, golden, property and integration tests pass? | S0–S2 |
| G3 | Does the strategy do anything at all in-sample, net of costs? | S3 |
| G4 | Does it survive out-of-sample validation? | S4 |
| G5 | Does it survive walk-forward and parameter perturbation? | S4 |
| G6 | Does it survive Monte Carlo, cost stress, and trial deflation? | S4 |
| G7 | Does it behave as predicted on the demo account? | S5 |
| G8 | Do forward and backtest distributions agree statistically? | S5 |

Numeric criteria: [`08-acceptance-criteria.md`](08-acceptance-criteria.md).

**Gate discipline.** A gate is evaluated by the harness against criteria fixed *before* the run.
Failing a gate stops that hypothesis; it does not authorise a search for parameters that pass.
The permitted responses to a gate failure are exactly three:

1. Abandon the hypothesis and record the negative result.
2. Fix a demonstrated *implementation bug* and re-run (recorded as a bug fix, with the defect
   identified — "the numbers looked wrong" is not a demonstrated bug).
3. Formulate a **new** hypothesis, pre-register it, and start over — inheriting the parent's
   trial count.

There is no fourth option, and in particular "adjust the criteria" is not one. The criteria are
committed before the data is seen precisely so that this temptation is answered in advance.

## 4. Negative results are deliverables

Every failed hypothesis produces a committed record under `experiments/gates/` stating what was
tested, why it was expected to work, how it failed, and what was learned.

This is not bookkeeping ceremony. Without it, a failed idea returns six months later in
slightly different clothing and is retested as though new — which is unrecorded multiple testing
and is how a research programme fools itself over time. The register of dead hypotheses is one
of the more valuable artefacts this project will produce, and quite possibly the main one.
