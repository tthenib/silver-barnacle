# 04 — Build Order: What to Build First, and What Must Not Be Built Yet

Status: **accepted**  ·  Last reviewed: 2026-08-18

The brief's development principle — *start with the smallest system that can generate
scientifically useful results, then add complexity only when experiments demonstrate it helps* —
is implemented as the staged sequence below. Each stage has a deliverable that can be
demonstrated, and a gate that can fail.

---

## Stage sequence at a glance

```
S0  Scaffolding ───────────────────► compiles, logs, trades nothing
S1  Risk & execution spine ────────► executes INJECTED signals correctly.  No alpha.
S2  Baseline strategy + telemetry ─► end-to-end backtestable
S3  Research harness ──────────────► reproducible, provenance-complete results
S4  Validation machinery ──────────► gates 4–6 evaluable
S5  Demo forward test ─────────────► gates 7–8 evaluable
────────────────────────────────────────────────────────────────────────
    ↓ everything below requires evidence from above
S6  Second strategy family      (only if S5 produced a verdict worth extending)
S7  Portfolio layer             (only if ≥2 strategies validated)
S8  Regime layer                (only if pre-registered and it beats its penalty)
S9  Ensemble                    (only if S7 + multiple validated strategies)
S10 Advanced research           (only per 07-research-roadmap.md preconditions)
```

Two ordering choices are deliberate and worth defending.

**Risk before alpha (S1 before S2).** The conventional order is to build a strategy, get
excited, then bolt on risk management. That produces a risk layer shaped around one strategy's
convenience and reliably bypassed under pressure. Building the risk and execution spine first,
and proving it with *injected* signals, means the first real strategy arrives into a system that
already constrains it. It also means the first thing thoroughly tested is the thing that can
actually lose money.

**Harness before second strategy (S3/S4 before S6).** Without validation machinery there is no
way to know whether a second strategy helps or merely adds surface area. Building strategies
ahead of the apparatus that judges them accumulates untested code and, worse, accumulates
*informal* opinions about which ones look good — which is unrecorded multiple testing.

---

## S0 — Scaffolding

**Build:** repo layout · `Core/` (Types, Enums, Result, Clock, Json) · `Config/` with
validation · `Telemetry/Logger` · `Diagnostics/Assert` · `Tests/TestFramework.mqh` ·
`tools/` (deploy, version header, compile, invariant linter) · CI for Python + linter.

**Deliverable:** `SilverBarnacle.mq5` compiles clean at maximum warning level, initialises,
writes a run manifest containing its git SHA, validates its configuration, refuses to start on
a bad config or a non-demo account, and places no orders.

**Exit criteria:** compiles with zero warnings; `RunUnitTests` executes and reports; the
invariant linter passes; a deliberately invalid config is rejected with a specific message.

---

## S1 — Risk and execution spine

**Build:** `Data/` (SymbolCatalog, BarProvider, DataQuality) · `Risk/` (PositionSizer,
LotQuantiser, RiskLimits, RiskEngine, DrawdownGuard, CircuitBreaker) · `Capital/CapitalLedger`
· `Costs/CostModel` · `Execution/` (TradeGateway, OrderStateMachine, IdempotencyJournal,
Reconciler, ExecutionEngine) · `Portfolio/` (PortfolioState, ExposureModel; Allocator as
pass-through) · `Telemetry/` (TradeJournal, RejectJournal) · `Diagnostics/SelfTest`.

**Deliverable:** an EA driven by a **signal injector** — a test-only component that emits
scripted intents (from a CSV, or on a fixed schedule) with no market logic whatsoever. It
sizes, risk-checks, executes, journals, and reconciles them correctly.

**Why a deliberately stupid signal source is the right call.** With a real strategy in place,
every execution anomaly invites the question "is this a bug or is the strategy behaving
oddly?" A scheduled injector removes that ambiguity entirely: every observed behaviour is
attributable to the plumbing. It also makes adversarial testing easy — inject an intent with an
absurd stop, or 50 intents at once, and watch the risk engine refuse them.

**Exit criteria:**
- Every risk check has a test that trips it and a test that passes it.
- Sizing golden table passes for 5-digit FX, JPY pairs, gold, and an index.
- Simulated restart mid-`SUBMITTED` reconciles without duplicating an order.
- Drawdown limits survive a restart.
- A full tester run on injected signals shows realised risk per trade never exceeding the
  configured cap, and the quantisation-error distribution is reported.
- `SelfTest` passes against the actual demo broker's specifications.

---

## S2 — Baseline strategy and full telemetry

**Build:** `Features/` (ATR, Donchian, Returns, FeatureVector validity) ·
`Strategy/` (IStrategy, StrategyManifest, StrategyRegistry) ·
`Strategy/Strategies/TrendBreakout.mqh` (see [`06-baseline-strategy.md`](06-baseline-strategy.md))
· `Telemetry/RunManifest`, `MetricsCollector` (`OnTester` + `FrameAdd`).

**Deliverable:** an end-to-end backtestable EA producing complete trade and reject journals.

**Exit criteria:** feature golden vectors match Python references to 1e-9; no signal is emitted
before warm-up or on an invalid feature vector; a full-history tester run completes on the
instrument panel and produces parseable journals; two identical runs produce byte-identical
journals (determinism, R1).

---

## S3 — Research harness

**Build:** `research/` registry, tester driver, ingest, metrics, split custody, CLI.

**Deliverable:** `sb run --prereg H-001 --split is` executes a tester pass and emits a metrics
report with complete provenance; `sb registry trials H-001` returns the trial count.

**Highest-risk task in the project, scheduled first within the stage:** confirm the headless
terminal loop actually works on the target machine (compile via `metaeditor64 /compile`, run via
`terminal64 /config:`, parse the report). If it does not, fall back to the semi-automated loop
described in [`01-architecture.md`](01-architecture.md) §3.2 immediately rather than burning
time on automation. Provenance is the requirement; full automation is only a convenience.

**Exit criteria:** a run is reproducible from its manifest alone; the registry refuses a run
whose binary SHA disagrees with the working tree; the holdout is inaccessible without an unlock
token; journal→DataFrame round-trip is lossless.

---

## S4 — Validation machinery

**Build:** walk-forward orchestration · sensitivity grids and plateau detection · block
bootstrap and trade-order randomisation · Monte Carlo path simulation and ruin probability ·
cost perturbation and the breakeven-cost solver · Deflated Sharpe Ratio · concentration metrics
· gate report rendering.

**Deliverable:** `sb gate G4 --hypothesis H-001` produces a pass/fail report against the
numeric criteria in [`08-acceptance-criteria.md`](08-acceptance-criteria.md).

**Exit criteria:** every statistical routine is tested against a synthetic series with a known
analytic answer (a seeded random walk must produce a Sharpe indistinguishable from zero and
must **fail** the gates — if the harness passes pure noise, the harness is broken and every
result it has produced is void).

---

## S5 — Demo forward test

**Build:** operational tooling — deployment runbook, monitoring, daily health report, live-vs-
backtest comparison in the harness.

**Deliverable:** the EA runs continuously on the demo account for the pre-registered duration,
producing journals directly comparable to backtest output.

**Exit criteria:** gates 7 and 8 in [`08-acceptance-criteria.md`](08-acceptance-criteria.md).

---

## Stages S6+ — gated on evidence

Each requires its preconditions to be satisfied and a committed pre-registration.
See [`07-research-roadmap.md`](07-research-roadmap.md).

---

# What must NOT be built yet, and why

This section exists because the failure mode it prevents is not laziness — it is enthusiasm.
Each item below is a component that would be genuinely interesting to build and that would
actively damage the project's ability to reach a trustworthy conclusion if built now.

### ✗ A second, third, or fourth strategy family

**Why not:** the framework's ability to *evaluate* a strategy is itself unvalidated until S4.
Strategies written before then cannot be judged, so writing them produces code plus informal
impressions — and informal impressions are untracked trials that corrupt the eventual
multiple-testing correction.

**Precondition:** S4 complete, and the baseline has been through gates 3–6 (whatever the
verdict — a *failed* baseline still validates that the apparatus can detect failure).

### ✗ Portfolio construction / correlation optimiser

**Why not:** with one strategy there is nothing to allocate between. A correlation matrix
estimated from a few hundred daily observations is unstable enough that an optimiser fitted to
it is fitting noise — and mean-variance optimisation is notoriously effective at converting
estimation error into confident, concentrated, wrong allocations.

**Precondition:** ≥2 strategies past gate 5, with enough overlapping history to estimate
cross-strategy correlation with a usable confidence interval.

*Built instead now:* the static, structural factor-exposure model (§Portfolio in
[`03-module-specifications.md`](03-module-specifications.md)), which encodes what is known a
priori and estimates nothing.

### ✗ Regime detection

**Why not:** three compounding problems. (1) It multiplies hypotheses — 3 strategies × 4 regimes
is 12 hypotheses, and the confidence intervals in [`00`](00-consolidated-understanding.md) §5
are already too wide for 3. (2) Regime labels are trivially fitted in hindsight; a classifier
tuned on the full sample leaks future information into every historical label. (3) Conditioning
fragments an already small sample into per-regime subsamples with far too few trades each.

**Precondition:** a pre-registered regime hypothesis with an a-priori-specified, *causal*
classifier whose parameters are fixed before evaluation, plus a demonstration that the baseline
has enough trades to survive being partitioned.

### ✗ Ensemble / meta-strategy / strategy scoring

**Why not:** the brief's own warning applies precisely — an adaptive weighting layer that
responds to recent performance is a machine for chasing winners, and it will show a beautiful
in-sample equity curve regardless of whether the underlying strategies have any edge, because
it is fitting the sequence of realised outcomes.

**Precondition:** ≥2 strategies past gate 6 individually, plus a portfolio layer, plus a
pre-registered combination rule with an explicit turnover cap.

### ✗ Machine learning / ONNX inference

**Why not:** MQL5 supports ONNX inference natively, so this is not a capability problem — it is
a statistics problem. Model selection consumes degrees of freedom on top of strategy selection,
against a sample that (per [`00`](00-consolidated-understanding.md) §5) cannot reliably resolve
a Sharpe of 0.5 for a *fixed* rule.

**Precondition:** see [`07-research-roadmap.md`](07-research-roadmap.md). The bar is
deliberately high.

### ✗ Kelly or any edge-proportional sizing

**Why not:** Kelly sizing requires an accurate estimate of edge and its variance. With edge
estimates whose confidence intervals span zero, Kelly is not "optimal growth" — it is an
amplifier applied to an unreliable number, and it fails asymmetrically: overestimating edge by
2× produces catastrophic overbetting, while underestimating merely underperforms.

**Precondition:** a strategy through gate 7 with a *stable* edge estimate across walk-forward
windows. Even then, capped fractional Kelly, and only if it beats fixed-fractional out-of-sample.

### ✗ Equity-curve trading / adaptive risk / drawdown-responsive sizing

**Why not:** these introduce a feedback loop between realised outcomes and future position size.
They are extremely attractive in backtest for the same reason they are dangerous — they are
fitted to the specific *sequence* of returns, which is the least stable property of any
strategy. Trade-order randomisation typically destroys their apparent benefit entirely.

**Precondition:** must survive trade-order randomisation, which is a hard test to pass.
Deferred indefinitely. Note the existing drawdown *guard* (which reduces exposure to zero at a
hard limit) is not this — it is a fixed, non-adaptive circuit breaker.

### ✗ News / economic calendar filters

**Why not:** no reliable, point-in-time, survivorship-free calendar is available inside MQL5 for
historical periods. A filter built on a *current* calendar applied to *past* data is look-ahead
bias in a particularly hard-to-notice form, because the calendar itself was revised after the
fact.

**Precondition:** a genuinely point-in-time historical calendar with verified as-of timestamps.
Until then, the honest substitute is measuring and *reporting* performance around known
high-volatility windows rather than filtering them out.

### ✗ Per-instrument parameter tuning

**Why not:** it destroys the breadth that makes the statistics credible and multiplies the
parameter count by the panel size. See
[`adr/ADR-0003-shared-parameters-across-instruments.md`](adr/ADR-0003-shared-parameters-across-instruments.md).

**Precondition:** an economic argument for why an instrument is *structurally* different (not
merely "it backtests better"), pre-registered before testing.

### ✗ Multi-timeframe signal combination

**Why not:** each additional timeframe multiplies the parameter space and introduces subtle
alignment bugs (a D1 bar closing at a different time than the H1 bars composing it). The
baseline uses a single timeframe deliberately.

**Precondition:** baseline validated first; then a pre-registered hypothesis that a specific
higher-timeframe filter improves OOS results, tested as an *addition* to the validated baseline.

---

## The standing rule for all of the above

> Before building any deferred component, write and commit a pre-registration stating the
> hypothesis, why it might work, how it will be tested, and **what result would cause it to be
> removed**. If the removal criterion cannot be stated, the component is not ready to be built.

The last clause is the important one. A component that cannot fail is not a component under
test; it is a decoration, and decorations are exactly what the brief instructs this system not
to accumulate.
