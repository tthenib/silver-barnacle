# 06 — The Minimum Viable Baseline Strategy

Status: **accepted**  ·  Hypothesis ID: **H-001**  ·  Last reviewed: 2026-08-18

---

## 1. What the baseline is actually for

The baseline's primary job is **not** to make money. It is to be a *known-answer test for the
research apparatus*.

Time-series momentum / trend following is the most extensively studied and most widely
replicated systematic effect available to a retail trader. Its approximate behaviour is
documented across decades and asset classes: a modest Sharpe, a low win rate, positive skew,
long drawdowns, and a strong dependence on a minority of large winners.

That gives us a **prior** — and priors are what make a research framework falsifiable:

> If our harness reports a Sharpe of 2.5 with an 8% maximum drawdown for a Donchian breakout on
> EURUSD, **the harness is wrong**, not the strategy.

A framework whose first result is an unfamiliar strategy has no way to distinguish "we found
something" from "we have a look-ahead bug". Starting from a well-characterised strategy means
the first end-to-end result is diagnostic of the *infrastructure*.

Secondary jobs: exercise every module end to end, and establish whether a genuine, cost-
surviving edge exists on this broker's instruments — which is the actual research question.

---

## 2. The hypothesis

**H-001.** *Liquid futures-like instruments exhibit time-series momentum: instruments that have
risen over a multi-week horizon are more likely than chance to continue rising over the
following weeks, and symmetrically for declines. A simple breakout rule can capture this net of
realistic transaction costs.*

### Why it might work

Three mechanisms have been proposed, and none requires the market to be irrational in an
implausible way:

1. **Slow information diffusion** — participants update beliefs at different speeds, so prices
   adjust to new information over days rather than instantly.
2. **Risk transfer** — hedgers systematically pay speculators to absorb directional risk, and
   that premium accrues to whoever is positioned with the flow.
3. **Behavioural** — under-reaction to news followed by over-reaction as a trend attracts
   attention.

The honest counter-arguments, recorded here so they are not rediscovered later as surprises:
the effect has been widely known and traded for decades and may be substantially arbitraged
away; published results generally reflect diversified portfolios of 50+ futures markets, not
6 CFDs at one retail broker; and CFD costs are materially higher than institutional futures
costs.

### What would disprove it

- Net-of-cost expectancy indistinguishable from zero out-of-sample.
- Positive results only within a narrow parameter neighbourhood.
- Edge smaller than the cost tolerance threshold (§7).
- Profit concentrated in fewer than 5 trades.

---

## 3. Specification

### 3.1 Instrument panel

| Symbol | Group | Factors | Rationale |
|--------|-------|---------|-----------|
| EURUSD | fx_major | usd −1, eur +1 | Tightest spread in FX |
| GBPUSD | fx_major | usd −1, gbp +1 | Liquid; distinct from EUR |
| USDJPY | fx_major | usd +1, jpy −1 | Opposite USD sign — tests factor model |
| AUDUSD | fx_major | usd −1, aud +1 | Commodity-linked FX |
| XAUUSD | metal | usd −1, gold +1 | Different asset class; strong historical trends |
| US500 | equity_index | usd +0.3, equity +1 | Equity risk factor; different behaviour |

Six instruments spanning three risk factors. Small enough that data quality can be verified
per instrument by hand; broad enough that the panel is not a single bet.

**Panel selection is pre-registered and frozen before any testing.** Choosing instruments after
seeing results is instrument cherry-picking, which is the most effective way to manufacture a
false discovery, and it is invisible in the final report unless prevented up front.

#### ⚠ Open decision: panel width at £100,000 — pending confirmation

The six-instrument panel above was sized partly by the £2,000 constraint, where sizing
granularity limited how many positions could be held at meaningful risk. At £100,000 that
limit is gone, and §5 of [`00`](00-consolidated-understanding.md) argues directly for breadth:
applying one rule across more weakly-correlated instruments accumulates evidence faster than
any other lever available to this project.

**Recommendation — widen to 10, adding risk factors rather than more USD legs:**

| Addition | Group | New factor contributed |
|----------|-------|------------------------|
| EURJPY | fx_cross | First non-USD-legged pair — a genuinely different bet |
| GER40 (or UK100) | equity_index | European equity + European session; US500 is US-session only |
| USOIL | energy | Entirely new factor; historically strongly trending, so well suited to the baseline |
| NZDUSD | fx_major | Modest FX breadth |

Deliberately **not** added: USDCHF, USDCAD, more USD majors (the factor model would show these
as largely the same USD bet); XAGUSD (highly correlated with the gold already in the panel);
NAS100/US2000 (highly correlated with US500). Four more instruments that move together are four
more chances to find a spurious pattern and almost no extra independent evidence.

If the panel widens, per-position risk drops to 0.25% so the heat budget permits ~8 concurrent
positions (see §3.5).

**This must be settled before any test is run**, because revising it afterwards is
cherry-picking. Until confirmed, the frozen panel remains the six above.

### 3.2 Timeframe and timing

- **Decisions:** D1 bar close.
- **Execution:** market order on the next bar's open.
- **No intrabar decisions of any kind.**

Daily bars are chosen for three reasons: turnover is low enough that transaction costs cannot
dominate the result (so a gate failure is informative about the *signal*, not the plumbing);
D1 minimises the number of decisions and therefore the overfitting surface; and it removes
intraday session and timezone complexity from the first end-to-end system.

### 3.3 Rules

```
Entry  (evaluated at D1 close, all instruments, identical parameters):
   LONG   if close > max(high[1..N])         # N-bar Donchian breakout, prior bars only
   SHORT  if close < min(low[1..N])

Initial stop:
   LONG   stop = entry − k × ATR(A)
   SHORT  stop = entry + k × ATR(A)

Exit (whichever occurs first):
   1. Stop hit (broker-side stop order — always present)
   2. Opposite Donchian channel of length M breached
   3. Trailing stop: ratchets to k × ATR(A) from the best close since entry,
      never moves adversely

Sizing:
   risk_fraction = r  of SizingBasis, per position
   lots = quantise_down( r × SizingBasis / (|entry − stop| × value_per_price_unit) )

Position rules:
   - One position per instrument at a time
   - No pyramiding, no averaging, no re-entry on the same bar
   - Both directions permitted
```

### 3.4 Parameters — the entire set

| Param | Symbol | Baseline | Sweep range | Notes |
|-------|--------|----------|-------------|-------|
| Entry lookback | N | 50 | 20–100 | The single alpha parameter |
| Exit lookback | M | 25 | N/4 – N/2 | Constrained: `M < N` |
| ATR period | A | 20 | 14–30 | Volatility scale |
| ATR stop multiple | k | 3.0 | 2.0–4.0 | Stop distance |
| Risk per position | r | 0.5% | 0.25%–1.0% | Risk config, not alpha |

**Five parameters, of which one is genuinely alpha-bearing.** `M` is constrained to a fraction
of `N`, `A` and `k` are volatility-scaling rather than signal parameters, and `r` does not affect
the *shape* of the return stream at all. Effective alpha dimensionality is therefore close to one.

**The same values apply to all six instruments.** Per-instrument tuning would multiply the
parameter count by six and destroy the breadth that makes the estimate credible. See
[`adr/ADR-0003-shared-parameters-across-instruments.md`](adr/ADR-0003-shared-parameters-across-instruments.md).

### 3.5 Portfolio-level constraints (risk engine, not strategy)

| Constraint | Baseline value | Reasoning |
|------------|----------------|-----------|
| Max open positions | 4 | Falls out of the heat budget: 4 × 0.5% = the 2.0% cap. Not a quantisation limit |
| Max portfolio heat | 2.0% | Total simultaneous risk if every stop is hit |
| Max factor exposure | 1.0% risk per factor | Prevents 4 disguised USD bets |
| Max per-instrument exposure | 1 position | No stacking |
| Daily loss limit | 2.0% | Halt for the day |
| Weekly loss limit | 4.0% | Halt for the week |
| Peak-to-trough halt | 15% | Full stop, manual reset, review required |
| Max margin utilisation | 20% | Far below broker limits, deliberately |

Portfolio heat of 2.0% with per-position risk of 0.5% means at most 4 concurrent positions can
be at full size — which is why the position cap and the heat cap are consistent rather than
independently chosen. Under a fully correlated shock the worst case is a 2% day, which the daily
loss limit also bounds.

**These three numbers are coupled, and widening the panel means changing the per-position risk,
not the heat.** Panel width, per-position risk, and portfolio heat cannot be set independently:
`max_positions ≈ heat ÷ per_position_risk`. A 10-instrument panel that can only ever hold 4
positions wastes most of its breadth, since the whole statistical argument for a wide panel is
accumulating partly-independent observations concurrently. The correct adjustment is to **lower
per-position risk** (0.25% → 8 concurrent positions) rather than to raise heat, because heat is
the quantity bounded by drawdown tolerance and drawdown tolerance has not changed.

---

## 4. Expected behaviour (recorded *before* testing)

Pre-registering the expectation is what makes the first result interpretable. From the published
characteristics of trend-following systems:

| Metric | Expected range | Interpretation if far outside |
|--------|----------------|-------------------------------|
| Annualised Sharpe (net) | 0.2 – 0.8 | **> 1.5 ⇒ suspect a bug**, not a discovery |
| Win rate | 30 – 45% | > 60% ⇒ suspect exit look-ahead |
| Payoff ratio (avg win / avg loss) | 1.8 – 3.5 | < 1.2 ⇒ stops are too tight for the signal |
| Max drawdown | 15 – 35% | < 10% ⇒ suspect the risk model or the cost model |
| Trades per instrument per year | 4 – 12 | > 30 ⇒ N is too short; costs will dominate |
| Return skew | Positive | Negative ⇒ this is not behaving like trend following |
| Longest drawdown | 12 – 30 months | Shorter is implausible for this family |

**The right-hand column is the point of the table.** These are tripwires for infrastructure
bugs, not performance targets. A result that is *too good* triggers an investigation with the
same urgency as one that is too bad — arguably more, since a bad result is merely disappointing
while a spuriously good one is actively misleading.

---

## 5. Data requirements and an unresolved question

Target: ≥15 years of D1 history per instrument (~3,900 bars each; ~23,400 panel observations,
yielding perhaps 400–1,000 trades total).

Note against [`00`](00-consolidated-understanding.md) §5: even 15 years of a 6-instrument panel
gives a Sharpe standard error of roughly 0.2–0.3 depending on realised cross-instrument
correlation. **We should expect wide confidence intervals and plan to report them honestly
rather than to overcome them.**

**Open question — real tick availability.** "Every tick based on real ticks" depends on the
broker having stored real tick history, and depth varies widely by broker and symbol; several
years is common, fifteen is not.

*Resolution, and it is a measurement rather than an assumption:* `ExportTickStats.mq5` (S1)
measures actual tick depth and spread distributions per instrument on the target broker. The
result determines the modelling strategy:

- **M1-based modelling** for the long history (D1 decisions with next-open execution are
  relatively insensitive to intrabar tick detail),
- **real-tick modelling** for whatever recent period supports it,
- and a **cross-check** of the overlapping period to quantify the difference between the two.

If the overlap shows a large discrepancy, the long-history result is downgraded accordingly and
the report says so. This turns an unknown into a measured quantity with a stated impact — the
alternative, quietly assuming M1 modelling is adequate, is exactly the kind of unexamined
assumption that produces unrealistic backtests.

---

## 6. Modules exercised

The baseline is a complete integration test of the system:

| Module | Exercised by |
|--------|-------------|
| Config + validation | 5 parameters, 6 instruments, cross-parameter constraint `M < N` |
| BarProvider | D1 closed bars across 6 symbols |
| DataQuality | Weekend gaps, holidays, index vs FX session calendars |
| Features | ATR, Donchian, validity gating, warm-up |
| Strategy | Full `IStrategy` contract including `Describe()` |
| PortfolioState / ExposureModel | Multi-position USD factor aggregation |
| PositionSizer / LotQuantiser | FX, JPY-quote, gold, index — four different specs |
| RiskEngine | All 15 checks reachable |
| CapitalLedger | Monthly allocation over a multi-year run |
| CostModel | Spread + commission + slippage + swap on multi-day holds |
| Execution | Market entries, broker stops, stop modification, exits |
| Telemetry | Full journals across hundreds of trades and rejections |

If any module is *not* exercised by the baseline, that is a signal the module may not be needed
yet — and it gets re-examined against R10 rather than kept on the assumption it will be useful
later.

---

## 7. Acceptance criteria specific to H-001

Beyond the standard gates in [`08-acceptance-criteria.md`](08-acceptance-criteria.md):

1. **Cost tolerance > 2 SD** of the measured spread distribution for every instrument in the
   panel. A trend system on daily bars with 4–12 trades per year per instrument *should* have
   ample cost headroom; if it does not, either the signal is far weaker than expected or the
   implementation is trading too often.
2. **Directional symmetry** — long and short results are reported separately. A strategy
   profitable only long on an appreciating asset over the sample is not demonstrating momentum;
   it is demonstrating that the asset went up.
3. **Per-instrument breakdown** — reported for all six, with no requirement that all six be
   profitable. Demanding uniform profitability would invite dropping the losers, which is
   cherry-picking. What matters is that the *panel* result is not driven by one instrument.
4. **Cross-instrument consistency** — the sign of expectancy should be positive for a majority
   of instruments. A panel result that is positive only because one instrument was extraordinary
   is a single observation wearing a panel's clothing.

---

## 8. What comes after the baseline — in all three cases

**If H-001 passes all gates:** it becomes the reference against which every later addition is
measured. No component enters the system unless it improves on the validated baseline
out-of-sample, after costs, after deflation.

**If H-001 fails:** that is a legitimate and informative result. Trend following on 6 retail CFD
instruments may simply not survive retail costs — which is worth knowing, is consistent with the
counter-arguments in §2, and would be recorded as such. The apparatus will have proven it can
return a negative verdict, which is the capability the brief asks for most explicitly.

**If H-001 produces results far outside the §4 expectations in either direction:** the
investigation targets the infrastructure first. Verified bug fixes are re-run; unexplained
discrepancies block progression to later stages until they are explained. "We could not explain
it but the numbers were good" is not a state this project is permitted to move forward from.
