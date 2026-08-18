# 01 — System Architecture

Status: **accepted**  ·  Last reviewed: 2026-08-18

---

## 1. The governing decision: two tiers, one source of truth

MetaTrader 5 is an excellent *execution* environment and a poor *research* environment.

**What MT5 does well and nothing else can replace:** tick-level simulation against real
recorded ticks, correct broker constraint semantics (volume steps, stops levels, freeze
levels, margin), a real order lifecycle with real rejections, and a demo forward-testing
environment identical to the backtest environment.

**What MT5 does badly or not at all:** walk-forward orchestration, bootstrap and Monte Carlo
analysis, multiple-testing correction, parameter stability surfaces, experiment tracking,
statistical hypothesis testing, and anything requiring a matrix library or a plotting stack.

The architecture therefore splits along that seam:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  TIER B — Research Harness (Python, outside the terminal)               │
│                                                                          │
│   experiment registry · split custody · tester orchestration            │
│   journal ingestion · metrics · walk-forward · bootstrap / Monte Carlo  │
│   sensitivity grids · cost perturbation · deflated Sharpe · reporting   │
│                                                                          │
│   Drives the terminal via CLI + .ini.  Reads results from journals.     │
│   NEVER re-implements strategy logic.                                   │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ writes .ini / reads journals + reports
                             │ (process boundary — file-based, no shared state)
┌────────────────────────────┴────────────────────────────────────────────┐
│  TIER A — Trading System (MQL5, inside the terminal)                    │
│                                                                          │
│   THE ONLY PLACE STRATEGY LOGIC EXISTS.                                 │
│   Identical binary runs in Strategy Tester and on the demo account.     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.1 The invariant that makes this safe

> **Strategy logic exists in exactly one place: the MQL5 modules. Python never
> re-implements a signal, a feature, a sizing rule, or an exit.**

The most common way a research pipeline lies to its owner is by having two implementations of
the "same" strategy — a fast vectorised one used for research and a real one used for trading —
which quietly diverge. Every result then describes a system that was never traded.

Python's only computational role over strategy logic is **verification**: it produces
independent reference values for features (ATR, Donchian bounds, returns) which are committed
as golden vectors and asserted against by the MQL5 unit tests. That is an adversarial
cross-check, not a parallel implementation, and the two are never both allowed to generate
results.

Rationale and rejected alternatives: [`adr/ADR-0001-two-tier-research-architecture.md`](adr/ADR-0001-two-tier-research-architecture.md).

---

## 2. Tier A — the trading system

### 2.1 Layered pipeline

Data flows one way. Each layer may only call downward. No layer may reach around another.

```
                          ┌──────────────────────────┐
                          │  Config + Validation     │  parsed once at init;
                          │  (fail-closed)           │  invalid config = refuse to start
                          └────────────┬─────────────┘
                                       │  immutable after init
   ┌───────────────────────────────────┴───────────────────────────────────┐
   │                                                                        │
   │   ① MARKET DATA          SymbolCatalog · BarProvider · DataQuality     │
   │        │                 closed bars only · gap + staleness detection  │
   │        ▼                                                                │
   │   ② FEATURES             FeatureVector{ valid, bar_time, ... }          │
   │        │                 invalid ⇒ downstream must refuse to act        │
   │        ▼                                                                │
   │   ③ STRATEGY             IStrategy → Signal{ dir, stop, reason, ... }   │
   │        │                 pure: no I/O, no order calls, no globals       │
   │        ▼                                                                │
   │   ④ PORTFOLIO            OrderIntent — arbitration across strategies    │
   │        │                 (stage 0–5: pass-through, single strategy)     │
   │        ▼                                                                │
   │   ⑤ SIZING               PositionSizer → LotQuantiser                   │
   │        │                 reports achieved vs intended risk              │
   │        ▼                                                                │
   │   ⑥ RISK ENGINE  ◄──────  CapitalLedger, DrawdownGuard, CircuitBreaker  │
   │        │                 ***MANDATORY CHOKEPOINT***                     │
   │        │                 emits ApprovedOrder or RiskRejection           │
   │        ▼                                                                │
   │   ⑦ EXECUTION            OrderStateMachine · TradeGateway · Reconciler  │
   │        │                 the ONLY module that includes <Trade/Trade.mqh>│
   │        ▼                                                                │
   │   ⑧ BROKER (MT5)                                                        │
   └────────────────────────────────────────────────────────────────────────┘
                                       │
                     every layer emits ──┴──► ⑨ TELEMETRY
                                              TradeJournal · RejectJournal
                                              RunManifest · Logger
```

### 2.2 The three structural invariants

These are not style guidance. Each is mechanically checked by
`tools/lint_invariants.py`, which runs in CI and fails the build on violation.

**I1 — Risk supremacy.** `<Trade/Trade.mqh>` may be included by exactly one file:
`Include/SilverBarnacle/Execution/TradeGateway.mqh`. Any other inclusion fails the build.
A strategy therefore *cannot* place an order, even by mistake, even under time pressure,
even if a future contributor wants to.

**I2 — Causality.** Direct indexing of bar 0 (`rates[0]`, `iClose(...,0)`, `CopyBuffer(...,0,1,...)`
with a zero start shift) is forbidden outside `Data/BarProvider.mqh`, which encapsulates the
closed-bar rule in one auditable place. The linter flags bar-0 access elsewhere.

**I3 — Purity of strategies.** Files under `Strategy/Strategies/` may not include anything from
`Execution/`, `Risk/`, `Telemetry/`, or `Capital/`, and may not call `Print`, `FileWrite`,
`OrderSend`, or account functions. A strategy is a function from features to a signal. It has
no other capabilities, so it cannot develop them.

### 2.3 Decision timing

| Event | What runs | Why |
|-------|-----------|-----|
| **Bar close** (new bar detected) | Full pipeline ①→⑦ | Deterministic; identical in tester and live; no tick-delivery dependence |
| **Tick** | Execution management only: stop/freeze-level checks, trailing-stop maintenance, spread-guard, circuit-breaker evaluation | Must react faster than a bar, but takes no *signal* decisions |
| **Timer (1 s)** | Reconciliation, health checks, day/week rollover | Independent of market activity — still fires in a dead market, which is exactly when a stalled feed must be noticed |
| **`OnTradeTransaction`** | Order state machine transitions | The only trustworthy source of fill/rejection truth |

Rationale: [`adr/ADR-0002-bar-close-decisioning.md`](adr/ADR-0002-bar-close-decisioning.md).

### 2.4 State, persistence and restart

The system holds three kinds of state, treated differently:

| Kind | Example | Persistence | On restart |
|------|---------|-------------|------------|
| **Derived** | Feature values, indicator buffers | None | Recomputed from history after warm-up |
| **Authoritative-external** | Open positions, account equity | Broker-owned | Read from the terminal; never cached as truth |
| **Authoritative-internal** | Pending intents, capital ledger, daily loss accumulator, circuit-breaker state, high-water marks | `MQL5/Files/` JSON, written atomically (temp + rename) | Loaded, then **reconciled** against broker truth |

**Restart protocol.** On `OnInit`: load internal state → enumerate live positions carrying our
magic-number scheme → reconcile. Three outcomes:

- *Match* → resume normally.
- *Known position, unknown to journal* (e.g. crash between submit and journal write) → adopt it,
  log a `RECONCILE_ADOPT` event, and continue.
- *Any unresolvable mismatch* → **enter `HALTED_UNRECONCILED`**: manage and protect existing
  positions, open nothing new, raise an alert, require manual clearance.

The third branch implements R8. When the system cannot explain its own state, it stops. It does
not guess, and it does not blindly flatten either — an automatic mass-close on a reconciliation
bug is itself a way to lose money.

---

## 3. Tier B — the research harness

### 3.1 Responsibilities

```
research/silver_barnacle/
   registry/     ── experiment registry (SQLite + committed YAML pre-registrations)
                    assigns run IDs, records provenance, COUNTS TRIALS
   tester/       ── generates MT5 .ini files, drives metaeditor/terminal headlessly,
                    parses tester reports, collects optimisation frames
   ingest/       ── parses TradeJournal / RejectJournal / RunManifest into dataframes
   metrics/      ── Sharpe, Sortino, Calmar, PF, expectancy, tail stats,
                    concentration, deflated Sharpe
   validation/   ── split custody, walk-forward, sensitivity grids,
                    bootstrap / Monte Carlo, cost perturbation
   golden/       ── independent reference feature implementations (verification only)
   report/       ── gate reports, per-stage artefacts
```

### 3.2 How Python drives the terminal

MetaTrader 5 supports headless invocation via a configuration file, and MetaEditor supports
command-line compilation:

```bash
# Compile (Windows / Wine)
metaeditor64.exe /compile:"...\Experts\SilverBarnacle\SilverBarnacle.mq5" \
                 /inc:"...\MQL5" /log:"build.log"

# Run a tester pass from a generated .ini
terminal64.exe /config:"...\run_0f3a91.ini"
```

The harness generates one `.ini` per run from the registry entry, so the parameters that were
*recorded* and the parameters that were *executed* are the same object. There is no path by
which a run's manifest can disagree with what ran.

> **Verify on the target machine before relying on it.** Command-line switches and headless
> behaviour vary across terminal builds, and MetaEditor's CLI is known to be quiet about some
> failure modes on large multi-file projects. Stage 3's first task is to confirm this loop
> end-to-end and pin the terminal build in the run manifest. If headless orchestration proves
> unreliable, the fallback is a semi-automated loop (harness writes `.ini` and parameter sets,
> operator triggers runs, harness ingests results) — slower, but it preserves every provenance
> property that matters. Nothing downstream depends on full automation.

### 3.3 The experiment registry

The registry is the anti-overfitting mechanism with the most leverage in the entire system,
because it makes the trial count **automatic and un-fudgeable**.

Every run — successful, failed, abandoned, or "just a quick look" — is assigned an ID and
recorded. The registry stores:

```yaml
run_id:            r_20260818_0f3a91
hypothesis_id:     H-001                  # links to a committed pre-registration
git_commit:        <sha>                  # compile-time stamped, matched against binary
terminal_build:    <build>
parameters:        {donchian_n: 50, atr_k: 3.0, risk_pct: 0.5}
parameter_hash:    sha256:...
instruments:       [EURUSD, GBPUSD, USDJPY, AUDUSD, XAUUSD, US500]
split:             is_2008_2018           # named, from config/splits.yaml
date_range:        [2008-01-01, 2018-12-31]
cost_model:        cm_v2_pessimistic
modelling_mode:    real_ticks | m1_ohlc
seed:              20260818
purpose:           "baseline IS calibration"   # free text, REQUIRED
results_digest:    sha256:...
counted_as_trial:  true
```

`counted_as_trial` defaults to `true` and **the harness refuses to set it false without a
reason string that is committed to git**. Exploratory runs on the training split still count.
This is deliberately awkward: the friction is the point, because the cost of undercounting
trials is a false discovery that survives every later gate.

Deflated Sharpe Ratio is computed from `SELECT COUNT(*) FROM runs WHERE hypothesis_id = ? AND
counted_as_trial`. Nobody estimates the trial count from memory.

### 3.4 Split custody

`config/splits.yaml` defines every split by name and date range. It is version-controlled, and
changing it requires an ADR — because silently moving a boundary after seeing results is the
single most effective way to fake a validated strategy.

The **final holdout** is additionally protected: the harness refuses to run against it unless
an unlock token file exists naming the hypothesis and the gate. Unlocking is logged to an
append-only file committed to git. Any hypothesis whose holdout has been unlocked cannot be
re-tested on it — a second unlock for the same hypothesis is refused outright.

---

## 4. Cross-cutting design decisions

### 4.1 Error handling: `Result<T>` rather than sentinel values

MQL5 has no exceptions. Silent sentinel returns (`0.0`, `-1`, `false`) are how trading systems
end up acting on a zero ATR or a missing price.

Every fallible operation returns a small result struct carrying success, a typed error code, and
a context string. Callers must inspect it. The linter flags discarded results on the fallible
call list.

```mql5
struct DoubleResult {
   bool     ok;
   double   value;
   int      error;        // ENUM_SB_ERROR
   string   context;
};
```

The specific failure this prevents: `CopyBuffer` returning fewer elements than requested during
indicator warm-up, which a naive implementation reads as a valid `0.0` and sizes a position from.

### 4.2 Configuration: centralised, validated, immutable

All tunables are `input` variables in one place, copied at `OnInit` into an immutable config
struct, and validated before anything else initialises. Validation is **fail-closed**: a config
that does not validate refuses to start the EA, in tester and live alike. No magic numbers
outside `Config/`.

Validation checks ranges, cross-parameter consistency (`donchian_exit_n < donchian_entry_n`),
environment compatibility (demo mode, hedging vs netting, symbol availability, market open),
and that every instrument in the panel actually exists with sane specifications.

### 4.3 Time

Broker server time is not UTC and its offset changes with daylight saving. Session filters
written against server time silently shift by an hour twice a year, which is exactly the kind
of bug that produces a plausible-looking but wrong backtest.

All internal reasoning is in **UTC**. Server time is converted once, at the boundary, using a
measured offset that is recorded in the run manifest. Session definitions are expressed in UTC.

### 4.4 Determinism and seeding

`MathSrand` is called once at init with the configured seed, which is recorded. Any stochastic
component (execution jitter simulation, tie-breaking) draws from that stream. Two runs with the
same manifest produce byte-identical journals; the harness asserts this as a regression test.

### 4.5 Magic numbers and attribution

A structured magic number encodes strategy identity and instance so positions can be attributed
after a restart without external state:

```
magic = BASE_MAGIC + (strategy_id * 1000) + instance_id
```

`BASE_MAGIC` is configured per deployment so multiple experiments can share a terminal without
colliding. Positions carrying a foreign magic are ignored entirely — never modified, never
counted, never closed.

---

## 5. What is intentionally *not* in this architecture yet

Placeholders exist as interfaces only, with pass-through implementations, so that adding them
later is a substitution rather than a re-architecture — and so that the absence is visible in
the code rather than hidden:

| Layer | Stage 0–5 implementation | Becomes real when |
|-------|--------------------------|-------------------|
| Portfolio arbitration | Pass-through (single strategy) | A second strategy clears its gates |
| Correlation management | Static instrument-group caps from config | Measured correlation demonstrably improves OOS results |
| Regime detection | Absent — not even an interface | A regime hypothesis clears pre-registration |
| Ensemble / scoring | Absent | ≥2 validated strategies plus a portfolio layer |
| ML inference | Absent | Preconditions in the roadmap are met |

Building the interface but not the implementation is a deliberate middle path: it keeps the
seams visible without inviting speculative complexity behind them. Where even the interface
would be speculation — regime detection, ensembles — nothing is built at all, because an unused
abstraction designed before its use case is usually the wrong abstraction.
