# 00 — Consolidated Understanding, Source Reconciliation, and Conflict Resolution

Status: **accepted**  ·  Supersedes: nothing  ·  Last reviewed: 2026-08-18

This document is the single reconciled statement of what the project is, derived from three
source documents plus the project brief. Where the sources disagree, the resolution is
recorded here with its rationale. Nothing downstream should re-derive intent from the PDFs.

---

## 1. Source inventory

| Ref | File | Role assigned by brief | Internal evidence of vintage |
|-----|------|------------------------|------------------------------|
| **D1** | `Executive_Summary.pdf` | Original specification (lowest priority) | £20 starting capital; roadmap begins 2026-09-06 |
| **D2** | `Executive_Summary_2.pdf` | Research / technical foundation | £2,000 capital; multi-asset, multi-strategy; week-indexed plan |
| **D3** | `Designing_a_Robust_MT5_Expert_Advisor_for_Long-Term_Risk-Adjusted_Profitability.pdf` | **Primary specification / source of truth** | £2,000 capital; roadmap begins 2026-08-23 (nearest to today) |

The vintage ordering asserted by the brief (D3 newest, then D2, then D1) is consistent with
the internal timelines, so the stated priority is applied without amendment.

### 1.1 A necessary caveat about the sources

All three documents are secondary research summaries. Their inline citation markers
(`【8†L156-L164】`, `【23†L65-L72】`, …) are retrieval artefacts, not resolvable references.
None of the quantitative claims in them — "mean reversion achieves Sharpe 0.8–1.2",
"momentum earns a 12% annual premium", "trend following yields Sharpe 0.5–0.8" — can be
traced to a verifiable source from the documents alone.

**Resolution:** every numeric performance claim in D1/D2/D3 is treated as a *prior belief to
be tested*, never as an established fact and never as a target. They are useful for choosing
which hypotheses to test first. They are not evidence. No acceptance criterion anywhere in
this project is calibrated against a number taken from these documents.

The MQL5 code in all three documents is separately unreliable; see
[`10-mt5-platform-notes.md`](10-mt5-platform-notes.md) for the specific defects found. It is
not used as reference implementation.

---

## 2. What the project is

A **research and paper-trading system**, built on MetaTrader 5 / MQL5, whose purpose is to
determine — with enough statistical discipline that the answer is trustworthy — whether a
systematic trading strategy with genuinely positive out-of-sample expectancy can be
constructed and operated on a £100,000 demo/paper account.

The deliverable is *the apparatus and the verdict*, not a profitable bot. A well-built
apparatus that returns the verdict "no edge found" has succeeded. An apparatus that returns
"large edge found" and is wrong has failed catastrophically, because it will be believed.

Consequently the system is optimised for **the reliability of its own conclusions** before it
is optimised for anything else. Every design decision below traces back to that.

### 2.1 Non-goals, stated explicitly

- Not a live-money trading system. No real-capital code path is built (see §4.2).
- Not a return-target-driven system. No CAGR, multiple, or profit figure appears anywhere as
  a design input or an optimisation objective.
- Not a strategy marketplace. Breadth of strategy families is a means of testing whether *any*
  family survives, not an end.
- Not a machine-learning project. ML is permitted only at a late stage and only against
  evidence (see [`07-research-roadmap.md`](07-research-roadmap.md)).

---

## 3. Points of agreement across all three sources

These are carried forward without further debate:

1. **Modular architecture** — signal generation, risk sizing, execution, and logging must be
   separated. All three documents converge on this; the brief strengthens it to ~23 modules.
2. **Fixed-fractional position sizing** derived from stop distance, equity, and real contract
   specifications — not arbitrary lot sizes.
3. **Every trade carries a stop.** No exceptions, no hidden risk.
4. **No martingale, no grid, no averaging into losers, no size increase after a loss.**
5. **Account-level risk limits** beyond per-trade risk: daily loss, drawdown, max open
   positions, correlated exposure.
6. **Kill switch / trading disable** on breach of hard limits.
7. **Realistic cost modelling** — spread, commission, slippage, swap — applied in backtest.
8. **In-sample / out-of-sample separation, walk-forward analysis, Monte Carlo perturbation,
   parameter sensitivity, multi-instrument testing** as the validation core.
9. **Risk-adjusted metrics** (Sharpe, Sortino, Calmar/MAR, profit factor, expectancy, max
   drawdown) over gross profit.
10. **Liquid instruments only** — FX majors, major indices, gold. No exotics.
11. **Demo / paper only** at this stage.

---

## 4. Contradictions and their resolutions

### C1 — Starting capital: £20 (D1) vs £2,000 (D2, D3) vs £100,000 (current instruction)

**Resolution: £100,000, demo/paper.** Superseding both figures in the source documents, per
direct instruction on 2026-08-18. The document-priority rule is not in play here — a later
instruction from the project owner outranks all three PDFs.

*Why it matters beyond a number.* D1's £20 premise drove several of its design conclusions —
"scalping is not recommended", "even a 50% drawdown is effectively ruin", "target 10×/100×" —
and those are artefacts of the assumption, **discarded along with it**.

The £2,000 figure carried its own artefact, now also discarded: at £2,000 the binding
constraint was *lot quantisation*, because the minimum tradeable size on most instruments
corresponds to a risk step of roughly 0.2–0.4% of equity — a coarse grid against a 0.5% risk
target. At £100,000 that grid is ~50× finer and effectively vanishes for liquid instruments.

**What the increase does and does not change** is the important part, because it is easy to
assume more capital improves the research position. It does not:

| | Effect of £2,000 → £100,000 |
|---|---|
| Lot quantisation | **Resolved.** Grid falls from ~0.20% of equity to ~0.004%. See [`03`](03-module-specifications.md) §6 |
| Achievable diversification | **Improved.** Concurrent positions are no longer limited by sizing granularity |
| Instrument eligibility | **Widened.** Instruments with coarse contract sizes become tradeable at sane risk |
| Binding sizing constraint | **Inverted** — from the volume *floor* to the volume *ceiling* and margin |
| **Statistical power** | **Unchanged. Exactly.** §5 below contains no capital term |
| Anti-overfitting machinery, gates, splits, trial counting | Unchanged |
| Risk *fractions* (per-trade, heat, drawdown limits) | Unchanged — they are set by drawdown tolerance, which is scale-invariant |

The middle row is the one to internalise. A 50× larger account buys zero additional evidence,
while making a spurious result substantially more seductive: a fictitious 30% return now reads
as £30,000 rather than £600, and a number that large is much harder to abandon on the strength
of a confidence interval. The account size changed; the epistemics did not.

### C2 — Return targets: D1 "10×/100×"; D2 "20–50% CAGR aggressive blend"; brief "no claims"

**Resolution: no return target exists anywhere in the system.** The brief is explicit and it
also supersedes both documents. D2's "Strategy Blend Comparison" table — which pairs risk
levels with expected CAGR bands — is rejected in full: it asserts returns as a *consequence of
risk appetite*, which is backwards. Risk appetite determines dispersion, not expectation.

What survives from that table is only the idea of **named risk presets** (conservative /
balanced / aggressive) as configuration bundles, with the CAGR and drawdown "targets" stripped
out. Presets are capped: see C6.

### C3 — Per-trade risk: D1/D3 "1–2%"; D2 "0.5–2%"; aggressive preset "2%"

**Resolution: baseline 0.5%, hard ceiling 1.0% at portfolio level for the initial stages.**

The 1–2% convention in all three documents is a *single-position* heuristic. This system holds
multiple simultaneous positions across correlated instruments, so per-trade risk is not the
quantity that needs bounding — *aggregate risk conditional on correlated adverse movement* is.
With a panel of FX majors, gold and an equity index, a plausible worst-case correlated shock
can move most positions together. Four positions at 1% each is not 4% of risk; under a
correlated shock it is much closer to 4% of *simultaneous* loss.

The risk engine therefore bounds portfolio heat directly (see
[`03-module-specifications.md`](03-module-specifications.md) §Risk/RiskEngine), and per-trade
risk is a derived quantity, not a primary input.

### C4 — Take-profit rule: D3 "TP = 2 × SL to enforce ≥ 2:1 R/R"

**Resolution: rejected as a universal rule.** A fixed reward:risk multiple is an arbitrary
constraint that presumes the exit distribution rather than measuring it. It is also one of the
easiest ways to manufacture a flattering backtest, because the ratio interacts with the stop
distance to produce a win-rate/payoff trade-off that can be tuned until the equity curve looks
right. Exits must be specified by each strategy with a stated rationale, and the exit rule is
part of the hypothesis under test — not a global default.

Fixed R:R remains *available* as one exit policy among several, subject to the same evidence
requirement as anything else.

### C5 — Market making (D3) and HFT (D1, D2)

**Resolution: both permanently out of scope.** D3 itself concedes market making is
"high-frequency and infrastructure-intensive"; D1 correctly calls HFT "not feasible" on MT5.
MT5's execution model, retail latency, and the absence of order-book rebates make both
untestable and unrealisable here. They are removed from the strategy universe rather than
carried as aspirations.

### C6 — Leverage: D1 "assume 1:100–1:500"; D3 "UK/EU cap 30:1 on majors"

**Resolution: D3's regulatory framing is correct in direction; both numbers are replaced by
measurement.** The FCA restricts retail CFD leverage to a range between 30:1 and 2:1 depending
on the underlying asset ([FCA PS19/18](https://www.fca.org.uk/publications/policy-statements/ps19-18-restricting-contract-difference-products),
COBS 22.5) — so D1's 1:100–1:500 assumption is wrong for a UK retail account, and D3's flat
"30:1" is right only for major FX pairs.

Rather than hard-code either, the system **reads actual margin requirements from the terminal
at runtime** (`OrderCalcMargin`, `SYMBOL_MARGIN_INITIAL`, `ACCOUNT_MARGIN_MODE`) and validates
them at startup. Available leverage is an observed property of the environment, not an
assumption. Utilisation is capped independently of whatever the broker permits.

### C7 — Machine learning: D2 proposes LSTM/GBM signal models; D3 omits ML; brief warns against complexity-for-its-own-sake

**Resolution: deferred behind an evidence gate, not adopted and not banned.** MQL5 does
support ONNX model inference natively (`OnnxCreate`, `OnnxRun`, and the model can be exercised
inside the Strategy Tester), so it is technically available. It is nonetheless excluded from
stages 0–5 because the sample sizes involved (§5) cannot support model selection on top of
strategy selection. See [`07-research-roadmap.md`](07-research-roadmap.md) for the specific
preconditions.

### C8 — Statistical arbitrage / cointegration (D2)

**Resolution: deferred.** Genuine relative-value work needs a synchronised cross-sectional
panel with reliable timestamps. MT5 supplies per-symbol tick streams from a single broker with
no guarantee of cross-symbol synchronisation, and cointegration estimates over a few thousand
daily observations are notoriously unstable. Deferred to the roadmap with an explicit data
adequacy precondition rather than dropped, because currency triangles are a legitimate case
where the data may support it.

### C9 — Regime detection: implied useful by D2/D3 (session filters, "trend confirm", volatility regimes)

**Resolution: treated as an unproven hypothesis, and one with an unusually high cost of being
wrong.** Regime conditioning multiplies the hypothesis count (3 strategies × 4 regimes = 12
hypotheses, not 3) and is trivially fitted in hindsight. It is built only after a strategy has
independently cleared its gates, and it must demonstrate improvement *net of the multiple-
testing penalty its own existence creates*. See [`07-research-roadmap.md`](07-research-roadmap.md).

### C10 — Demo-only status

D1 and D2 both state the project is demo-only, citing the operator being under 18. D3 is
silent. The brief independently specifies paper/demo research.

**Resolution: demo-only, and the constraint is enforced architecturally rather than by
convention.** All three inputs agree on the outcome, so no priority ordering is needed. The
concrete consequence: the EA asserts `ACCOUNT_TRADE_MODE == ACCOUNT_TRADE_MODE_DEMO` at
initialisation and refuses to initialise otherwise. Capital allocation is paper accounting only
(C11). Nothing in the roadmap builds toward live deployment; converting this system to live
trading would be a separate project with its own review, not a configuration change.

### C11 — Profit allocation (80% retained / 20% reserved)

This appears in the brief, not in the source documents.

**Resolution: implemented as a paper ledger, entirely separate from the broker account.** The
EA cannot and must not attempt to move money. The ledger tracks four quantities the brief
requires to be distinguishable — trading equity, retained capital, reserved capital, and total
strategy-generated profit — and the *sizing basis* is derived from the ledger rather than from
raw account equity. Percentage configurable, high-water-mark based, one-way. Detail in
[`03-module-specifications.md`](03-module-specifications.md) §Capital.

### C12 — Signal combination: D2's pseudocode sums signals (`signalTrend + signalMR`)

**Resolution: rejected.** Adding a trend signal to a mean-reversion signal produces silent
cancellation and destroys attribution — a flat composite is indistinguishable from "no signal"
and from "two strategies in violent disagreement", which are opposite states requiring opposite
responses. Strategies emit *independent, attributed intents*; combination is an explicit
portfolio-layer decision made later and only if it earns its place. Until then, one strategy.

### C13 — Decision frequency: D1/D2/D3 pseudocode all act on every tick

**Resolution: signal decisions occur on bar close only.** Per-tick signal evaluation is
non-deterministic (results depend on tick delivery, which differs between tester modelling
modes and between backtest and live), makes look-ahead bugs hard to detect, and is untestable
in the reproducibility sense the brief demands. Per-tick logic is retained *only* for execution
management — stop handling, freeze-level checks, reconciliation. See
[`adr/ADR-0002-bar-close-decisioning.md`](adr/ADR-0002-bar-close-decisioning.md).

---

## 5. The constraint that shapes everything: how much evidence is actually available

This is the most important number in the project and it is absent from all three source
documents.

For approximately i.i.d. returns, the standard error of an annualised Sharpe ratio estimated
over `T` years is approximately

```
SE(SR) ≈ sqrt( (1 + SR²/2) / T )        [Lo, 2002]
```

For a strategy whose *true* annualised Sharpe is 0.5 — a realistic, respectable figure for a
retail-accessible trend system, and squarely inside the range D3 attributes to trend following
— measured over 10 years:

```
SE ≈ sqrt(1.125 / 10) ≈ 0.335
95% CI ≈ 0.5 ± 0.66  →  [-0.16, 1.16]
```

**Ten years of data cannot distinguish a genuinely good strategy from noise.** To push the
standard error down to ~0.25, so that SR = 0.5 sits two standard errors from zero, requires
roughly **18 years** of data on a single return stream.

Four consequences follow, and they drive the whole design:

1. **Breadth beats depth.** Applying one rule across `k` weakly-correlated instruments
   accumulates evidence far faster than adding years to one instrument. The instrument panel
   is therefore part of the statistical design, not a deployment detail.
2. **Shared parameters across instruments are mandatory at baseline.** Per-instrument tuning
   destroys exactly the breadth that makes the estimate credible, while multiplying the
   parameter count by `k`. See
   [`adr/ADR-0003-shared-parameters-across-instruments.md`](adr/ADR-0003-shared-parameters-across-instruments.md).
3. **Trial counting is not optional.** With confidence intervals this wide, testing a few dozen
   configurations *guarantees* an apparently significant winner. The Deflated Sharpe Ratio
   requires an honest count of trials, and humans reliably undercount. The experiment registry
   exists to make the count automatic and un-editable.
4. **The most probable honest outcome is "no detectable edge".** The system is built so that
   this outcome is *reportable and credible* rather than something to be optimised away.

---

## 6. Consolidated requirement set

What the system must do, stated once, in the form downstream documents refer to.

**R1 — Determinism.** Identical inputs, parameters, and code version produce identical output,
including logs. Any randomness is explicitly seeded and the seed is recorded.

**R2 — Provenance.** Every result traces to a code commit, a parameter set, an instrument list,
a date range, a cost model, a split definition, and a seed. Results without complete provenance
are discarded, not interpreted.

**R3 — Risk supremacy.** No strategy can place an order. Only the execution engine touches the
trade API, and it accepts only objects the risk engine produced. Enforced by a build-time
invariant check, not by convention.

**R4 — Causality.** No feature, signal, or decision may use information unavailable at the
decision timestamp. Enforced by structural means (closed-bar-only access, explicit warm-up
gating, validity flags on feature vectors) rather than by reviewer vigilance.

**R5 — Cost honesty.** Modelled costs are pessimistic by default. Every strategy reports its
*cost tolerance* — the additional round-turn cost that reduces its expected edge to zero —
measured against the observed distribution of real spreads for its instruments.

**R6 — Split integrity.** The final test set is defined once, committed, and untouched until
its designated gate. Access is a recorded, irreversible event.

**R7 — Falsifiability.** Every gate has numeric pass criteria fixed *before* the data is seen.
Every stage can fail. Failure is a reportable result.

**R8 — Graceful degradation.** On any uncertainty about its own state — reconciliation
mismatch, data gap, repeated execution errors, abnormal spread — the system's default is to
stop trading, not to continue on assumptions.

**R9 — Complete observability.** Executed trades and *rejected* trades are both logged with
enough context to reconstruct the decision. Rejections are primary research data.

**R10 — Component justification.** Every module and every parameter must be traceable to a
requirement or to experimental evidence. Components that cannot demonstrate they improve
out-of-sample performance after costs are removed.

---

## 7. What is deliberately deferred

Named here so that their absence is understood as a decision rather than an oversight.
Preconditions for each are in [`07-research-roadmap.md`](07-research-roadmap.md).

| Deferred | Reason |
|----------|--------|
| Second and subsequent strategy families | Nothing to combine until one strategy clears its gates |
| Portfolio construction / correlation optimiser | Requires ≥2 validated strategies to have any content |
| Regime detection layer | Unproven; multiplies hypothesis count (C9) |
| Ensemble / meta-strategy | Requires multiple validated strategies plus a portfolio layer |
| Machine learning (ONNX) | Sample size cannot support model selection atop strategy selection (C7) |
| Statistical arbitrage / cointegration | Data adequacy unproven for cross-sectional work on MT5 (C8) |
| Kelly-derived sizing | Requires a *stable, validated* estimate of edge; premature and dangerous before that |
| Equity-curve trading / adaptive risk | Classic overfitting vector; deferred indefinitely pending strong evidence |
| Market making, HFT | Permanently out of scope (C5) |

---

## 8. Reading order for the rest of these documents

1. [`01-architecture.md`](01-architecture.md) — system architecture and the two-tier split
2. [`02-repository-layout.md`](02-repository-layout.md) — directory and file structure
3. [`03-module-specifications.md`](03-module-specifications.md) — every module, its
   responsibilities, and the interfaces between them
4. [`04-build-order.md`](04-build-order.md) — what is built first, and what must not be built yet
5. [`05-testing-and-validation.md`](05-testing-and-validation.md) — testing strategy and the gate system
6. [`06-baseline-strategy.md`](06-baseline-strategy.md) — the minimum viable baseline strategy
7. [`07-research-roadmap.md`](07-research-roadmap.md) — the advanced research programme
8. [`08-acceptance-criteria.md`](08-acceptance-criteria.md) — numeric pass/fail criteria per stage
9. [`09-risk-register.md`](09-risk-register.md) — overfitting, false discovery, implementation
   and backtest-realism risks
10. [`10-mt5-platform-notes.md`](10-mt5-platform-notes.md) — verified MT5/MQL5 platform facts
    and the defects found in the source documents' code
