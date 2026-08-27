# RESEARCH.md — Evidence Survey for a Crypto MT5 Expert Advisor

**Status:** Phase 1 complete. No code written beyond a reproducible feasibility calculation.
**Last updated:** 2026-08-26
**Owner:** quant research
**Companion documents:** [STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [BACKTESTING_PROTOCOL.md](BACKTESTING_PROTOCOL.md)

---

## 0. How to read this document

This is a survey of what is actually *known* about systematic crypto trading, graded by
evidence quality, followed by an assessment of what is implementable on MetaTrader 5.

Two rules govern everything below:

1. **A claim is worth exactly as much as the evidence behind it.** Every substantive claim
   carries an evidence grade (A–E, defined in §1). Grades are assigned pessimistically.
2. **Implementability is a filter applied *after* evidence, not before.** Several strategies
   with excellent evidence are not implementable on an MT5 crypto CFD account. Saying so is
   more useful than pretending otherwise.

### 0.1 A note on the source document supplied with this brief

The brief was accompanied by *"Designing a Robust MT5 Expert Advisor for Long-Term,
Risk-Adjusted Profitability."* It is a sensible architectural sketch and its risk-control
instincts are sound. However, **its citations are not verifiable.** Every reference is an
opaque internal marker of the form `【8†L156-L164】` with no bibliography, no author, no title,
and no URL. The document therefore cannot be used as an evidence base, and several of its
specific numbers should be treated as **Grade E (unsupported)** until independently sourced:

| Claim in the source PDF | Status here |
|---|---|
| "Trend strategies yield Sharpe ~0.5–0.8" | Plausible, but the cited range is for *diversified multi-asset portfolios*, not single instruments. See §3.1 — this distinction is the single most important thing in this document. |
| "Mean-reversion can achieve higher Sharpe ~0.8–1.2" | **Unsupported.** No verifiable source. Contradicted by the cost analysis in §2.2 for retail CFD execution. Do not design around this. |
| "Momentum: 12% annual premium" | Refers to the cross-sectional equity momentum premium. Not transferable to a 1–3 instrument crypto CFD book. |
| "Ensemble of weak strategies outperforms any single one" | Directionally right but stated too strongly. Ensembling helps only when components are genuinely uncorrelated. See §3.8. |
| The FX-oriented instrument and cost analysis (EURUSD, 30:1 caps, $8–12/lot) | Not applicable. This project is crypto. Crypto CFD costs are an order of magnitude worse in relative terms. See §2.2. |

The PDF's architecture (Signal Engine → Risk Sizer → Execution Engine → Logging/Kill-switch)
is retained and extended in [ARCHITECTURE.md](ARCHITECTURE.md). Its evidence claims are not.

---

## 1. Evidence grading scheme

| Grade | Meaning | How we treat it |
|---|---|---|
| **A** | Independently verified or live/audited track record over a full cycle, or a mechanically-observable cash flow | Can be a load-bearing assumption |
| **B** | Credible peer-reviewed backtest, replicated or replicable, with disclosed methodology | Can motivate a hypothesis; must still be re-tested on our data and costs |
| **C** | Single unreplicated study, working paper, or credible practitioner backtest with disclosed method | Hypothesis generator only. Never load-bearing |
| **D** | Vendor-reported backtest, blog post, or undisclosed methodology | Ignore for design. Occasionally useful as a pointer to a mechanism |
| **E** | Marketing claim, unsourced number, or unfalsifiable assertion | Discard |

**Standing rule:** *no Grade C, D, or E claim may justify adding a component to the EA.*
Grade C may justify **running an experiment**. Only our own out-of-sample results — held to
[BACKTESTING_PROTOCOL.md](BACKTESTING_PROTOCOL.md) — may justify shipping.

**Sourcing note:** claims marked ✅ below were checked against a primary or publisher source
during this research session (URLs in §8). Claims marked ⚠️ are recalled background knowledge
that I could not verify to a primary source in this session, and are down-weighted accordingly.

---

## 2. Three structural constraints that dominate every design decision

Before surveying strategies, three facts constrain the entire solution space. Any proposal that
ignores them is fantasy regardless of how good its backtest looks.

### 2.1 Constraint 1 — We have almost no breadth, and breadth is where Sharpe comes from

The canonical trend-following result (Moskowitz, Ooi & Pedersen 2012, *Journal of Financial
Economics*) documents time-series momentum across **58 liquid futures** spanning equity indices,
currencies, commodities and sovereign bonds over 25+ years ✅. The strong portfolio-level
Sharpe in that literature is overwhelmingly a *diversification* result: individual-instrument
TSMOM Sharpes are typically in the 0.2–0.5 range, and the portfolio gets to ~1.0 by averaging
dozens of weakly-correlated bets ⚠️.

An MT5 crypto CFD account offers, realistically, 3–20 crypto symbols, and they are **not
independent**. BTC/ETH daily return correlation typically runs 0.7–0.9, and in stress it goes
to ~1.0 — precisely when diversification is needed. The Grinold fundamental law gives
`IR ≈ IC × √breadth`. Going from 58 near-independent bets to an effective breadth of perhaps
1.5–2 costs a factor of roughly **√(58/2) ≈ 5.4** in information ratio.

> **Implication:** we should expect a *single-asset* crypto trend system to deliver a true
> net Sharpe somewhere around **0.3–0.7**, not the 1.0+ implied by the multi-asset literature.
> Section §6 shows what that means for the return target. This is the most important
> paragraph in this document.

### 2.2 Constraint 2 — Crypto CFD transaction costs are punitive relative to the edge

We do not trade an exchange. We trade a broker's CFD, and we are always the spread-taker.
Typical retail MT5 BTCUSD conditions (broker-dependent, must be measured, not assumed):

- **Spread:** commonly 20–60 USD on a ~60,000 USD BTC quote in calm conditions ≈ **3–10 bps
  per side**, widening several-fold during volatility events and around broker maintenance windows ✅.
- **Overnight swap:** crypto CFDs charge financing, often asymmetric and often punitive
  (figures in the ~$10–50/night range per standard BTC position are reported for retail
  accounts ✅). **This is the silent killer of any position-holding strategy** and it is
  frequently omitted from MT5 backtests.
- **Slippage:** market orders on a fast-moving synthetic feed; no order-book depth is visible.

Round-trip cost of ~10–20 bps is survivable for a system holding positions for weeks. It is
fatal for anything holding hours. **This single fact eliminates most of the intraday
mean-reversion and scalping design space before we run a single backtest.**

Swap cost also creates an asymmetry the literature ignores: a strategy that is long 60% of the
time pays financing 60% of the time. Over a year at 20% annualised financing on notional, a
1.0× exposure long-biased strategy starts roughly 12% behind.

### 2.3 Constraint 3 — We cannot measure a Sharpe ratio well enough to trust a parameter search

From `results/return_target_feasibility.md` (generated, reproducible):

- The standard error of an annualised Sharpe estimate on a **5-year** sample is **≈ 0.55**.
- The *expected best* in-sample Sharpe from **500 trials on strategies with literally zero
  edge**, on a 5-year sample, is **1.37**.

A six-parameter sweep at five values each is 15,625 trials. Under the null of no skill
whatsoever, such a sweep is expected to produce an in-sample Sharpe *above the level we would
need for the return target*. **Selection noise alone can manufacture our entire target.**

> **Implication:** the number of configurations we test is a first-class quantity that must be
> logged and carried into every significance calculation (Deflated Sharpe Ratio; Bailey &
> López de Prado ✅). A strategy family with two parameters and a broad stable plateau is worth
> far more than one with six parameters and a higher peak.

---

## 3. Strategy family survey

Each promising family is assessed against the nine questions in the brief.

### 3.1 Trend following / time-series momentum — **STRONGEST CANDIDATE**

**Evidence: B** (crypto), **B/A** (cross-asset, with a live-performance caveat)

- Moskowitz, Ooi & Pedersen (2012, JFE): significant TSMOM in all 58 futures examined; past
  12-month return positively predicts future return; effect persists ~12 months then partially
  reverses ✅.
- Liu & Tsyvinski (2021, *Review of Financial Studies* 34(6):2689–2727): documents a **strong
  time-series momentum effect** in cryptocurrency, plus investor-attention predictability (a
  1-SD rise in Google search for "Bitcoin" → +2.3% two-week-ahead return) ✅. Sample is
  BTC/XRP/ETH and ends around 2018 — before institutionalisation, ETFs, and the derivatives
  build-out.
- Detzel, Liu, Strauss, Zhou & Zhu (*Financial Management*): ratios of price to moving averages
  forecast daily Bitcoin returns **in- and out-of-sample**, with predictability concentrated in
  the 5–100 day MA range, and Sharpe gains over buy-and-hold ✅. Notably, Bitcoin returns were
  largely *un*predictable by macro variables — consistent with a learning/attention mechanism
  rather than a risk premium.
- Practitioner evidence (Grayscale, "The Trend is Your Friend") reports momentum signals
  improving return *and* reducing volatility versus buy-and-hold from 2012 ✅ — **Grade C/D**:
  vendor research, and the sample starts at the most favourable possible date.
- ⚠️ Counterweight, and it matters: the live performance of the managed-futures industry over
  2010–2020 was far weaker than the academic TSMOM backtests implied. The gap between
  published TSMOM and realised CTA returns is the best available real-world estimate of how
  much a trend backtest overstates the future.

**Why might it work?** Two mechanisms, both plausible in crypto and neither requiring
"the market is dumb": (i) *slow information diffusion and learning* — for an asset with no
cash flows, price itself is the primary information channel, which is exactly Detzel et al.'s
model; (ii) *flow-driven feedback* — leveraged perpetual futures with forced liquidation create
mechanical, price-following order flow. Liquidation cascades are trend-following flows by
construction.

**What condition does it exploit?** Positive autocorrelation of returns at multi-day to
multi-week horizons; persistent directional drift.

**When does it fail?** Choppy, range-bound, mean-reverting markets — trend systems bleed via
repeated whipsaw. Also at sharp reversals (a trend system is maximally long at the top).
Expect win rates of 30–40% and long strings of small losses; the entire P&L comes from a
handful of large winners. Crypto's 2018 and 2022 drawdowns are the reference failure periods
if the system is long-only.

**What data does it require?** Only OHLCV of the traded instrument. **This is a decisive
advantage**: it is the one strong-evidence family that needs nothing MT5 cannot provide.

**Likely source of alpha?** A risk premium for holding directional exposure through
uncertainty, plus a behavioural/structural component from leverage-driven flow. Note that it
is *not* an arbitrage — it can be crowded and it can stop working.

**Implementation difficulties?** Moderate and well-understood: signal computed on closed bars
only, position sizing, swap cost on multi-week holds, and gap risk through the stop.

**Overfitting vulnerability?** *Low, if disciplined; high, if not.* The family is robust —
predictability is documented across the whole 5–100 day MA range ✅, which means we should not
be picking a single lookback at all. The vulnerability is entirely self-inflicted: adding
filters, thresholds, and confirmations until only one configuration survives.

**How to combine it?** With volatility scaling (§3.3), which is nearly orthogonal to it, and
with a crash/abnormality circuit breaker. **Not** with breakout systems, which are the same
signal in different clothing (§3.2).

**How to make it more robust?** The single highest-value technique: **ensemble across lookbacks
rather than optimise one.** Compute the signal at, say, 8 lookbacks spanning 20–200 days and
average them. This has *no free parameter to overfit*, matches the shape of the published
evidence (which finds predictability across a broad band, not at a point), degrades gracefully
when any single horizon stops working, and is what large trend managers actually do. It is also
strictly easier to defend in adversarial review than "we chose 37 because it tested best."

### 3.2 Breakout systems (Donchian, opening-range, volatility breakout)

**Evidence: B** — but for *the same underlying effect as §3.1.*

Breakout entries are a discretised trend signal: "price above the 60-day high" and "price above
the 60-day moving average" are correlated in the 0.7–0.9 range and are driven by the same
autocorrelation ⚠️. Turtle-style rules have long public histories, but they are evidence *for
trend*, not evidence for an additional independent source of return.

**Verdict:** do not treat breakout as a diversifying module. Treat it as an *alternative
estimator of the same signal*, and include it inside the trend ensemble if and only if it
improves out-of-sample results over the MA ensemble alone. Its distinct practical property is
worse execution: breakouts fill at the worst moment (peak spread, peak slippage), which in a
CFD context is a real and measurable cost disadvantage. Volatility-adjusted breakout thresholds
(e.g. N × ATR beyond a reference) are a reasonable variant to test.

### 3.3 Volatility targeting / volatility-scaled sizing — **STRONGEST NON-SIGNAL CANDIDATE**

This needs splitting into two claims that are constantly conflated.

**Claim A — vol scaling stabilises realised risk. Evidence: A (near-mechanical).**
Volatility is strongly persistent (ARCH effects; the reason GARCH exists), and crypto's
volatility clustering is among the most pronounced in any liquid asset ⚠️ but is directly
verifiable on our own data and will be. If tomorrow's volatility is forecastable, then sizing
by inverse forecast volatility demonstrably stabilises the risk actually taken. This is a
*risk-control* claim and it is solid. It is the reason a fixed-lot EA is indefensible in
crypto: the same lot size is a completely different bet at 25% vol than at 120% vol.

**Claim B — vol timing generates alpha. Evidence: B, and seriously contested.**
Moreira & Muir (2017, *Journal of Finance* 72(4):1611–1644) found volatility-managed portfolios
produce large alphas and higher Sharpe ratios ✅. But Cederburg, O'Doherty, Wang & Yan (2020,
*Journal of Financial Economics*) tested the same construction on 103 equity strategies: only
**8** showed a statistically significant Sharpe improvement, and — decisively — the
*real-time implementable* versions "generally earn lower certainty equivalent returns and
Sharpe ratios than simple investments in the original, unmanaged portfolios," attributed to
structural instability in the underlying regressions ✅.

> **Design consequence:** we adopt volatility scaling for **risk stabilisation and drawdown
> control**, and we will **not** claim or assume it adds return. If our backtest shows vol
> scaling adding alpha, that is a finding to be *suspicious of*, not celebrated.

**When does it fail?** When volatility jumps faster than the estimator updates — a gap. The
estimator is always looking backwards, so vol scaling systematically under-reacts at exactly
the moment of a crash. It also mechanically *increases* position size in quiet periods, which
is how "low volatility" strategies blow up. Both are mitigated by hard caps on gross exposure
that bind regardless of what the vol estimate says.

### 3.4 Funding-rate / basis carry — **EXCELLENT ECONOMICS, NOT IMPLEMENTABLE HERE**

**Evidence: A for the mechanism, C for the reported returns.**

The perpetual-futures funding rate is a directly observable cash flow, not a statistical
artefact — that is genuinely rare. A recent study reports the crypto carry strategy (short
perp / long spot) with an annualised Sharpe of **6.45** over 2020–2025, falling to 4.06 in 2024
and turning **negative in 2025**, with returns driven by a funding mean of ~8% at ~0.8%
volatility ✅.

**Treat the Sharpe figure as Grade C and probably overstated.** A Sharpe of 6 in a liquid
public market should trigger disbelief, not enthusiasm. The likely omissions are: exchange
counterparty risk (FTX is the reference event and a Sharpe-6 series does not contain an FTX),
liquidation risk on the short perp leg during a squeeze, withdrawal/borrow constraints,
execution slippage on two legs, and the fact that the strategy's risk is almost entirely in a
rare left tail that a 5-year sample may simply not contain. The authors' own finding that it
went negative in 2025 is consistent with crowding.

**Why it is out of scope for V1 regardless:** MT5 crypto CFDs do not expose funding rates,
open interest, or perpetual/spot basis. The broker charges a *swap* that is its own commercial
decision, not the market's funding rate, and there is no second leg to hedge against. Executing
carry requires exchange accounts and an entirely different execution stack.

**Action:** define a `IExternalDataProvider` interface (see [ARCHITECTURE.md](ARCHITECTURE.md)
§4.6) with funding/OI/basis as first-class fields, leave it unimplemented, and never let the
rest of the system assume it exists. If the project later moves to exchange execution, this is
the highest-value thing to add.

### 3.5 Mean reversion — **REJECTED FOR V1**

**Evidence: C at best for crypto at tradeable horizons; the specific claims in the source PDF are Grade E.**

Short-horizon reversal genuinely exists in crypto, concentrated in the minutes-to-hours after
liquidation cascades — over-extended forced selling overshoots and snaps back. The mechanism is
real. Three problems make it a poor fit here:

1. **Cost.** The edge lives at horizons of hours. At 10–20 bps round trip on a CFD, an edge
   that size is consumed entirely. §2.2 kills this before evidence even matters.
2. **Data.** Identifying a liquidation cascade properly needs liquidation feeds, open interest,
   and order-book data. MT5 provides none of it. Proxies (large ATR-multiple candles) are much
   weaker and much more overfittable.
3. **Payoff shape.** Mean reversion has negative skew: many small wins, occasional catastrophic
   loss when "oversold" keeps going. That interacts terribly with a high return target, because
   the strategy looks best right up until it doesn't, and its drawdowns arrive as single events
   rather than as a slow bleed you can react to.

The claim that mean reversion achieves Sharpe 0.8–1.2 versus trend's 0.5–0.8 (source PDF,
uncited) should be **discarded**. If it were true at retail cost levels it would be the most
important fact in retail trading, and it would not need an anonymous citation.

**Revisit condition:** exchange-level execution + liquidation/OI data. Not before.

### 3.6 Market-regime detection — **VALUABLE IN PRINCIPLE, OVERFIT MACHINE IN PRACTICE**

**Evidence: A for volatility regimes; C/D for directional regime classification.**

Volatility regimes are real and persistent — that is Claim A of §3.3 and it is solid.
*Directional* regime classification ("strong bullish trend" vs "weak bullish trend") is a much
weaker proposition: the labels are typically defined by the same indicators used to trade, and
the classifier is fitted on the same data as the strategy.

The brief proposes nine regimes. Consider the arithmetic: ~8 years of daily data ≈ 2,900 bars.
Nine states with per-state parameters gives ~320 bars per state, unevenly distributed, and
several states will contain fewer than 100 observations. Each state boundary is a parameter.
This is a mechanism for converting noise into confident-looking rules.

**Recommended V1 position:**
- Volatility state: **continuous, not discrete** — feed the volatility estimate into position
  sizing rather than into a discrete on/off switch. A continuous mapping has no threshold to
  overfit and no cliff edge.
- Abnormality: **one binary circuit breaker**, not a regime — realised volatility above a high
  percentile, or spread above a multiple of its median, ⇒ *stop opening new positions*. This is
  a risk control with a safety rationale, not an alpha claim, and it is defended on those terms.
- Directional regimes: **deferred to V2**, and only if a specific pre-registered experiment
  shows the regime-conditional system beating the always-on system out of sample.

**Robustness technique if we do build it:** require the regime label to be computed from
features *not* used by the signal, and require regime dwell time (hysteresis) so the classifier
cannot flip daily. Test regime-conditional performance on assets the regime was not fitted on.

### 3.7 Statistical arbitrage / pairs — **REJECTED FOR THIS PLATFORM**

**Evidence: B in equities; C in crypto.** Cointegration among crypto assets is unstable —
relationships that hold for months break permanently at protocol events, listings, and
regime shifts, and there is no fundamental anchor forcing re-convergence. On MT5 specifically:
two-leg execution across CFDs, doubled spread, doubled swap, no borrow, and correlated
margin. The economics do not work at retail CFD cost.

### 3.8 Ensembles and signal combination

**Evidence: B for the general principle, with a large caveat.**

Ensembling reduces variance **only to the extent components are uncorrelated.** Averaging three
trend-following variants (MA cross, Donchian breakout, momentum-of-returns) is not an ensemble
— it is one signal measured three ways, and it produces a false sense of robustness while
adding parameters. The source PDF's claim that combining "weak" strategies reliably beats any
single one is overstated for exactly this reason.

Where ensembling genuinely helps us: **averaging across the lookback dimension of a single
signal family** (§3.1). That is a variance reduction with no new parameters and no correlation
illusion, and it is the technique V1 should adopt.

**Weight determination.** The brief rightly asks for weights determined by validation rather
than arbitrary optimisation. The most defensible answer for V1 is **equal weights**. Optimised
weights over correlated components are notoriously unstable — estimation error in the
correlation matrix dominates any genuine signal at our sample sizes. Equal weighting is the
robust default and any optimised alternative must beat it out-of-sample by a margin that
survives the Deflated Sharpe correction.

### 3.9 Exit engineering

**Evidence: B for "exits matter"; D/E for most specific exit refinements.**

The exit rule defines the payoff distribution of a trend system more than the entry does. But
most popular exit refinements are value-destructive in a positive-skew system, and this is
arithmetic rather than opinion:

- **Partial profit taking:** truncates the right tail. In a system where the top 5% of trades
  produce all the profit, systematically taking half off at +1R removes half of exactly the
  trades that pay for everything. It reduces variance and feels good. Expect it to *reduce*
  expectancy. **Pre-registered prediction: it fails. Test it anyway and record the result.**
- **Break-even stops:** convert winners into scratches by stopping out on normal retracement
  noise. Same expected sign.
- **Time-based exits:** helpful for mean reversion (where the thesis has a horizon); usually
  harmful for trend (where the thesis is "this continues").
- **Trailing ATR stop:** the credible one. It is the mechanism that produces the positive skew
  in the first place — cut losers at a volatility-scaled distance, let winners run behind a
  volatility-scaled trail.

**V1 position:** primary exit is **signal reversal**; a wide ATR stop exists as a *catastrophe
brake*, not a profit mechanism. Everything else is a V2 experiment with a pre-registered
hypothesis and a null of "no improvement."

### 3.10 The published MT4/MT5 EA landscape — **Grade D/E almost without exception**

Surveying commercial EAs is worth doing once, to know what not to do. The characteristic
pattern of the vendor market:

- Backtests on "Open prices only" or M1-modelled ticks with a fixed, optimistic spread —
  the tester generates a *plausible* price path, not the real one, and the sequence of ticks
  does not match what actually happened ✅.
- Reported returns that come from **martingale or grid position management** — averaging into
  losers with escalating size. This produces a near-perfectly smooth equity curve for years and
  then loses the entire account in a single event. The smoothness *is* the warning sign.
- No out-of-sample period, or an "out-of-sample" period chosen after the fact.
- Swap and commission omitted.

**Verdict:** the commercial EA market is not an evidence source. Its one useful contribution is
a catalogue of failure modes, which is folded into
[docs/ADVERSARIAL_REVIEW.md](docs/ADVERSARIAL_REVIEW.md). **Martingale, grid, and
averaging-down are prohibited by design in this project** — see
[RISK_MANAGEMENT.md](RISK_MANAGEMENT.md) §7.

---

## 4. Coverage of the 23 topics in the brief

Nothing in the brief's list is silently dropped. Verdicts are justified in §3 or §5.

| # | Topic | Evidence | V1? | Verdict |
|---|---|---|---|---|
| 1 | Trend following | B | ✅ | Core signal. Multi-lookback ensemble (§3.1) |
| 2 | Momentum | B | ✅ | Same family as #1; implemented as one ensemble |
| 3 | Breakout systems | B | ⚠️ | Not diversifying; test as ensemble member only (§3.2) |
| 4 | Volatility breakouts | C | ❌ | V2 test; worst-case execution cost (§3.2) |
| 5 | Mean reversion | C/E | ❌ | Cost and data kill it on CFDs (§3.5) |
| 6 | Statistical arbitrage | C | ❌ | Not viable on MT5 CFDs (§3.7) |
| 7 | Market-regime strategies | C | ⚠️ | Vol-continuous + one circuit breaker only (§3.6) |
| 8 | Multi-timeframe systems | C | ❌ | Usually adds parameters, not information. V2 test |
| 9 | Volatility targeting | A (risk) / B-contested (alpha) | ✅ | Core sizing. Risk claim only (§3.3) |
| 10 | Dynamic position sizing | A | ✅ | Same as #9 |
| 11 | ATR-based risk management | A (as a convention) | ✅ | Stop distance + sizing denominator |
| 12 | Market structure | C | ❌ | Swing-high/low logic is discretionary and hard to falsify. V2 |
| 13 | Price action | D | ❌ | Candlestick patterns: no credible crypto evidence found |
| 14 | Volume / flow signals | C | ❌ | **CFD volume is broker tick-count, not market volume.** Unusable |
| 15 | Funding / open interest | A (mechanism) | ❌ | Not available on MT5. Interface stub (§3.4) |
| 16 | Cross-asset regime | C | ❌ | Requires external data. Stub |
| 17 | BTC/ETH dominance | C | ❌ | Requires external data. Stub |
| 18 | Correlation-based allocation | B | ⚠️ | Needed only when trading >1 symbol; correlation estimates unstable. V1 handles it as an *exposure cap*, not an optimiser |
| 19 | Adaptive stop-loss / exits | B | ⚠️ | Trailing ATR is the credible variant (§3.9) |
| 20 | Time-based exits | C | ❌ | Expected to hurt trend. V2 test |
| 21 | Trailing stops | B | ✅ | Wide ATR trail; catastrophe brake in V1 |
| 22 | Partial profit taking | D | ❌ | Expected to *reduce* expectancy (§3.9). Pre-registered null test |
| 23 | Risk-on/risk-off filters | C | ⚠️ | Implemented as a volatility/spread circuit breaker, not a market-wide filter |

---

## 5. Crypto-specific market structure (Phase 5)

| Characteristic | Reality | Consequence for design |
|---|---|---|
| **24/7 market** | No session close. "Daily bar" is an arbitrary broker-timezone convention | Bar boundaries differ between our research data (UTC) and the broker (server time, possibly DST-shifting). **Must be reconciled explicitly** or the EA trades a different signal than the research |
| **Extreme volatility** | BTC realised vol has ranged ~30%–150% annualised | Fixed lot sizing is indefensible. Vol scaling is mandatory |
| **Volatility compression over time** | ⚠️ BTC vol has trended down as the asset institutionalised — roughly 80–100%+ in 2013–2017 toward 40–50% in recent years | **Directly reduces achievable absolute return at constant Sharpe.** Historical returns are not repeatable at today's volatility. Do not extrapolate |
| **Volatility clustering** | Strong and directly measurable on our data | Vol forecasting works; also means drawdowns arrive in clusters, worsening the tail (see the GARCH rows in the feasibility results — 95th-percentile drawdown is materially worse than Gaussian) |
| **Liquidation cascades** | Real, mechanical, and the source of both trend flow and reversal opportunity | Trend benefits; gap risk through stops is elevated. Size for a stop that fails |
| **Weekend behaviour** | Underlying trades 24/7, but *broker* conditions change: wider spreads, thinner CFD liquidity, maintenance windows | Do not assume weekend bars are tradeable at quoted prices. Consider a spread gate rather than a weekend gate |
| **Exchange differences / broker feed** | The broker's quote is a synthetic derived feed, not an exchange print | **Must measure tracking difference between research data (exchange) and execution data (broker).** This is a named V1 experiment |
| **Spread** | 3–10 bps calm, multiples of that in stress | Spread gate before entry; spread modelled in backtest at realistic and stressed levels |
| **Gaps / dislocations** | Occur despite 24/7 trading (broker maintenance, flash moves) | Stops are not guaranteed. Size assuming slippage past the stop |
| **BTC/alt correlation** | 0.7–0.9 normally, → 1.0 in stress | Multi-symbol trading provides far less diversification than the symbol count suggests. Cap aggregate crypto exposure, not per-symbol exposure |
| **Funding / OI / dominance** | Rich signal set, **not exposed by MT5** | Interface stub only. Never simulate data we don't have |

---

## 6. What this means for the 60–75% return target (Phase 13)

Full derivation and tables: [`results/return_target_feasibility.md`](results/return_target_feasibility.md),
generated by [`research/analysis/return_target_feasibility.py`](research/analysis/return_target_feasibility.py)
(seeded, reproducible, no fitted data).

**The compounding ceiling.** For a strategy with true Sharpe `S` run at annualised volatility
`σ`, expected log growth is `S·σ − σ²/2`, maximised at `σ = S`. So the maximum CAGR attainable
**at any leverage** is `exp(S²/2) − 1`:

| True net Sharpe | Max possible CAGR, any leverage |
|---|---|
| 0.5 | **13.3%** |
| 0.7 | **27.8%** |
| 0.8 | **37.7%** |
| 1.0 | **64.9%** |
| 1.2 | 105.4% |
| 1.5 | 208.0% |

This is a hard ceiling — leverage beyond `σ = S` *lowers* compound growth while continuing to
raise drawdown. Read against §2.1's estimate that a single-asset crypto trend system plausibly
delivers a true net Sharpe of **0.3–0.7**:

> **A 60–75% CAGR is arithmetically out of reach unless our true net Sharpe exceeds 1.0.**
> Not "requires more risk" — *out of reach at any leverage whatsoever*.

**The drawdown attached.** Even granting the required Sharpe, the target arrives with:

| True Sharpe | Vol required for ~65% CAGR | Median MaxDD (5y) | 95th-pct MaxDD | P(DD > 50%) |
|---|---|---|---|---|
| 1.2 | 53.8% | 53.5% | 76%–90% | **62%** |
| 1.5 | 38.3% | 37.4% | 56%–76% | 12%–22% |
| 2.0 | 26.8% | 23.8% | 36%–59% | 0.2%–8% |

(Ranges span Gaussian → Student-t(4) → GARCH models. Volatility clustering barely moves the
*median* drawdown but substantially worsens the *tail* — 95th-percentile drawdown rises from
75% to 90% at Sharpe 1.2.)

**The measurement problem.** From §2.3: a 5-year Sharpe estimate has SE ≈ 0.55, and 500 trials
on zero-edge strategies is expected to produce a best-in-sample Sharpe of 1.37. **The Sharpe we
would need to hit the target is inside the noise band of a modest parameter search.** Any
backtest that "achieves" 60–75% is a priori more likely to be selection noise than skill.

**Honest position, stated once and carried forward:**

1. We will **not** design toward 60–75%. We will design toward the highest *defensible*
   risk-adjusted return and report what falls out.
2. If a candidate reaches the target band, the correct first response is heightened suspicion
   and a full adversarial review, not celebration.
3. The realistic planning expectation, given breadth and cost constraints, is a system with
   net Sharpe ~0.4–0.8 delivering **roughly 10–30% CAGR** at a tolerable drawdown — or the
   finding that we cannot beat vol-targeted buy-and-hold at all, which is a legitimate and
   valuable outcome.
4. The lever the user actually controls is **drawdown tolerance**, not return. Return is
   `Sharpe × volatility`; we can set volatility freely. The project's real deliverable is a
   defensible Sharpe. Everything after that is a dial.

---

## 7. What the survey rules in and out

**In for V1:** time-series momentum via a multi-lookback ensemble; volatility-scaled position
sizing; ATR-based catastrophe stop; signal-reversal exit; a spread/abnormal-volatility circuit
breaker; hard risk caps.

**Out of V1, retained as pre-registered experiments:** breakout as an ensemble member;
short exposure; trailing ATR upgrade; a second symbol; directional regime conditioning;
multi-timeframe confirmation; partial profit taking (as a null test).

**Out entirely on this platform:** funding/basis carry; statistical arbitrage; market making;
volume/flow signals; liquidation-cascade mean reversion; BTC-dominance filters. Each gets an
interface stub, never a simulated data source.

Ranking, scoring, and the V1 specification are in [STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md).

---

## 8. Sources

Checked during this research session:

- Moskowitz, Ooi & Pedersen, *Time Series Momentum*, JFE 104(2), 2012 — [paper](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf) · [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463) · [AQR dataset](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data)
- Liu & Tsyvinski, *Risks and Returns of Cryptocurrency*, RFS 34(6):2689–2727, 2021 — [Oxford Academic](https://academic.oup.com/rfs/article-abstract/34/6/2689/5912024) · [NBER w24877](https://www.nber.org/papers/w24877)
- Liu, Tsyvinski & Wu, *Common Risk Factors in Cryptocurrency*, JF 77(2):1133–1177, 2022 — [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13119) · [NBER w25882](https://www.nber.org/papers/w25882)
- Detzel, Liu, Strauss, Zhou & Zhu, *Learning and Predictability via Technical Analysis: Evidence from Bitcoin and Stocks with Hard-to-Value Fundamentals* — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3115846)
- Moreira & Muir, *Volatility-Managed Portfolios*, JF 72(4):1611–1644, 2017 — [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12513) · [NBER w22208](https://www.nber.org/papers/w22208)
- Cederburg, O'Doherty, Wang & Yan, *On the Performance of Volatility-Managed Portfolios*, JFE, 2020 — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0304405X2030132X) · [PDF](https://www.lehigh.edu/~xuy219/research/COWY.pdf)
- Bailey & López de Prado, *The Deflated Sharpe Ratio*, JPM, 2014 — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) · [PDF](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting* — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- Rozario, Holt, West & Ng, *A Decade of Evidence of Trend Following Investing in Cryptocurrencies*, arXiv:2009.12155, 2020 — [arXiv](https://arxiv.org/abs/2009.12155) — **Grade C.** Headline "255% walkforward annualised returns" covers Bitcoin's infancy, a period in which buy-and-hold itself returned astronomically. Not usable as support for a return target
- *Dynamic time series momentum of cryptocurrencies*, North American Journal of Economics and Finance — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1062940821000590)
- *Cryptocurrency factor momentum*, Quantitative Finance 23(12), 2023 — [Taylor & Francis](https://www.tandfonline.com/doi/abs/10.1080/14697688.2023.2269999)
- *Cryptocurrency momentum has (not) its moments*, Financial Markets and Portfolio Management, 2025 — [Springer](https://link.springer.com/article/10.1007/s11408-025-00474-9)
- *Exploring risk and return profiles of funding rate arbitrage on CEX and DEX* — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2096720925000818) — **Grade C**, see §3.4
- Grayscale Research, *The Trend is Your Friend* — [Grayscale](https://research.grayscale.com/reports/the-trend-is-your-friend-managing-bitcoins-volatility-with-momentum-signals) — **Grade C/D**, vendor research
- *Not All 99% Backtests Are Equal: How Tick Data Quality Impacts Your Strategy in MetaTrader 5* — [MQL5 blog](https://www.mql5.com/en/blogs/post/762517) — practitioner source on MT5 tester tick modelling

**Not verified in this session** (marked ⚠️ above, treated as background knowledge and
down-weighted): single-instrument TSMOM Sharpe ranges; the live-versus-backtest CTA performance
gap; BTC realised-volatility trend by era; BTC/ETH correlation levels; crypto CFD spread and
swap levels. **Each of these is directly measurable on our own data and is scheduled as a
pre-registered measurement in [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) rather than assumed.**
