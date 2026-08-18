# 09 — Risk Register

Status: **living document**  ·  Last reviewed: 2026-08-18

The four risk classes the brief asks about — overfitting, false discovery, implementation bugs,
and unrealistic backtests — plus operational risk. Each entry: the risk, why it is credible
*here*, the mitigation, and the residual.

Severity reflects **damage to the trustworthiness of conclusions**, not to money. This is a demo
system; the thing it can actually destroy is the credibility of its own answers.

---

## A. Overfitting risks

### OF-1 · Researcher degrees of freedom (severity: **critical**)
Every informal decision — which instruments, which date range, which timeframe, when to stop
looking — is an untracked trial. Human researchers reliably undercount their own trials by an
order of magnitude, and they do so sincerely.

*Mitigation:* the experiment registry counts every run automatically; `counted_as_trial` cannot
be set false without a committed reason; DSR is computed from the database, never from memory;
instrument panel and splits are pre-registered and frozen.

*Residual:* **high.** Decisions made *before* the first run — panel choice, timeframe, strategy
family — are not captured by any registry. Partially mitigated by committing the reasoning in
[`06`](06-baseline-strategy.md) §3 before testing, but this is genuinely unsolved and should be
treated as a known limitation of the whole programme rather than a solved problem.

### OF-2 · Parameter over-optimisation (severity: high)
Searching a 5-parameter grid finds a peak whether or not one exists.

*Mitigation:* one alpha-bearing parameter at baseline; worst-corner sensitivity (G5.6) rather
than average; plateau-width requirement (G5.7); shared parameters across instruments.

*Residual:* medium.

### OF-3 · Instrument cherry-picking (severity: high)
Reporting the 3 instruments that worked out of 6 tested.

*Mitigation:* panel frozen pre-registration; per-instrument results always reported for all six;
G4.9 deliberately does *not* require all instruments to be profitable — which removes the
incentive to drop losers.

*Residual:* low, provided the panel is never revised. Any revision is an ADR.

### OF-4 · Period cherry-picking (severity: high)
Choosing a start date that excludes an inconvenient period.

*Mitigation:* splits defined in `config/splits.yaml` before testing; changes require an ADR;
walk-forward exposes period dependence directly.

*Residual:* low.

### OF-5 · Holdout contamination (severity: **critical**)
Testing on the holdout, failing, adjusting, retesting. After three attempts the holdout is a
validation set and nobody involved quite noticed the transition.

*Mitigation:* harness-enforced unlock tokens; one unlock per hypothesis; append-only unlock log
committed to git; a modified hypothesis is a *new* hypothesis inheriting the parent's trial
count.

*Residual:* low — this is one of the few overfitting risks that can be mechanically prevented,
which is why it is worth the machinery.

### OF-6 · Complexity creep (severity: medium)
Each component individually justified; the whole unjustifiable.

*Mitigation:* R10 (every component traceable to evidence); quarterly complexity audit; delta
testing on the validated baseline; deferral list in [`04`](04-build-order.md).

*Residual:* medium. Requires ongoing discipline and cannot be automated.

### OF-7 · Regime/ensemble hypothesis multiplication (severity: high)
3 strategies × 4 regimes is 12 hypotheses against a sample too small for 3.

*Mitigation:* regime work gated behind R-301 preconditions; ≤3 regimes; every combination
counted as a trial; per-regime confidence intervals reported.

*Residual:* medium, and the honest expectation is that this line of work will not clear its bar.

---

## B. False-discovery risks

### FD-1 · Insufficient statistical power (severity: **critical**)
Per [`00`](00-consolidated-understanding.md) §5, 10 years cannot distinguish Sharpe 0.5 from
zero. Most results will be inconclusive, and inconclusive results are easily read as positive.

*Mitigation:* confidence intervals reported on every metric, never point estimates alone;
G4.2 threshold set at the detectability limit; panel breadth to accumulate evidence faster;
the framing throughout that "no detectable edge" is a valid deliverable.

*Residual:* **high, and irreducible.** This is a property of the available data, not a defect in
the design. The only honest response is to report it prominently rather than to work around it.

### FD-2 · Multiple testing without correction (severity: critical)
*Mitigation:* DSR from registry trial counts (G6.6).
*Residual:* low for counted trials; see OF-1 for the uncounted ones.

### FD-3 · Non-normal returns invalidating standard tests (severity: medium)
Trend returns are skewed and fat-tailed; the standard Sharpe SE understates uncertainty exactly
where these strategies live.

*Mitigation:* DSR incorporates skew and kurtosis; block bootstrap preserves autocorrelation
(i.i.d. resampling would overstate significance).

*Residual:* low.

### FD-4 · Survivorship in instrument selection (severity: medium)
Instruments available on today's broker are not a random sample of instruments that existed;
symbol lists change, and discontinued instruments are invisible.

*Mitigation:* documented as a known bias; panel restricted to major instruments with long
continuous histories, where the bias is smallest.

*Residual:* medium, and unavoidable with a single-broker data source.

### FD-5 · Confirmation bias in gate review (severity: medium)
A near-miss on a gate is easier to rationalise than to accept.

*Mitigation:* numeric criteria fixed in advance; harness evaluates pass/fail mechanically;
criteria changes require an ADR stating what was seen.

*Residual:* medium. Process helps; it does not eliminate the human factor.

---

## C. Implementation-bug risks

These are ordered by *probability of occurring and going unnoticed*, which is the combination
that matters. Several have been observed in the code contained in the source PDFs — see
[`10-mt5-platform-notes.md`](10-mt5-platform-notes.md).

### IB-1 · Look-ahead through bar 0 (severity: **critical**)
Using the forming bar's close makes a backtest use information from the future. It produces
spectacular results and is easy to miss.

*Mitigation:* invariant I2 — bar-0 access confined to `BarProvider` and linted; features carry
their source bar time; the §4 expectation table in [`06`](06-baseline-strategy.md) makes
"too good" a gate failure.

*Residual:* low.

### IB-2 · Silent `CopyBuffer` / `CopyRates` short reads (severity: **critical**)
These return fewer elements than requested during warm-up or after gaps. Unchecked, a naive
implementation reads `0.0`, and an ATR of zero produces either a division by zero or an enormous
position.

*Mitigation:* `Result<T>` return types; `FeatureVector.valid`; linter flags discarded results;
explicit short-history test fixtures.

*Residual:* low.

### IB-3 · Tick-value and currency-conversion errors (severity: high)
`SYMBOL_TRADE_TICK_VALUE` is in account currency and varies with the cross rate for instruments
whose profit currency differs. Caching it at init produces sizing that drifts wrong over months —
slowly enough that nobody notices.

*Mitigation:* tick value re-read per sizing call, never cached; cross-checked against
`OrderCalcProfit`; golden sizing table covering JPY pairs, gold and an index; `SelfTest` verifies
against live broker specs at every init.

*Residual:* low.

### IB-4 · Timezone and DST errors (severity: high)
Broker server time is not UTC and its offset shifts twice a year. Session logic written against
server time silently moves by an hour, and daily-limit resets land at the wrong time.

*Mitigation:* all internal reasoning in UTC; offset measured and recorded in the manifest;
`Clock` tested across DST boundaries in both hemispheres.

*Residual:* low.

### IB-5 · Netting vs hedging account semantics (severity: high)
On a netting account a second buy *adds to* an existing position rather than opening a new one,
which invalidates per-trade risk accounting entirely. Backtest and demo may differ in mode.

*Mitigation:* `ACCOUNT_MARGIN_MODE` detected at init, recorded in the manifest, and execution
behaviour made explicitly conditional on it. Mismatch between manifest and tester configuration
invalidates the run.

*Residual:* low.

### IB-6 · Duplicate orders across restart (severity: high)
*Mitigation:* idempotency journal written before submission; key derived from the decision bar;
`UNCERTAIN` state forces reconciliation; 100 simulated-restart test (G2.8).
*Residual:* low.

### IB-7 · MQL5 not compiled or tested in CI (severity: medium)
MetaEditor is Windows-only and its CLI is reported to fail quietly on large multi-file projects,
so the MQL5 half of the system has weaker automated enforcement than the Python half.

*Mitigation:* local pre-push gate (`tools/run_mql5_tests.*`) with compiler log and test summary
pasted into the pull request; the invariant linter runs in CI since it needs no compiler.

*Residual:* **medium — this is the weakest link in the engineering process** and is honestly
recorded as such. Revisit if a Windows runner becomes available.

### IB-8 · Indicator handle leaks (severity: low)
Handles created per call rather than per symbol exhaust terminal resources over a long run.

*Mitigation:* handles owned by `IndicatorHandles`, created at init, released at deinit; a
1,000-cycle leak test.

*Residual:* low.

### IB-9 · Journal schema drift (severity: medium)
A renamed column silently mis-parsed downstream yields confidently wrong analysis.

*Mitigation:* versioned schemas; ingest fails loudly on mismatch; round-trip tests.

*Residual:* low.

---

## D. Unrealistic-backtest risks

### UB-1 · Tester spread modelling not matching reality (severity: **critical**)
Non-real-tick modelling modes may use a fixed or synthetic spread. Real spreads widen exactly
when a breakout strategy trades — at session opens, on news, in fast markets — so the error is
*correlated with the strategy's activity* rather than random.

*Mitigation:* real-tick modelling wherever tick depth allows; spread distributions measured per
instrument by `ExportTickStats.mq5`; independent cost accounting inside the EA rather than
reliance on tester internals; cost tolerance measured against the *measured* distribution.

*Residual:* medium.

### UB-2 · Limited real-tick history depth (severity: high)
Brokers typically store real ticks for a few years, not fifteen — which collides directly with
wanting a long sample.

*Mitigation:* measure depth first (`ExportTickStats.mq5`); M1 modelling for the long history,
real ticks for the recent period, and an **overlap cross-check quantifying the difference**;
report the discrepancy rather than assuming it away.

*Residual:* medium, but *measured* rather than assumed, which is the material improvement.

### UB-3 · Zero slippage in the tester (severity: high)
The Strategy Tester does not simulate adverse slippage the way a real venue produces it.

*Mitigation:* explicit `SlippageModel` applied inside the EA's own cost accounting, asymmetric
by default; G6.8 requires the edge to survive doubled slippage; G7.5 compares realised demo
slippage against the model and revises it if wrong.

*Residual:* medium until demo data arrives, then low.

### UB-4 · Commission not configured in the tester (severity: medium)
Commission comes from broker symbol settings; for custom symbols it must be configured in the
tester's own commission settings and cannot be set programmatically at runtime.

*Mitigation:* the EA computes commission independently from `config/cost_assumptions.yaml` and
reports it separately, so results do not depend on tester configuration being correct;
`HistoryDealGetDouble(DEAL_COMMISSION)` is compared against the model to detect double-counting
or omission.

*Residual:* low.

### UB-5 · No requotes, rejections or partial fills in the tester (severity: medium)
The tester fills essentially everything; live execution does not.

*Mitigation:* execution state machine handles rejection and partial fill paths regardless, and
they are exercised by injected fault tests; G7.3/G7.7 compare live execution outcomes with
backtest assumptions.

*Residual:* medium — genuinely only resolvable by forward testing, which is why gate 7 exists.

### UB-6 · Swap and financing mis-modelling (severity: medium)
Swap rates change over time, are broker-specific, and triple-swap day conventions vary. Historic
swap rates are generally unavailable.

*Mitigation:* current swap rates recorded and applied as a *constant pessimistic* assumption
across history, with the assumption stated in the manifest; sensitivity to swap included in cost
perturbation. Multi-day holds make this material for the baseline, so it is not ignorable.

*Residual:* medium, and inherent — historic swap data does not exist to be modelled better.

### UB-7 · Backtest/live divergence from dual implementations (severity: critical **if it occurs**)
*Mitigation:* structurally prevented — strategy logic exists only in MQL5, and Python is never
permitted to generate a result (see [`01`](01-architecture.md) §1.1).
*Residual:* very low. This risk is designed out rather than managed.

---

## E. Operational risks

| ID | Risk | Mitigation | Residual |
|----|------|-----------|----------|
| OP-1 | Terminal/VPS downtime skews forward test | Uptime tracked; G7.2 requires ≥95%; gaps recorded | low |
| OP-2 | Broker changes specs or symbol names mid-test | Specs snapshotted per run; `SelfTest` detects drift at init | low |
| OP-3 | Demo server behaves unlike live (better fills, no rejections) | Documented limitation; no live claims are made from demo results | **inherent** |
| OP-4 | Loss of experiment database | SQLite committed or backed up; manifests are files in git | low |
| OP-5 | Headless orchestration unreliable across terminal builds | Semi-automated fallback preserves all provenance properties | low |

---

## F. The three risks worth re-reading

If attention is limited, these are the ones that determine whether the project's conclusions can
be believed:

1. **FD-1 — insufficient statistical power.** Irreducible, and it means most results will be
   inconclusive. Everything else is downstream of accepting this honestly.
2. **OF-1 — researcher degrees of freedom.** Partially mitigated by the registry, but decisions
   made before the first run escape it entirely. Genuinely unsolved.
3. **UB-1/UB-3 — spread and slippage realism.** Backtest execution assumptions are optimistic in
   a way that correlates with when the strategy trades. Only forward testing resolves it, which
   is precisely why gate 7 cannot be skipped or shortened.
