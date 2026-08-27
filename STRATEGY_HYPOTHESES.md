# STRATEGY_HYPOTHESES.md — Ranked Components and the V1 Specification

**Status:** Ranking complete. V1 specified. Nothing implemented.
**Last updated:** 2026-08-26
**Companion documents:** [RESEARCH.md](RESEARCH.md) (evidence) · [BACKTESTING_PROTOCOL.md](BACKTESTING_PROTOCOL.md) (how each is tested) · [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) (pre-registrations)

---

## 1. Ranking method

Components are ranked by a deliberately conservative composite. The weighting reflects a view
argued in [RESEARCH.md](RESEARCH.md) §2.3: at our sample sizes, *the ability to validate a
component matters more than its expected edge*, because an edge we cannot distinguish from
noise is not an edge we can safely lever.

| Criterion | Weight | Scale |
|---|---|---|
| Evidence quality | 30% | Grade A=5 … E=1 |
| Implementability on MT5 crypto CFD | 25% | 5 = works today with broker data; 1 = impossible |
| Overfitting resistance | 25% | 5 = no free parameters / broad plateau; 1 = point-fitted |
| Expected marginal contribution | 20% | 5 = large and diversifying; 1 = redundant with what we have |

**Marginal** contribution is the key subtlety: a component that duplicates an existing signal
scores low even if its standalone evidence is good. We are building a system, not a collection.

---

## 2. The ranked list

| Rank | Component | Evid. | Impl. | Overfit-resist. | Marginal | Score | V1 |
|---|---|---|---|---|---|---|---|
| **1** | Volatility-scaled position sizing | A (risk) | 5 | 5 | 5 | **4.85** | ✅ |
| **2** | Risk circuit breakers & hard caps | A | 5 | 5 | 5 | **4.85** | ✅ |
| **3** | Trend / TSMOM — multi-lookback ensemble | B | 5 | 5 | 5 | **4.55** | ✅ |
| **4** | Signal-reversal exit + wide ATR catastrophe stop | B | 5 | 4 | 4 | **4.10** | ✅ |
| **5** | Abnormal-volatility / spread circuit breaker | B | 5 | 4 | 3 | **3.90** | ✅ |
| **6** | Trailing ATR stop (exit upgrade) | B | 5 | 3 | 3 | **3.65** | ⬜ V2 |
| **7** | Donchian breakout as ensemble member | B | 4 | 4 | 2 | **3.50** | ⬜ V2 |
| **8** | Short-side exposure | C | 4 | 4 | 4 | **3.45** | ⬜ V1.1 |
| **9** | Second symbol (ETHUSD) + exposure caps | B | 4 | 4 | 3 | **3.45** | ⬜ V1.1 |
| **10** | Directional regime conditioning | C | 4 | 2 | 3 | **2.85** | ⬜ V2 |
| **11** | Multi-timeframe confirmation | C | 4 | 2 | 2 | **2.65** | ❌ |
| **12** | Conviction-scaled sizing | C | 5 | 2 | 2 | **2.80** | ❌ |
| **13** | Partial profit taking / break-even stop | D | 5 | 3 | 1 | **2.55** | ❌ null test |
| **14** | Funding / basis carry | A | **1** | 4 | 5 | **3.25** | ❌ stub |
| **15** | Liquidation-cascade mean reversion | C | **1** | 2 | 4 | **2.25** | ❌ |
| **16** | Cross-sectional crypto momentum | B | **1** | 4 | 3 | **2.85** | ❌ |
| **17** | Market making | A | **1** | 5 | 5 | **3.30** | ❌ structurally impossible |

Note ranks 14 and 17: **good evidence, unusable platform.** Score alone would promote them;
the implementability column is what disqualifies them. This is why implementability is scored
separately rather than folded into evidence — it keeps the reason for rejection legible, and it
tells us exactly what changes if we ever move to exchange execution.

---

## 3. Component detail

### #1 — Volatility-scaled position sizing ✅ V1

- **Evidence:** **A** for the risk claim. Volatility is persistent and forecastable; sizing by
  inverse forecast vol demonstrably stabilises realised risk. **Not** claimed to add alpha —
  Cederburg et al. (2020) show real-time volatility *timing* generally fails to beat the
  unmanaged portfolio ([RESEARCH.md](RESEARCH.md) §3.3).
- **Expected advantage:** the difference between a strategy that survives a vol regime change
  and one that doesn't. Under fixed lots, the same position is a 3× larger bet at 120% vol than
  at 40% vol — most retail EA blowups are this, not a bad signal.
- **Failure modes:** (a) the estimator lags a volatility jump, so we are largest right before a
  crash; (b) it mechanically *increases* size in quiet regimes, which is the classic low-vol
  blowup; (c) vol forecast → position size is a leverage amplifier if uncapped.
- **Mitigations (all in V1):** hard gross-exposure cap that binds regardless of the vol estimate;
  a volatility *floor* in the denominator so quiet periods cannot produce unbounded size;
  asymmetric estimator response (fast up, slow down) so risk falls quickly and rises slowly.
- **Implementation difficulty:** Low.
- **Overfitting risk:** **Very low.** One parameter (target risk) which is a *policy choice*,
  not a fitted value, and one estimator window with a broad plateau.
- **Data:** OHLCV only.
- **Test:** EXP-0004. Compare fixed-lot vs vol-scaled on identical signals. Success = lower
  realised-vol dispersion and lower max drawdown at matched average exposure. **Return
  improvement is not required and not expected.**

### #2 — Risk circuit breakers and hard caps ✅ V1

- **Evidence:** **A** — not a market claim at all, but a claim about our own equity path.
- **Expected advantage:** converts an unbounded left tail into a bounded one. Given
  `results/return_target_feasibility.md` shows a 62% chance of a >50% drawdown for a
  Sharpe-1.2 system levered to the return target, this is the component that decides whether the
  project survives long enough to learn anything.
- **Failure modes:** breakers that fire too often turn a viable strategy into a stopped one; a
  daily-loss breaker on a weekly-horizon strategy can exit the position that was about to pay.
  Breakers can also be *gap-jumped* and provide less protection than their nominal level.
- **Mitigations:** breakers halt **new entries** rather than force-liquidating existing ones,
  except the outermost kill switch; every breaker's historical trigger frequency is measured
  and reported before it ships ([RISK_MANAGEMENT.md](RISK_MANAGEMENT.md) §8).
- **Implementation difficulty:** Low logic, moderate state management (persistence, resets,
  restart recovery).
- **Overfitting risk:** **Low if set by policy, high if tuned.** Limits are chosen from risk
  tolerance *before* seeing results and are never optimised. Tuning a drawdown limit on
  historical data is curve-fitting with extra steps.
- **Test:** EXP-0005. Measure trigger frequency and P&L impact across all periods. Report how
  much return each breaker cost — the honest framing is that breakers are *insurance with a
  premium*, and we should know the premium.

### #3 — Trend / TSMOM via multi-lookback ensemble ✅ V1 — **the core signal**

- **Evidence:** **B**, the best available for anything implementable here. Moskowitz/Ooi/Pedersen
  (2012) across 58 futures; Liu & Tsyvinski (2021, RFS) documenting strong TSMOM in crypto;
  Detzel et al. finding price/MA ratios forecast daily BTC returns **in- and out-of-sample**
  across the whole 5–100 day band. See [RESEARCH.md](RESEARCH.md) §3.1.
- **Expected advantage:** the only family with (i) credible peer-reviewed crypto evidence,
  (ii) a plausible non-arbitrage mechanism (learning/attention plus leverage-driven flow), and
  (iii) zero data requirements beyond price.
- **Why *ensemble* rather than an optimised lookback — the central design decision:**
  the published evidence finds predictability across a *broad band* of lookbacks, not at a
  point. Averaging the signal over ~7 lookbacks spanning 20–200 days therefore matches the
  shape of the evidence, has **no lookback parameter to overfit**, degrades gracefully when any
  one horizon stops working, and is what large trend managers do. It also converts the most
  dangerous free parameter in the system into a fixed design choice.
- **Failure modes:** choppy ranges (death by whipsaw); sharp reversals (maximally long at the
  top); win rate of 30–40% with long losing streaks, which is a *behavioural* failure mode as
  much as a financial one. Swap cost on multi-week holds is a persistent drag
  ([RESEARCH.md](RESEARCH.md) §2.2).
- **Implementation difficulty:** Low. MA distances and a sign function.
- **Overfitting risk:** **Low as specified** — the lookback grid is fixed a priori and never
  tuned. It becomes high the moment we start adding confirmation filters.
- **Data:** OHLCV only. ✅
- **Test:** EXP-0007 (baseline), EXP-0008 (lookback-grid sensitivity), EXP-0011 (cross-asset).
  Must beat vol-targeted buy-and-hold on Sharpe out-of-sample, after full costs. **If it does
  not, V1 fails and we say so** — see §6.

### #4 — Signal-reversal exit + wide ATR catastrophe stop ✅ V1

- **Evidence:** **B** that exits shape the payoff distribution more than entries do; the
  specific parameterisation is a design choice, not a finding.
- **Expected advantage:** signal-reversal keeps the right tail intact, which is where a trend
  system's entire P&L lives. The ATR stop is a **catastrophe brake for gap and cascade risk**,
  set wide enough (3–5 ATR) that it is not a normal exit path.
- **Failure modes:** a wide stop means large individual losses; a stop that is hit is a stop
  that was probably too tight for the regime; **stops are not guaranteed** — crypto gaps through
  them, so realised loss can exceed nominal risk.
- **Mitigations:** size assuming adverse slippage past the stop (see
  [RISK_MANAGEMENT.md](RISK_MANAGEMENT.md) §4); measure realised-vs-nominal stop loss and report
  the distribution.
- **Overfitting risk:** **Moderate** — the ATR multiple is a genuine free parameter. Mitigated
  by requiring a flat performance plateau across 3–5 ATR rather than a peak.
- **Test:** EXP-0009 (stop-multiple sensitivity). Requirement: no cliff. If performance depends
  sharply on the exact multiple, the strategy is fragile and the finding is reported as such.

### #5 — Abnormal-volatility / spread circuit breaker ✅ V1

- **Evidence:** **B** for volatility persistence and clustering; the *entry-blocking rule* is a
  safety policy, defended as such rather than as alpha.
- **Expected advantage:** avoids opening positions when execution quality is worst — precisely
  when spreads blow out and slippage is largest. This is a cost-avoidance argument and it is
  measurable directly.
- **Failure modes:** high volatility is also when trends start. A blunt filter can systematically
  exclude the best entries. **This is a real risk and it must be measured, not assumed away.**
- **Mitigation:** the breaker blocks *new entries only* and never closes existing positions;
  its cost is measured explicitly in EXP-0005.
- **Overfitting risk:** **Moderate** — the percentile threshold is a free parameter. Set from
  the spread distribution (a cost argument) rather than from P&L (a fitting argument).
- **Data:** OHLCV + live spread. Note spread history is not reliably available in the MT5 tester,
  so the backtest models it and the live system measures it. That gap must be stated in results.

### #6 — Trailing ATR stop ⬜ V2

The credible exit upgrade. Deferred because it adds a second free parameter to the exit rule
and V1 must establish a baseline first. Pre-registered hypothesis: improves Calmar via drawdown
reduction; **reduces** total return by exiting trends early. Test EXP-0013.

### #7 — Donchian breakout as ensemble member ⬜ V2

**Not a diversifier.** Correlated ~0.7–0.9 with MA trend signals — it is the same effect measured
differently ([RESEARCH.md](RESEARCH.md) §3.2). Adding it risks a false sense of robustness.
Worth testing only as an *alternative estimator inside* the trend ensemble, with the explicit
requirement that it improve out-of-sample results over the MA-only ensemble. Also carries the
worst execution profile in the system: breakouts fill at peak spread and peak slippage.

### #8 — Short-side exposure ⬜ V1.1

Deferred one step, deliberately. Rationale: crypto's unconditional drift has been strongly
positive, so a long/flat system's backtest is flattered by beta while a long/short system is
not. Running long/flat first and long/short second makes the beta contribution **visible** —
if long/short is much worse, we have learned that the "edge" was largely directional exposure.
That is a diagnostic worth one iteration. Additional short-side frictions: asymmetric and often
punitive swap; short squeezes produce the fat left tail; borrow-equivalent costs embedded in CFD
financing.

### #9 — Second symbol (ETHUSD) + exposure caps ⬜ V1.1

Adds breadth, which [RESEARCH.md](RESEARCH.md) §2.1 identifies as the binding constraint on
achievable Sharpe. But BTC/ETH correlation of 0.7–0.9 means the effective breadth gain is
roughly 1 → 1.3, not 1 → 2. Requires portfolio-level exposure caps *before* it is safe to add,
because two correlated positions at full size is one position at 2× size. Handled as an
**aggregate exposure cap**, not a correlation optimiser — correlation estimates are too unstable
at our sample sizes to optimise against.

### #10 — Directional regime conditioning ⬜ V2

The brief's nine-regime taxonomy is a good analytical vocabulary and a poor implementation.
~2,900 daily bars across nine states is ~320 bars per state before accounting for imbalance, and
every state boundary is a fitted parameter ([RESEARCH.md](RESEARCH.md) §3.6). If pursued: at most
**three** states, features disjoint from the signal's, hysteresis to prevent flip-flopping, and
validated on assets it was not fitted on. Must beat the always-on baseline out of sample.

### #11 — Multi-timeframe confirmation ❌

Usually adds parameters without adding independent information — an H4 trend and a D1 trend on
the same instrument are largely the same variable sampled twice. No credible evidence found that
it improves genuine out-of-sample performance. Not scheduled.

### #12 — Conviction-scaled sizing ❌ V1

Mapping `|score|` to position size is intuitive and appealing. It is also a second-order effect
that requires the score to be *calibrated* — i.e. that a 0.8 score really does predict better
than a 0.4 score. We have no evidence for that calibration and cannot establish it at our sample
sizes. V1 uses a binary mapping. Revisit only if score-decile analysis on out-of-sample data
shows monotonic returns across deciles (EXP-0019, exploratory).

### #13 — Partial profit taking / break-even stop ❌ — **pre-registered null test**

- **Pre-registered prediction: both reduce expectancy.** In a positive-skew trend system the
  top handful of trades produce all the profit; taking half off at +1R systematically removes
  half of exactly those trades. Break-even stops convert winners into scratches on ordinary
  retracement noise.
- Tested anyway (EXP-0014) because it is cheap, because the prediction is falsifiable, and
  because recording a *pre-registered failed prediction* is worth more than not testing —
  it calibrates how much to trust our other priors.
- If it improves risk-adjusted return out of sample, the prior was wrong and it ships. That is
  what pre-registration is for.

### #14 — Funding / basis carry ❌ stub — **best economics we cannot access**

Mechanically observable cash flow rather than a statistical artefact, which is rare and valuable.
But MT5 crypto CFDs expose no funding rate, no open interest, and no spot/perp basis, and there
is no second leg to hedge. The reported Sharpe of 6.45 (2020–2025, decaying to 4.06 in 2024 and
negative in 2025) is **Grade C and almost certainly overstated** — a Sharpe of 6 in a liquid
public market should trigger disbelief. The likely omissions are exchange counterparty risk
(no FTX in the sample), short-leg liquidation risk, and a left tail a 5-year window may simply
not contain. **Action: `IExternalDataProvider` stub only** ([ARCHITECTURE.md](ARCHITECTURE.md)
§4.6). This is the single highest-value addition *if* the project ever moves to exchange
execution — which is a strategic decision worth making explicitly rather than drifting into.

### #15–17 — Mean reversion, cross-sectional momentum, market making ❌

- **Liquidation-cascade mean reversion:** real mechanism, wrong platform. The edge lives at
  hourly horizons and 10–20 bps round-trip CFD costs consume it; proper identification needs
  liquidation and OI feeds MT5 does not provide. Negative skew also interacts badly with a high
  return target.
- **Cross-sectional crypto momentum:** Liu/Tsyvinski/Wu (2022, JF) establish market, size and
  momentum as the crypto three-factor model (**Grade B**) — but it needs a broad cross-section.
  A broker offering 5–20 large-cap crypto CFDs cannot construct the size factor at all and
  gives negligible momentum breadth.
- **Market making:** structurally impossible. On a CFD we are the spread *taker*; we cannot post
  quotes. Excellent evidence, zero applicability. Listed so the rejection is on record.

---

## 4. Prohibited by design

Not "discouraged" — prohibited, enforced by the risk engine's `approved_lots <= requested_lots`
invariant and by review.

| Prohibited | Why |
|---|---|
| **Martingale / averaging down** | Produces a beautiful equity curve for years, then loses the account in one event. The smoothness *is* the warning sign |
| **Grid systems without a stop** | Same failure with extra steps |
| **Adding to losers** | Any size increase against an open loss |
| **Removing or widening a stop on an open losing position** | Turns a bounded loss into an unbounded one |
| **Re-optimising parameters on the test set** | Destroys the only unbiased estimate we have |
| **Trading a signal computed from the forming bar** | Look-ahead bias, structurally prevented ([ARCHITECTURE.md](ARCHITECTURE.md) §6.1) |

---

## 5. The minimum viable V1

**Design intent: the smallest system that is capable of being *wrong in a detectable way*.**
V1 is not meant to be good. It is meant to establish an honest baseline against which every
later addition must prove itself.

### 5.1 Specification

| Element | V1 choice | Rationale |
|---|---|---|
| **Instrument** | BTCUSD, single symbol | Deepest liquidity, tightest spread, longest history |
| **Timeframe** | D1 signal, evaluated on bar close | Multi-week horizon amortises 10–20 bps round-trip cost. Intraday is cost-dead |
| **Direction** | **Long / flat only** | Makes the beta contribution visible before shorts are added (§#8) |
| **Signal** | Equal-weight sign of `close/MA(n) − 1` over `n ∈ {20, 40, 60, 90, 120, 160, 200}` → score ∈ [−1, +1] | Matches the shape of the published evidence; **no lookback to overfit** |
| **Entry rule** | `score ≥ +0.5` (majority of horizons long) → target long | One threshold, deliberately at a round, non-tuned value |
| **Exit rule** | `score ≤ 0.0` → flat | Signal reversal preserves the right tail |
| **Position sizing** | `lots = (equity × target_risk) / (vol_forecast × price × contract_size)`, target_risk = 15% annualised | Vol scaling; 15% is a policy choice, not fitted |
| **Vol forecast** | 30-day realised vol of daily log returns, floored at 20% annualised | Floor prevents unbounded size in quiet regimes |
| **Hard cap** | Gross notional ≤ 1.0 × equity | Binds regardless of what the vol estimate says |
| **Catastrophe stop** | 4 × ATR(14) from entry, never widened | Gap/cascade brake, not a profit mechanism |
| **Circuit breakers** | Daily −4%, weekly −8%, peak DD −20% (halt new entries); spread > 3× median (block entry); realised vol > 95th pct (block entry) | Policy limits, chosen before results, never tuned |
| **Regime module** | Continuous `vol_scalar` only. No directional labels | No thresholds to overfit |
| **External data** | Stub returning `None` | We do not have it, so we do not pretend to |

**Free parameters that are genuinely fitted: zero.** Every number above is either a policy
choice (risk targets, limits), a fixed grid chosen a priori (lookbacks), or a convention
(ATR-14, 30-day vol). This is the point. It means V1's out-of-sample result is close to an
*unbiased* estimate of the trend edge in crypto — which is exactly the number we need before
deciding whether this project has a future.

### 5.2 Benchmarks V1 must be measured against

A strategy is only meaningful relative to what you would otherwise do. All four, always:

| # | Benchmark | Why it matters |
|---|---|---|
| B1 | **Buy & hold BTC** | The honest alternative. If we cannot beat it risk-adjusted, we are adding complexity for nothing |
| B2 | **Volatility-targeted buy & hold BTC** (same 15% target, same caps) | **The real benchmark.** Isolates whether the *signal* adds anything beyond the *sizing*. Most crypto "strategies" beat B1 purely through vol scaling |
| B3 | **Random-entry control**: identical sizing, risk, and exit logic; entry timing randomised, matched exposure, 1,000 seeds | Tells us whether the entry signal contains information or whether the risk framework is doing all the work |
| B4 | **Zero-edge pipeline control**: the whole pipeline run on synthetic GBM data with no edge | If the pipeline "finds" a strategy on random data, the pipeline is broken. See [BACKTESTING_PROTOCOL.md](BACKTESTING_PROTOCOL.md) §7 |

**B2 is the one that matters.** It is also the one almost never reported, because it is the one
most strategies fail.

### 5.3 Success and kill criteria — declared before any test is run

**V1 passes** only if all of:

1. Out-of-sample Sharpe > B2 (vol-targeted buy & hold) by a margin that survives the Deflated
   Sharpe correction at our logged trial count.
2. Out-of-sample Sharpe > 95th percentile of the B3 random-entry distribution.
3. ≥ 100 independent trades across the full sample.
4. Positive out-of-sample expectancy at **2× baseline spread and 2× baseline swap**.
5. Parameter perturbation of ±30% on every non-fixed input degrades median Sharpe by < 25% with
   no sign flip.
6. Directionally consistent results on ETHUSD *without any retuning*.
7. Signal parity between Python and MQL5 on 100% of bars.

**V1 is killed** if any of:

- It fails to beat B2 out of sample. → The signal adds nothing; the honest report is
  "vol-targeted buy & hold is the better product," and that conclusion gets written up.
- It requires a specific lookback grid to work. → Overfit; the ensemble premise is falsified.
- Out-of-sample results invert in sign versus in-sample. → No edge.
- It only works on BTC and inverts on ETH. → Asset-specific curve fit.
- It requires > 1.5× gross leverage to be interesting. → The edge is too small to lever safely
  given the drawdown mathematics in `results/return_target_feasibility.md`.

**A killed V1 is a successful project outcome.** It costs weeks and saves an account. The
failure mode to fear is not "V1 doesn't work" — it is "V1 doesn't work and we adjust it until
the backtest says it does."

#### A conflict between two of these criteria, flagged rather than hidden

Criterion 3 requires **≥ 100 independent trades**. But EXP-0007 predicts V1 generates only
**4–12 trades per year**. Over the development-plus-validation window (2017–2023, 7 years) that
is **28–84 trades** — and even across the entire available history it is roughly 39–116.

**V1 will probably not meet its own trade-count criterion.** This is not an oversight to be
patched by loosening the threshold; it is a real and serious limitation on statistical power,
and it is intrinsic to trading a slow signal on one asset. It deserves to be stated plainly
before any result is produced, because afterwards it will be tempting to treat it as a detail.

How it is handled — decided now, not after seeing results:

1. **Pool across assets with a correlation haircut.** Five crypto assets at 0.7–0.9 correlation
   give an effective sample nearer 1.5–2× the single-asset count, not 5×. The haircut is
   computed and reported, never assumed away.
2. **Rely on the CPCV out-of-sample Sharpe *distribution* rather than a point estimate**
   ([BACKTESTING_PROTOCOL.md](BACKTESTING_PROTOCOL.md) §4, Stage 4). With few trades, the
   dispersion *is* the finding.
3. **Report the resulting confidence intervals in full and refuse to round them away.** With
   ~50 trades, a Sharpe point estimate carries an interval so wide that "we cannot tell" will
   often be the correct conclusion — and reporting that is the whole point of this project.
4. **The trade-count criterion is downgraded from a pass/fail gate to a reported quantity**,
   and the gate is replaced by: *the CPCV Sharpe distribution's 5th percentile must exceed B2's
   point estimate.* This is a stricter test than a trade count, not a weaker one.

This adjustment is recorded here, before any data has been seen, precisely so it cannot later be
mistaken for a threshold moved to accommodate a disappointing result.

### 5.4 What V1 is expected to produce

Stated in advance so we cannot rationalise afterwards. Based on
[RESEARCH.md](RESEARCH.md) §2.1 and §6:

- **Expected net Sharpe: 0.3–0.7.** Anything above 1.0 out of sample triggers a full adversarial
  review before it is believed.
- **Expected CAGR at 15% target vol: 5–12%.** At the compounding ceiling `exp(S²/2) − 1`, a
  Sharpe of 0.5 caps out at **13.3% CAGR at any leverage.**
- **Expected max drawdown: 15–25%.**
- **Probability V1 beats B2 out of sample: genuinely uncertain — call it 40–60%.** Stating a
  number now is what makes the eventual result informative.

This is a long way from 60–75%. It is what the arithmetic supports. If the evidence later
supports more, the evidence will say so.

---

## 6. Reporting commitment

When V1 completes, the report states — in this order, whatever the numbers say:

1. Whether it beat B2. (First. Not buried.)
2. Full metrics on the locked test set, reported once.
3. The trial count and the Deflated Sharpe.
4. Every experiment run, including failures, per [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md).
5. The adversarial review, with each attack and its outcome.
6. A recommendation that may be "stop."
