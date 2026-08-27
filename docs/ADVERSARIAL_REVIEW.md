# Adversarial Review Checklist

**Purpose:** structured attempt to prove that a promising result is wrong, before it is believed.
**Referenced by:** [BACKTESTING_PROTOCOL.md](../BACKTESTING_PROTOCOL.md) · [ROADMAP.md](../ROADMAP.md) Stage 4

---

## Posture

The reviewer's job is **not** to check that the work was done carefully. It is to answer one
question:

> **"How could this backtest be lying to us?"**

Assume the result is false and look for the mechanism. A review that finds nothing has usually
not tried hard enough — the base rate for "promising retail crypto backtest is real" is low, so
finding nothing should itself prompt a second pass.

Where possible, the reviewer should be someone (or something) other than the author. An
independent model prompted to attack a result is far more useful than one prompted to check it.

**Standing rule:** a result is not production-ready until every item below has an explicit
verdict. "Not checked" is a fail, not a neutral.

---

## A. Look-ahead bias

| # | Attack | Verdict |
|---|---|---|
| A1 | Are all signals computed from **closed** bars only? Confirmed by the future-mutation test ([ARCHITECTURE.md](../ARCHITECTURE.md) §6.1)? | |
| A2 | Do orders execute at the **next** bar's open, never the signal bar's close? | |
| A3 | Is the timestamp convention (bar-open vs bar-close labelling) verified against the raw source? | |
| A4 | Are indicator warm-up periods excluded from the results window? | |
| A5 | Do any normalisation, scaling, or percentile calculations use full-sample statistics? *(A percentile computed over the whole history is look-ahead.)* | |
| A6 | Are volatility and correlation estimates strictly trailing? | |
| A7 | Does any parameter, threshold, or universe choice reflect knowledge of the test period? | |

## B. Data integrity

| # | Attack | Verdict |
|---|---|---|
| B1 | Survivorship: does any multi-asset universe include delisted assets? | |
| B2 | Are ticker changes, redenominations, and splits handled? | |
| B3 | Were outliers removed? *(Removing a crash removes the risk being measured.)* | |
| B4 | Does the broker feed match the exchange feed used for research (EXP-0001)? | |
| B5 | Are gaps, halts, and maintenance windows represented rather than interpolated away? | |
| B6 | Is the data range's start date defensible, or was it chosen because results improved? | |

## C. Cost and execution realism

| # | Attack | Verdict |
|---|---|---|
| C1 | Is **swap/financing** included, with correct sign and asymmetry? *(Most common omission.)* | |
| C2 | Are spreads realistic, including widening in volatile periods? | |
| C3 | Is slippage modelled on entries **and** stops, including gaps past the stop? | |
| C4 | Does the strategy remain profitable at ×2 costs? | |
| C5 | Are fills assumed at prices that were actually available in size? | |
| C6 | Is the position size achievable given broker lot granularity ([`results/lot_granularity.md`](../results/lot_granularity.md))? | |
| C7 | Are margin requirements respected throughout, including at peak drawdown? | |

## D. Statistical validity

| # | Attack | Verdict |
|---|---|---|
| D1 | **What is the cumulative trial count?** Is the Deflated Sharpe positive at that count? | |
| D2 | Are there ≥ 100 **independent** trades? *(Overlapping windows are not independent.)* | |
| D3 | Does the result exceed the noise floor established by the null-pipeline control (EXP-0006)? | |
| D4 | Does it beat the random-entry control (B3) at the 95th percentile? | |
| D5 | Does it beat **vol-targeted buy & hold (B2)** — not just buy & hold? | |
| D6 | Is P&L concentrated in a few trades or one period? What is the result excluding the best 5%? | |
| D7 | Would the conclusion survive if the sample started or ended one year earlier or later? | |

## E. Overfitting

| # | Attack | Verdict |
|---|---|---|
| E1 | How many parameters are genuinely fitted (as opposed to fixed a priori)? | |
| E2 | Is performance a **plateau** or a peak? ±30% perturbation on every input? | |
| E3 | Does it work on other assets **without retuning**? | |
| E4 | Does it work across walk-forward windows, or only some? Are losing windows reported? | |
| E5 | Was any parameter changed after seeing validation results? How many times? | |
| E6 | Would a simpler version work nearly as well? *(If yes, ship the simpler version.)* | |
| E7 | Is the strategy sensitive to arbitrary conventions — bar cut time, ATR period, rounding? | |

## F. Regime and structural dependence

| # | Attack | Verdict |
|---|---|---|
| F1 | How much of the return is directional beta rather than signal? *(Compare long/flat to long/short, EXP-0015.)* | |
| F2 | Does it depend on a market structure that has changed — pre-2017 crypto, pre-ETF flows, pre-institutional liquidity? | |
| F3 | How does it perform in each calendar year separately, including 2018 and 2022? | |
| F4 | What single market change would break it? How likely is that change? | |
| F5 | Is the edge plausibly crowded, and is there evidence of decay in recent periods? | |

## G. Implementation and operational risk

| # | Attack | Verdict |
|---|---|---|
| G1 | Does the MQL5 EA reproduce the Python signal on **100%** of bars? | |
| G2 | Is order placement idempotent under restart, timeout, and requote? | |
| G3 | Is every risk limit enforced, tested, and demonstrably unbypassable? | |
| G4 | Does the `approved_lots <= requested_lots` invariant hold under property-based fuzzing? | |
| G5 | Is state recovery correct after a mid-position restart? | |
| G6 | Can every live trade be reconstructed end to end from the log? | |

## H. Meta

| # | Attack | Verdict |
|---|---|---|
| H1 | Is the result **too good**? Does it exceed what [RESEARCH.md](../RESEARCH.md) §6 says is plausible? | |
| H2 | If an outsider showed us this backtest, would we believe it? | |
| H3 | What would need to be true for this to be real? Is that plausible? | |
| H4 | Have any negative results gone unreported? | |
| H5 | Was any gate relaxed to reach this point? | |

---

## Sign-off

```
Experiment ID:
Config hash:
Reviewer:                        (ideally not the author)
Date:

Items failed:
Items unresolved:
Attacks attempted that found nothing:      ← record these; they are evidence too

Verdict:  PRODUCTION-READY  /  NEEDS WORK  /  REJECTED

If PRODUCTION-READY, state the single most likely way this is still wrong:
```

That last line is mandatory. If the reviewer cannot name a residual risk, the review is
incomplete — every result has one.
