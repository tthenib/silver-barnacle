# EXPERIMENT_LOG.md — Pre-Registered Experiments and Results

**Status:** 19 experiments pre-registered. None run.
**Last updated:** 2026-08-26
**Protocol:** [BACKTESTING_PROTOCOL.md](BACKTESTING_PROTOCOL.md)

---

## Trial counter

> ### Cumulative trials against validation/test data: **0**
>
> Increment on **every** evaluation touching validation or test data — including sweeps,
> "just to see" variants, re-runs after bug fixes that changed results, and looks at any
> subset, asset, or period. This number only ever increases. It is carried into every
> Deflated Sharpe calculation, and a trial count reconstructed after the fact is worthless.

**Test-set access log** (the test set may be opened once; every access recorded here):

| # | Date | Config hash | Reason | Authorised by |
|---|---|---|---|---|
| — | — | — | *not yet opened* | — |

---

## How to use this log

1. **Pre-register before running.** Fill in hypothesis, prediction, and criteria *first*.
   An experiment added to the log after seeing its result is not an experiment, it is a story.
2. **Predict with direction and rough magnitude.** "Improves Sharpe" is not a prediction.
   "Raises Sharpe by 0.1–0.3 and lowers max drawdown by 3–8pp" is.
3. **Record the result verbatim**, including failures, bugs, and abandoned runs.
4. **Write the conclusion even when it is "inconclusive."** Especially then.
5. **Never delete an entry.** Supersede it with a new ID and link back.

### Entry template

```markdown
### EXP-XXXX — <title>

| Field | Value |
|---|---|
| Status | pre-registered / running / complete / abandoned |
| Hypothesis | |
| **Prediction** (direction + magnitude, written BEFORE running) | |
| Strategy / component | |
| Parameters | |
| Dataset + source | |
| Train / Validation / Test periods | |
| Cost assumptions | |
| Seed | |
| Config hash | |
| Trials consumed | |
| Success criteria | |
| Failure criteria | |

**Results:** CAGR · Sharpe · DSR · Sortino · Calmar · MaxDD · PF · expectancy · trades · exposure

**Benchmarks:** B1 buy&hold · B2 vol-targeted buy&hold · B3 random-entry · B4 null-pipeline

**Prediction correct?** yes / no / partially — *and what that tells us about our priors*

**Conclusion:**

**Follow-up:**
```

---

## Phase A — Infrastructure and honesty checks

*These run before any strategy work. Several can fail in ways that stop the project, which is
exactly why they come first.*

### EXP-0001 — Broker feed vs. exchange feed reconciliation

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | MT5 broker BTCUSD CFD bars track exchange spot closely enough that research on exchange data transfers to broker execution |
| **Prediction** | Daily return correlation > 0.99; median absolute tracking difference < 15 bps/day; a persistent basis of 0–50 bps; timestamp offset from UTC of several hours |
| Dataset | Broker MT5 D1/H1 bars vs. Binance/Coinbase, overlapping window, ≥ 12 months |
| Success criteria | Daily return correlation > 0.98 **and** tracking difference not systematically related to volatility |
| Failure criteria | Correlation < 0.95, or tracking difference widening in volatile periods |
| Trials | 0 (measurement, not selection) |

**Why this is first:** if the feeds diverge, every exchange-data result is unusable for
predicting broker performance, and we need to know that before building on it rather than after.

### EXP-0002 — Cost measurement on the live symbol

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | Realised spread and swap on the target broker are within the modelled baseline (8 bps/side, broker-quoted swap) |
| **Prediction** | Median spread 3–10 bps; 95th percentile 3–5× median; swap materially asymmetric and long-side-negative |
| Method | Tick-level spread sampling over ≥ 30 days across all hours; swap from symbol specs and confirmed against realised account charges |
| Success criteria | Measured baseline within 1.5× of modelled |
| Failure criteria | Measured costs > 2× modelled ⇒ **re-run all feasibility arithmetic before proceeding** |
| Trials | 0 |

### EXP-0003 — Daily bar cut-time sensitivity

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | A multi-week trend signal is insensitive to which hour the daily bar closes |
| **Prediction** | Sharpe varies by < 0.15 across 24 hourly cut times |
| Success criteria | Low dispersion across cut times |
| Failure criteria | High dispersion ⇒ **the strategy is fitted to an arbitrary convention**, which is itself an overfitting finding and must be reported as one |
| Trials | 24 |

**Note:** this is a rare experiment where a *bad* result is highly informative — it would tell us
the signal is noise-driven regardless of what its headline Sharpe says.

### EXP-0004 — Fixed lot vs. volatility-scaled sizing

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | Volatility scaling stabilises realised risk without requiring a return improvement |
| **Prediction** | Realised-volatility dispersion falls by > 40%; max drawdown falls 3–10pp; **CAGR roughly unchanged or slightly lower**. We are explicitly *not* predicting a return gain — see [RESEARCH.md](RESEARCH.md) §3.3 |
| Success criteria | Lower realised-vol dispersion and lower MaxDD at matched average exposure |
| Failure criteria | No risk stabilisation ⇒ the volatility forecast is not informative on this asset |
| Trials | 2 |

### EXP-0005 — Circuit breaker cost accounting

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | The circuit breakers reduce tail risk at an acceptable and *quantifiable* return cost |
| **Prediction** | Total drag 1–3% annualised; breakers trigger 2–8 times/year; 95th-percentile drawdown reduced 5–15pp |
| Method | Ablation — run with each breaker individually disabled, then all disabled |
| Success criteria | Tail reduction achieved at < 4% annualised drag |
| Failure criteria | Drag > 5% annualised, or no measurable tail reduction ⇒ the breaker is superstition and is removed |
| Trials | 6 |

### EXP-0006 — **Null-pipeline control (B4)**

| Field | Value |
|---|---|
| Status | pre-registered — **blocks all strategy experiments** |
| Hypothesis | The research pipeline does not manufacture edge from data that has none |
| **Prediction** | No configuration passes acceptance on synthetic GBM or GARCH data. Best in-sample Sharpe across the sweep will land near the §1 noise table for the trial count used |
| Method | GBM + GARCH paths calibrated to BTC volatility and drift; run the complete search end to end |
| Success criteria | Zero strategies pass acceptance criteria |
| Failure criteria | **Any** strategy passes ⇒ the pipeline is broken and every result it produces is void until fixed |
| Trials | 0 against real data |

**This is the single most important experiment in the project and it is run first.** It also
establishes the empirical noise floor that every real result must clear.

---

## Phase B — V1 baseline

### EXP-0007 — V1 trend ensemble baseline

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | An equal-weight multi-lookback trend ensemble on BTCUSD D1 delivers positive risk-adjusted return net of realistic costs, and beats vol-targeted buy & hold |
| **Prediction** | Net Sharpe **0.3–0.7**; CAGR 5–12% at 15% target vol; MaxDD 15–25%; win rate 30–40%; ~4–12 trades/year. **Probability of beating B2: 40–60%** |
| Parameters | `n ∈ {20,40,60,90,120,160,200}`, entry `score ≥ +0.5`, exit `score ≤ 0`, 15% vol target, 4×ATR stop — **all fixed a priori, none fitted** |
| Dataset | Exchange BTCUSD D1, 2017-01-01 → 2021-12-31 (dev), 2022-01-01 → 2023-12-31 (validation) |
| Costs | Baseline per [BACKTESTING_PROTOCOL.md](BACKTESTING_PROTOCOL.md) §3 |
| Success criteria | All seven V1 pass criteria in [STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §5.3 |
| Failure criteria | Any V1 kill criterion |
| Trials | 1 — *this is the value of pre-specifying every parameter* |

**Known power limitation:** at 4–12 trades/year this experiment will likely produce 28–84 trades,
below the nominal ≥100 threshold. Handled per [STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md)
§5.3 — the gate is the CPCV 5th-percentile criterion, and the confidence interval is reported in
full. Recorded here **before** the run so it cannot later look like an accommodation.

### EXP-0008 — Lookback grid sensitivity

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | Performance is a broad plateau across lookback grids, not a peak at the chosen one |
| **Prediction** | Sharpe varies < 0.2 across reasonable alternative grids ({10..100}, {30..300}, subsets) |
| Failure criteria | Results depend on the specific grid ⇒ **the ensemble premise is falsified and V1 is killed** |
| Trials | 8 |

### EXP-0009 — Stop multiple sensitivity

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | Performance is flat across a 3–6 × ATR stop; the stop is a catastrophe brake, not a profit source |
| **Prediction** | Sharpe varies < 0.15 across 3–6 × ATR; stop hit on < 20% of trades |
| Failure criteria | Sharp dependence on the multiple, or > 40% of exits via stop ⇒ the stop has become the strategy |
| Trials | 6 |

### EXP-0010 — Cost stress

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | The edge survives 2× costs |
| **Prediction** | Sharpe falls 0.1–0.25 at ×2; remains positive. At ×4 it is marginal or negative |
| Failure criteria | Unprofitable at ×2 ⇒ the edge is smaller than our cost uncertainty, which means we do not have one |
| Trials | 6 |

### EXP-0011 — Cross-asset validation

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | The edge is a property of crypto trend, not of BTC's specific history |
| **Prediction** | Same-sign Sharpe on ≥ 4 of 5 crypto assets; ETH within ±0.3 of BTC; **the non-crypto control (gold, S&P) also positive**, since this should be a generic trend effect |
| Failure criteria | Works only on BTC ⇒ asset-specific curve fit ⇒ V1 killed |
| Trials | 6 |

### EXP-0012 — Walk-forward and CPCV

| Field | Value |
|---|---|
| Status | pre-registered |
| Hypothesis | Performance is stable across time windows rather than concentrated in one regime |
| **Prediction** | 5–7 of 8 walk-forward windows positive; walk-forward efficiency 0.5–0.8; CPCV OOS Sharpe distribution centred near the single-path estimate with wide dispersion |
| Failure criteria | < 50% of windows positive, or efficiency < 0.4, or P&L concentrated in a single window |
| Trials | 1 (walk-forward), 1 (CPCV) |

---

## Phase C — Component promotion (each must beat the V1 baseline)

### EXP-0013 — Trailing ATR stop

**Prediction:** improves Calmar by 0.1–0.3 via drawdown reduction; **reduces total return** by
exiting trends early. Net effect on Sharpe uncertain — genuinely 50/50.
Failure: no Calmar improvement, or return cost > 20%. Trials: 8.

### EXP-0014 — Partial profit taking / break-even stop — **pre-registered null test**

**Prediction: BOTH REDUCE EXPECTANCY.** Partial TP by 10–25% (it truncates the right tail that
produces all the profit); break-even stops by 5–20% (they convert winners to scratches on
ordinary noise). See [STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §#13.
If either *improves* out-of-sample risk-adjusted return, the prior was wrong and it ships — that
is what pre-registration is for. Trials: 6.

### EXP-0015 — Short-side exposure

**Prediction:** long/short underperforms long/flat on total return (crypto's unconditional drift
has been strongly positive) but improves Sharpe in bear regimes. **The diagnostic value is
higher than the performance value** — a large gap tells us how much of V1's result was
directional beta rather than signal. Trials: 4.

### EXP-0016 — Second symbol (ETHUSD) + aggregate exposure cap

**Prediction:** portfolio Sharpe improves by 0.05–0.15 — much less than the naive √2 = 41% the
symbol count suggests, because BTC/ETH correlation is 0.7–0.9. If the improvement approaches
√2, **suspect a bug in the correlation handling.** Trials: 4.

### EXP-0017 — Donchian breakout as an ensemble member

**Prediction:** correlation with the MA ensemble 0.7–0.9; marginal Sharpe contribution < 0.05;
worse execution costs. Likely rejected on marginal contribution. Trials: 6.

### EXP-0018 — Directional regime conditioning (≤ 3 states)

**Prediction:** in-sample improvement, **no out-of-sample improvement.** This is the classic
regime-detection result and we should expect it. Failure to improve OOS ⇒ dropped permanently,
not re-specified until it works. Trials: 12.

### EXP-0019 — Signal score calibration (exploratory)

**Question:** does `|score|` carry information about *magnitude*, or only about *sign*?
**Prediction:** returns are **not** monotonic across score deciles — the ensemble score is a
vote count, and there is no reason a 6/7 vote should predict a larger move than a 5/7 vote.
Conviction-scaled sizing ships only if monotonicity holds out of sample
([STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §#12). Trials: 1 (analysis of an existing run,
no new fitting).

---

## Completed experiments

*None yet. Results appear here, including failures, verbatim.*

---

## Superseded / abandoned

*None yet. Abandoned experiments stay listed with the reason for abandonment — an experiment
abandoned because it was going badly is itself a form of selection bias, and recording it is how
we keep ourselves honest about that.*
