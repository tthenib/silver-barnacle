# BACKTESTING_PROTOCOL.md — Validation Standard

**Status:** Binding. No result may be reported that did not follow this protocol.
**Last updated:** 2026-08-26
**Companion documents:** [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) · [docs/ADVERSARIAL_REVIEW.md](docs/ADVERSARIAL_REVIEW.md)

---

## 1. The governing problem

From [RESEARCH.md](RESEARCH.md) §2.3, computed in
[`results/return_target_feasibility.md`](results/return_target_feasibility.md):

| Sample | SE of Sharpe estimate | Expected *best* Sharpe from 500 zero-edge trials |
|---|---|---|
| 2 years | 0.87 | **2.16** |
| 3 years | 0.71 | **1.76** |
| 5 years | 0.55 | **1.37** |
| 8 years | 0.43 | **1.08** |

A six-parameter sweep at five values each is 15,625 trials. **A search with no edge whatsoever
is expected to produce an in-sample Sharpe above the level this project's return target
requires.**

Everything in this document follows from that single fact. The protocol is not bureaucracy; it
is the minimum needed to distinguish a result from the noise a search generates by construction.

The paired risk is false negatives: a protocol can be so strict that it rejects real but modest
edges. [`results/research_power.md`](results/research_power.md) stress-tests this validation
process directly and shows that the V1 Sharpe range has low statistical power unless the trial
count stays very small.

---

## 2. Data

### 2.1 Two sources, deliberately

| Purpose | Source | Why |
|---|---|---|
| **Research** | Exchange OHLCV (Binance/Coinbase), 1m → 1d | Long history, high quality, free, reproducible, no broker-specific artefacts |
| **Production validation** | MT5 broker bars + tick data | This is what the EA will actually trade |

**Mandatory reconciliation (EXP-0001).** Research on exchange data and deployment on a broker
CFD is a silent divergence risk. Before any strategy result is trusted we measure and report:
daily return correlation between feeds, tracking difference distribution, systematic basis, bar
timestamp alignment, and gaps present in one feed but not the other. **If the feeds diverge
materially, exchange-data results do not transfer and we say so.**

### 2.2 Splits — fixed now, before any strategy exists

| Split | Period | Rules |
|---|---|---|
| **Development** | 2017-01-01 → 2021-12-31 | Free exploration. Iterate as much as needed |
| **Validation** | 2022-01-01 → 2023-12-31 | Model selection only. Every touch increments the trial counter |
| **Test (LOCKED)** | 2024-01-01 → present | **Opened once, at the end.** Every access logged in [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) |
| **Deep history** | 2013-01-01 → 2016-12-31 | Sanity check only. Never for tuning. Different market structure entirely |

**Why 2017 as the primary start:** before 2017 crypto lacked functioning derivatives, meaningful
institutional participation, and reliable exchange data. Pre-2017 returns come from a market
that no longer exists. Including them inflates every backtest — and the strategies that most
depend on that period are exactly the ones to distrust.

**Test-set discipline.** The test set is the only unbiased estimate we will ever have, and it is
consumed by looking at it. Rules:

- Opened once, after validation is complete and the configuration is frozen and hashed.
- Every access is logged with a timestamp, the config hash, and the reason.
- **A second look, after any change, permanently degrades it.** If that happens, it is recorded
  as a protocol breach and the test set is treated as a second validation set from that point on.
- No parameter, threshold, or rule may be changed after seeing test results. If we want to
  change something, we say so, and we report both the pre- and post-change results.

### 2.3 Data quality gates

Run before any strategy work; failures block the pipeline.

- Duplicate and missing bars; gaps longer than the timeframe
- Zero-volume, zero-range, and negative-price bars
- Split/rename events (ticker changes, redenominations)
- **Timestamp convention** — bar-open vs bar-close labelling. Getting this wrong is a one-bar
  look-ahead and it is the single most common silent bias in retail backtests
- Outliers > 10σ: investigated individually, never auto-removed. **A real crash is data, not an
  outlier.** Removing crashes from a crypto dataset removes the risk we are trying to measure
- Survivorship: for any multi-asset work, the universe must include delisted assets. Using
  today's top-10 coins as a historical universe guarantees an inflated backtest

---

## 3. Cost model — pessimistic by default

Costs are applied at three levels in every run. **The baseline is the pessimistic realistic
case, not the optimistic one.**

| Component | Baseline | Stress ×2 | Stress ×4 |
|---|---|---|---|
| Spread (per side) | 8 bps | 16 bps | 32 bps |
| Slippage (per side) | 5 bps | 10 bps | 20 bps |
| Commission | broker actual | ×2 | ×4 |
| Swap / financing | broker actual, **asymmetric** | ×2 | ×4 |
| Execution delay | 1 bar | 1 bar | 2 bars |

**Swap is not optional.** A multi-week holding strategy that ignores financing is measuring a
different strategy. Long-biased systems pay financing most of the time; at 20% annualised
financing on 1.0× notional this is a ~12%/year headwind that many backtests silently omit
([RESEARCH.md](RESEARCH.md) §2.2).

**Requirement:** the strategy must remain profitable out-of-sample at **×2**. Failing at ×2
means the edge is smaller than our uncertainty about costs, which means we do not have one.

---

## 4. Validation stages

Run in order. A failure at any stage stops the pipeline — later stages are not run "to see."

### Stage 1 — In-sample fit (development split)
Purpose: does the mechanism behave as hypothesised? **Not evidence of anything.** Reported for
diagnosis only, and never quoted without the out-of-sample number beside it.

### Stage 2 — Out-of-sample (validation split)
First real evidence. Requires ≥ 100 independent trades. **Independent** matters: 400 trades from
overlapping 200-day windows is closer to 5 observations than 400.

### Stage 3 — Walk-forward
Anchored *and* rolling; report both.
- Train 24 months → test 6 months → step forward 6 months
- **Report every window, including losers.** A walk-forward showing 3 of 8 windows profitable is
  a finding, not something to average away
- **Walk-forward efficiency** = OOS return / IS return. Below ~0.5 indicates overfitting

### Stage 4 — Combinatorial purged cross-validation (CPCV)
Stronger than a single walk-forward because it produces a *distribution* of OOS paths rather
than one.
- Purge training observations overlapping the test window; embargo N bars after
- **Purging is mandatory, not optional.** With a 200-day lookback, a training bar adjacent to
  the test set shares information with it, and unpurged CV leaks by construction
- Report the full distribution of OOS Sharpe, not just its mean

### Stage 5 — Monte Carlo
Three distinct tests that answer three distinct questions. Conflating them is common and wrong.

| Test | Method | Answers | Does **not** answer |
|---|---|---|---|
| Trade shuffling | Randomise trade order | "What drawdowns were possible given this trade set?" | Whether the edge is real |
| **Block bootstrap** | Resample **blocks** of 20–60 bars | "Does the edge survive resampled market paths?" | Whether the edge persists in the future |
| Parameter perturbation | ±10/20/30% on each input | "Is this a plateau or a peak?" | Whether the plateau itself is fitted |

**Block length is not a detail.** An i.i.d. bootstrap destroys the serial correlation that a
trend strategy exists to exploit — it will show *any* trend system failing and prove nothing.
Blocks must be long enough to preserve autocorrelation and volatility clustering. Report results
across block lengths of 20, 40 and 60 bars to show the conclusion is not a block-length artefact.

### Stage 6 — Cross-asset validation
Same parameters, **zero retuning**, on ETHUSD, SOLUSD, and two more large caps. Plus a
**non-crypto control** (gold, S&P 500 CFD): if the strategy works there too, it is a generic
trend edge and should be evaluated as one; if it works *only* on BTC, it is probably fitted to
BTC's specific history.

### Stage 7 — Cost and execution stress
The ×2 and ×4 grids from §3, plus execution delay, plus stopped-trade slippage at 1.5 × nominal.

### Stage 8 — Test set
Once. Frozen configuration. Reported in full whatever it says.

### Stage 9 — MT5 parity and platform validation
- Python ↔ MQL5 signal parity, 100% direction match ([ARCHITECTURE.md](ARCHITECTURE.md) §6.2)
- MT5 Strategy Tester on **real ticks** where the broker provides them. Where it does not, this
  is stated as a limitation — M1-modelled ticks generate a *plausible* price path with a fixed
  spread, not the real one, and results carry that caveat explicitly
- Restart/recovery test: kill the terminal mid-position, restart, confirm reconciliation
- Forward test on demo, ≥ 90 days, compared against the backtest's expected distribution

---

## 5. Metrics

### 5.1 Decision-grade — these determine whether we proceed

| Metric | Threshold |
|---|---|
| **Out-of-sample Sharpe vs. B2** (vol-targeted buy & hold) | Must exceed it |
| **Selection-sample Deflated Sharpe Ratio** | > 0 at the logged trial count; applied to the sample where selection occurred |
| **Fresh OOS Probabilistic Sharpe Ratio** | > 0.95 against the benchmark hurdle, without re-applying selection bias |
| **Calmar** (CAGR / MaxDD) | > 0.5 |
| **Independent trade count** | ≥ 100 where achievable — see note below |
| **CPCV Sharpe distribution, 5th percentile** | > B2 point estimate |
| **Profit factor at ×2 costs** | > 1.0 |
| **Parameter plateau** | ±30% perturbation degrades median Sharpe < 25%, no sign flip |
| **Cross-asset consistency** | Same-sign Sharpe on ≥ 3 of 5 assets, untuned |

> **Note on trade count.** A slow signal on a single asset will not reach 100 independent trades
> within the available history — V1 is predicted to produce 28–84 over 2017–2023
> ([STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §5.3). Rather than loosen the threshold after
> the fact, the gate is the CPCV 5th-percentile criterion above, which is stricter. Trade count
> remains reported, and low counts are stated as the power limitation they are.

**Implementation note:** DSR higher-moment terms are computed in per-observation units and only
annualised for reporting. Feeding annualised Sharpe into a per-observation skew/kurtosis
denominator overstates confidence.

### 5.2 Descriptive — always reported, never optimised against

CAGR · total return · annualised volatility · Sortino · maximum drawdown · average drawdown ·
drawdown duration (longest and median) · recovery factor · expectancy · win rate · average win ·
average loss · payoff ratio · exposure · turnover · longest losing streak · tail losses
(5% CVaR) · monthly and yearly return tables · realised-vs-nominal stop slippage distribution.

### 5.3 Reported alongside every result, without exception

1. **Trial count** — every configuration evaluated on this data, cumulative across the project.
2. **Config hash.**
3. **Cost assumptions.**
4. **Random seed.**
5. **Data range and source.**
6. **All four benchmarks** (B1–B4, [STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §5.2).

A result missing any of these is not reportable. This is the mechanism that makes the Deflated
Sharpe computable. Selection-bias correction is applied to the development/validation sample used
for selection; applying the same trial-count penalty again to a fresh OOS or locked test estimate
double-counts the penalty and can make the gate impossible to pass. A trial count reconstructed
after the fact is worthless.

### 5.4 Return/risk framing

The brief is right that 100% return with 80% drawdown is worse than 50% with 15%. We report
`CAGR / MaxDD` (Calmar) as a primary metric, and always alongside the drawdown *distribution*
rather than the single realised maximum — one realised maximum drawdown is a sample of size one
from a distribution whose upper tail is what actually matters.

---

## 6. Trial counting

**Every** evaluation against validation or test data increments the counter. Including:

- Each parameter combination in a sweep
- Each variant tried "just to see"
- Each re-run after a bug fix that changed results
- Each look at a subset, asset, or period

The counter lives at the top of [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) and only ever increases.
Under-counting inflates the Deflated Sharpe and defeats the purpose; when uncertain, count more.

**Corollary that should shape how we work:** because trials are expensive in statistical power,
prefer a small number of *pre-registered* hypotheses to a large sweep. This is why V1 has zero
fitted parameters ([STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §5.1) — it costs almost no
statistical power, so its out-of-sample number is close to unbiased.

---

## 7. The null-pipeline control (B4) — run this first

**Before testing any real strategy, run the entire pipeline on synthetic data with no edge.**

- Generate GBM paths calibrated to BTC's volatility and drift, plus a GARCH variant
- Run the complete search: signal generation, parameter sweep, selection, walk-forward, the lot
- **Expected result: no strategy survives the acceptance criteria**

If the pipeline "discovers" a profitable strategy on data that provably has no edge, **the
pipeline is broken** — and every result it has ever produced is void. This control is cheap, it
is decisive, it is run first and re-run after any pipeline change, and it is almost never done.

It also calibrates the noise floor: the best Sharpe the pipeline finds on null data is the
threshold a real result must clear to mean anything.

---

## 8. Reproducibility

Every experiment produces a directory under `/results/<EXP-ID>/`:

```
config.yaml          exact configuration (hashed)
manifest.json        data source, date range, row count, checksum
metrics.json         all metrics, machine-readable
trades.csv           every trade with entry/exit/size/costs/reason
equity.csv           equity and drawdown series
log.jsonl            full structured event log
report.md            human-readable summary INCLUDING failures
seed.txt             random seed
```

**Requirement:** re-running with the same config and seed reproduces `metrics.json` **bit for
bit**. Non-determinism is a defect and blocks the result, because a result that cannot be
reproduced cannot be defended.

---

## 9. Pre-registration

Before any experiment touches validation or test data, [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md)
records: hypothesis, **prediction with direction and rough magnitude**, success criteria,
failure criteria, and the trial count it will consume.

**The prediction is the point.** An experiment whose result we cannot predict in advance teaches
us little; one where we predicted wrong teaches us a lot. Recording the prediction is what makes
the difference legible — and it makes it much harder to retrofit a story onto whatever the data
happened to show.

---

## 10. Standing prohibitions

| Prohibited | Why |
|---|---|
| Reporting in-sample results without out-of-sample alongside | Misleading by omission |
| Changing parameters after seeing test results | Destroys the only unbiased estimate we have |
| Removing losing trades, periods, or assets | Fabrication |
| "The 2022 bear market was unusual" | It was normal. Regimes recur |
| Selecting the best-performing asset post hoc | Cherry-picking |
| Optimistic default costs | The most common way retail backtests lie |
| Quoting a Sharpe without its trial count | Meaningless number |
| Averaging away losing walk-forward windows | Hides regime dependence, which is the main risk |
| Extending the sample until results improve | Sample selection by another name |
