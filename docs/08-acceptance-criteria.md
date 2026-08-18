# 08 — Objective Acceptance Criteria

Status: **accepted**  ·  Last reviewed: 2026-08-18

Every criterion below is numeric and evaluated by the harness. Criteria are fixed **before** the
corresponding data is examined. Changing a criterion after seeing results requires an ADR
stating what was seen and why the change is not motivated by it — a deliberately high bar,
because this is the single most common route by which a research programme quietly abandons its
own standards.

**On the specific numbers.** They are calibrated to the sample sizes actually available (see
[`00`](00-consolidated-understanding.md) §5) and to published characteristics of the strategy
family, not to any of the figures quoted in the source PDFs. Where a threshold is a judgement
call it is marked ⚖ and its reasoning is given, so that a future reviewer can disagree with the
reasoning rather than merely with the number.

---

## Gate 1 — Code correctness

| # | Criterion | Threshold |
|---|-----------|-----------|
| 1.1 | MQL5 compiles | Zero errors, **zero warnings** |
| 1.2 | Invariant linter (I1/I2/I3) | Zero violations |
| 1.3 | `<Trade/Trade.mqh>` inclusions | Exactly 1 file |
| 1.4 | Bar-0 access outside `BarProvider` | Zero occurrences |
| 1.5 | Magic numbers outside `Config/` | Zero (linter allowlist for 0, 1, −1) |
| 1.6 | Discarded fallible results | Zero |
| 1.7 | Python lint + type check | Clean |
| 1.8 | Config validation | Every invalid-config fixture rejected with a specific message |

Zero warnings is not perfectionism: MQL5 warns about implicit conversions and possible loss of
data, and in a system that converts between prices, points, ticks and lots, those warnings are
where sizing bugs live.

---

## Gate 2 — Unit and integration testing

| # | Criterion | Threshold |
|---|-----------|-----------|
| 2.1 | MQL5 unit tests pass | 100% |
| 2.2 | Python harness tests pass | 100% |
| 2.3 | Golden-vector agreement (ATR, Donchian) | \|Δ\| < 1e-9 over the full reference series |
| 2.4 | Risk-check coverage | Every check has a tripping **and** a passing test |
| 2.5 | Sizing golden table | Passes for 5-digit FX, JPY, gold, index |
| 2.6 | Property test: achieved risk ≤ intended | 100% of 10,000 generated cases |
| 2.7 | Property test: reserved capital monotone non-decreasing | 100% |
| 2.8 | Restart reconciliation | No duplicate order across 100 simulated restarts |
| 2.9 | Determinism | Two identical runs ⇒ byte-identical journals |
| 2.10 | **Known-answer: seeded random walk** | **Fails gates 3–6** (if it passes, everything is void) |
| 2.11 | Known-answer: injected edge of known size | Detected, magnitude within 2 SE |
| 2.12 | `SelfTest` against live broker specs | Passes on all panel instruments |

---

## Gate 3 — In-sample viability (TRAIN split)

Deliberately permissive. Gate 3 eliminates the dead, it does not select winners — a demanding
in-sample threshold would simply be an invitation to optimise until it is met.

| # | Criterion | Threshold | Note |
|---|-----------|-----------|------|
| 3.1 | Total closed trades | ≥ 200 | ⚖ Below this nothing downstream is meaningful |
| 3.2 | Trades per instrument | ≥ 20 on ≥ 4 of 6 | Panel result is not one instrument |
| 3.3 | Net profit factor (after full costs) | ≥ 1.05 | Deliberately low |
| 3.4 | Net expectancy per trade | > 0 | After spread, commission, slippage, swap |
| 3.5 | Max drawdown | ≤ 35% | ⚖ Above this the strategy is untradeable regardless of return |
| 3.6 | Cost-to-gross-profit ratio | ≤ 0.6 | Above this the result is a cost-model artefact |
| 3.7 | Behavioural consistency with §4 of [`06`](06-baseline-strategy.md) | Within stated ranges | **Outside ⇒ investigate infrastructure before proceeding** |
| 3.8 | Rejection analysis reviewed | Documented | High rejection rates change the realised strategy |

**3.7 is a gate, not a note.** A result better than the expected range blocks progression until
explained, exactly as a bad one does.

---

## Gate 4 — Out-of-sample validation (VALIDATION split)

| # | Criterion | Threshold | Note |
|---|-----------|-----------|------|
| 4.1 | OOS closed trades | ≥ 60 | ⚖ Minimum for any inference |
| 4.2 | OOS net Sharpe (annualised) | ≥ 0.3 | ⚖ Below this, undetectable at any feasible sample size |
| 4.3 | OOS Sharpe ÷ IS Sharpe | ≥ 0.5 | Standard degradation tolerance |
| 4.4 | OOS net profit factor | ≥ 1.15 | |
| 4.5 | OOS max drawdown | ≤ 1.5 × IS max drawdown | Larger ⇒ IS understated risk |
| 4.6 | Top-5-trade dependency | ≥ 0.5 | Profit excluding best 5 trades ÷ total |
| 4.7 | Largest single-trade contribution | ≤ 25% of net profit | |
| 4.8 | Directional balance | Both directions traded; neither loses more than 1.5 × the other's gain | |
| 4.9 | Instrument breadth | Positive expectancy on ≥ 4 of 6 | Not required on all — that would invite dropping losers |
| 4.10 | Sign consistency IS vs OOS | Per-instrument expectancy sign agrees on ≥ 4 of 6 | |

**On 4.2.** A true Sharpe below 0.3 cannot be distinguished from zero with the data available,
so accepting one would mean accepting a result we cannot verify. This threshold is about the
limits of the evidence, not about ambition.

---

## Gate 5 — Walk-forward and parameter stability

| # | Criterion | Threshold | Note |
|---|-----------|-----------|------|
| 5.1 | Walk-forward efficiency (OOS ÷ IS return) | ≥ 0.5 | |
| 5.2 | Median per-window Sharpe | > 0 | |
| 5.3 | Profitable windows | ≥ 50% | ⚖ Not higher — trend strategies have losing years by design |
| 5.4 | Single-window P&L concentration | No window > 40% of total | |
| 5.5 | Parameter stability | Optimal N varies < 50% across windows | Jumping optima ⇒ fitting noise |
| 5.6 | **Worst-corner sensitivity** | Sharpe > 0.2 at the **worst** ±20% simultaneous perturbation | ⚖ Worst corner, not average |
| 5.7 | Plateau width | ≥ 3 contiguous N values (step 10) with Sharpe ≥ 0.8 × peak | No single-point optima |
| 5.8 | Timeframe robustness | Positive expectancy on ≥ 1 adjacent timeframe (H4 or W1) | Sanity, not a hard requirement on magnitude |
| 5.9 | Anchored vs rolling walk-forward | Both reported; large divergence documented | |

**On 5.6.** Reporting the worst corner rather than the average is the difference between
detecting a fitted peak and hiding one. An average over the neighbourhood lets one excellent
corner mask several terrible ones.

---

## Gate 6 — Monte Carlo, cost stress, and multiple-testing deflation

| # | Criterion | Threshold | Note |
|---|-----------|-----------|------|
| 6.1 | Bootstrap 5th-percentile terminal equity | > starting equity | ⚖ 95% of paths at least break even |
| 6.2 | P(max drawdown > 35%) | < 10% | |
| 6.3 | P(ruin: equity < 50% of start) | < 1% | |
| 6.4 | Trade-order randomisation: median Sharpe | ≥ 0.7 × observed Sharpe | Sequence-dependence check |
| 6.5 | Trade-removal (drop random 10%) | Positive expectancy in ≥ 90% of draws | |
| 6.6 | **Deflated Sharpe Ratio** | **> 0.95** | P(true Sharpe > 0) after deflating for the registry's trial count |
| 6.7 | **Cost tolerance** | > 2 SD of measured spread distribution, every instrument | Fragility test |
| 6.8 | Doubled slippage assumption | Expectancy remains > 0 | |
| 6.9 | Commission +50% | Expectancy remains > 0 | |
| 6.10 | Trial count | Reported and reconciled with the registry | Discrepancy ⇒ gate fails |

**6.6 is the gate most likely to fail, and it is meant to be.** It is the only criterion that
accounts for how many things were tried, and it is where a strategy that looks good because it
was the best of forty configurations gets caught.

---

## Gate 7 — Demo forward testing

Pre-registered before the forward test starts: duration, prediction intervals, and criteria.

| # | Criterion | Threshold | Note |
|---|-----------|-----------|------|
| 7.1 | Duration | ≥ 6 months **and** ≥ 60 closed trades | Whichever is later |
| 7.2 | Uptime | ≥ 95% of market hours | Below this the sample is not representative |
| 7.3 | Unexplained execution errors | Zero | Every error explained and categorised |
| 7.4 | Reconciliation mismatches | Zero unresolved | |
| 7.5 | Realised slippage vs modelled | Within modelled distribution (KS p > 0.05) | Worse ⇒ cost model understated |
| 7.6 | Realised spread vs assumed | Within assumption, or assumption revised and **all prior gates re-run** | |
| 7.7 | Trade frequency vs backtest | Within ±30% | Large deviation ⇒ signal implementation differs live |
| 7.8 | Forward net Sharpe | Within the 90% prediction interval computed **before** the test | Two-sided |
| 7.9 | Max drawdown | ≤ pre-registered limit | Breach halts the test |

**7.8 is two-sided.** A forward Sharpe *above* the prediction interval fails the gate. Beating
your own prediction means the model that produced the prediction is wrong, and a wrong model
that currently flatters the system is still wrong.

---

## Gate 8 — Statistical agreement between expected and observed

| # | Criterion | Threshold |
|---|-----------|-----------|
| 8.1 | Trade-return distribution: forward vs backtest | Two-sample KS, p > 0.05 |
| 8.2 | Win rate | Within backtest 95% CI |
| 8.3 | Payoff ratio | Within backtest 95% CI |
| 8.4 | Average holding period | Within ±25% |
| 8.5 | Rejection-reason mix | Qualitatively consistent; large differences explained |
| 8.6 | Equity-curve shape | Forward path inside the backtest bootstrap 90% envelope |
| 8.7 | Per-instrument behaviour | No instrument behaving qualitatively differently |
| 8.8 | Cost realisation | Realised total cost within ±20% of modelled |

Failing gate 8 while passing gate 7 is the most informative outcome available: the *level* of
performance matched but the *mechanism* did not, which almost always means the backtest was
right by accident. This is treated as a failure requiring root-cause analysis, not as a pass
with a caveat.

---

## Stage completion criteria (engineering)

| Stage | Complete when |
|-------|---------------|
| S0 | G1 passes; EA initialises, writes manifest, places no orders |
| S1 | G1 + G2 pass; injected signals execute correctly; risk caps hold under adversarial injection |
| S2 | G1 + G2 pass with the baseline; determinism verified; journals parse |
| S3 | Runs reproducible from manifest; registry enforces trial counting; holdout locked |
| S4 | Every statistical routine verified against a known-answer series; **noise fails gates 3–6** |
| S5 | G7 + G8 evaluated (pass or fail — both complete the stage) |

---

## Overall project acceptance

The project has succeeded when **either** of the following is true — the symmetry is the point:

**(A) A validated strategy exists.** It passed gates 1–8 without criteria being relaxed, with a
complete and auditable trial count, and with a documented cost tolerance exceeding measured
execution variability.

**(B) A credible negative result exists.** The apparatus passed gates 1–2 and its known-answer
tests, was applied to at least one well-motivated hypothesis, and returned a verdict of "no
detectable edge" that is trustworthy *because* the apparatus was shown capable of detecting a
known injected edge.

The project has **failed** if it produces a result that cannot be reproduced, cannot be traced
to a commit and parameter set, or rests on a trial count that does not reconcile with the
registry — regardless of how good the numbers look. Especially then.
