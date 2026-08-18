# 02 — Repository and File Structure

Status: **accepted**  ·  Last reviewed: 2026-08-18

---

## 1. Top level

```
silver-barnacle/
├── README.md
├── docs/                     # architecture, decisions, gate reports  (this directory)
├── mql5/                     # Tier A — everything that runs inside MetaTrader 5
├── research/                 # Tier B — Python research harness
├── config/                   # shared configuration: instruments, costs, splits, presets
├── experiments/              # pre-registrations and gate evidence (committed)
├── tools/                    # build, deploy, lint, codegen
└── .github/workflows/        # CI
```

`mql5/` mirrors the MetaTrader data-folder layout exactly, so `tools/deploy_to_terminal.*`
is a symlink (or copy) with no path rewriting. The repository is the source of truth; the
terminal directory is a deployment target and is never edited directly.

---

## 2. `mql5/` — the trading system

```
mql5/
├── Experts/SilverBarnacle/
│   └── SilverBarnacle.mq5              # composition root ONLY: wire modules, no logic
│
├── Include/SilverBarnacle/
│   ├── Core/
│   │   ├── Types.mqh                   # shared structs: Signal, OrderIntent, ...
│   │   ├── Enums.mqh                   # ENUM_SB_ERROR, reject reasons, states
│   │   ├── Result.mqh                  # DoubleResult / BoolResult / IntResult
│   │   ├── Clock.mqh                   # server-time → UTC, session arithmetic
│   │   ├── Json.mqh                    # minimal writer for journals + state
│   │   └── Version.mqh                 # GENERATED: git SHA, build stamp (never edited)
│   │
│   ├── Config/
│   │   ├── Config.mqh                  # immutable config struct
│   │   ├── Inputs.mqh                  # every `input` declaration, one place
│   │   ├── ConfigValidator.mqh         # fail-closed validation
│   │   └── Presets.mqh                 # conservative / balanced / aggressive bundles
│   │
│   ├── Data/
│   │   ├── SymbolCatalog.mqh           # broker specs; validated once, cached
│   │   ├── BarProvider.mqh             # ONLY module permitted bar-0 access (invariant I2)
│   │   └── DataQuality.mqh             # gaps, staleness, frozen feed, absurd prices
│   │
│   ├── Features/
│   │   ├── FeatureVector.mqh           # carries `valid` + `bars_available`
│   │   ├── IndicatorHandles.mqh        # handle lifecycle; leak-free release
│   │   ├── Atr.mqh
│   │   ├── Donchian.mqh
│   │   └── Returns.mqh
│   │
│   ├── Strategy/
│   │   ├── IStrategy.mqh               # the strategy contract
│   │   ├── StrategyManifest.mqh        # self-description (see 03 §Strategy)
│   │   ├── StrategyRegistry.mqh        # id → instance
│   │   └── Strategies/
│   │       └── TrendBreakout.mqh       # the baseline (see 06)
│   │
│   ├── Portfolio/
│   │   ├── PortfolioState.mqh          # aggregate exposure view
│   │   ├── ExposureModel.mqh           # instrument → risk-factor mapping
│   │   └── Allocator.mqh               # STAGE 0–5: pass-through
│   │
│   ├── Risk/
│   │   ├── RiskEngine.mqh              # the mandatory chokepoint
│   │   ├── RiskLimits.mqh              # limit definitions + evaluation
│   │   ├── PositionSizer.mqh           # risk → notional
│   │   ├── LotQuantiser.mqh            # notional → broker-legal volume
│   │   ├── DrawdownGuard.mqh           # daily / weekly / peak-to-trough
│   │   └── CircuitBreaker.mqh          # spread, price-jump, exec-error, data-quality
│   │
│   ├── Costs/
│   │   ├── CostModel.mqh               # spread + commission + slippage + swap estimate
│   │   └── SlippageModel.mqh           # pessimistic, configurable, seeded
│   │
│   ├── Execution/
│   │   ├── ExecutionEngine.mqh         # orchestrates the state machine
│   │   ├── OrderStateMachine.mqh       # explicit states + legal transitions
│   │   ├── TradeGateway.mqh            # ★ ONLY file including <Trade/Trade.mqh>
│   │   ├── IdempotencyJournal.mqh      # duplicate-order prevention across restarts
│   │   └── Reconciler.mqh              # startup + periodic broker-truth reconciliation
│   │
│   ├── Capital/
│   │   └── CapitalLedger.mqh           # paper 80/20 accounting; sizing basis
│   │
│   ├── Telemetry/
│   │   ├── Logger.mqh                  # levelled, structured
│   │   ├── TradeJournal.mqh            # one row per executed trade, ~40 fields
│   │   ├── RejectJournal.mqh           # one row per REJECTED intent
│   │   ├── RunManifest.mqh             # provenance written at init
│   │   └── MetricsCollector.mqh        # OnTester custom criterion + FrameAdd
│   │
│   └── Diagnostics/
│       ├── Assert.mqh                  # SB_ASSERT — halts, never continues silently
│       ├── HealthCheck.mqh             # periodic self-inspection
│       └── SelfTest.mqh                # init-time sanity checks against broker specs
│
├── Scripts/SilverBarnacle/
│   ├── RunUnitTests.mq5                # executes the whole MQL5 test suite
│   ├── ExportSymbolSpecs.mq5           # dump broker specs → CSV (feeds config + harness)
│   └── ExportTickStats.mq5             # measure real-tick depth + spread distributions
│
└── Tests/
    ├── TestFramework.mqh               # assertions, fixtures, reporting
    ├── test_lot_quantiser.mqh
    ├── test_position_sizer.mqh
    ├── test_risk_limits.mqh
    ├── test_capital_ledger.mqh
    ├── test_cost_model.mqh
    ├── test_donchian.mqh
    ├── test_atr.mqh
    ├── test_clock.mqh
    ├── test_order_state_machine.mqh
    └── golden/                          # CSV reference vectors from research/golden/
        ├── atr_eurusd_d1.csv
        └── donchian_eurusd_d1.csv
```

### Why the composition root is empty of logic

`SilverBarnacle.mq5` contains `OnInit`, `OnTick`, `OnTimer`, `OnTradeTransaction`, `OnDeinit`,
`OnTester` — and nothing else but wiring. Every event handler is a handful of lines delegating
to a module. This is what makes the modules independently testable: none of them depends on
being inside an EA, so `RunUnitTests.mq5` can exercise them directly.

The failure mode this avoids is the one every source document's pseudocode demonstrates — an
`OnTick` that computes indicators, checks risk, and sends orders inline. That code cannot be
unit tested at all.

---

## 3. `research/` — the harness

```
research/
├── pyproject.toml
├── silver_barnacle/
│   ├── cli.py                  # `sb run`, `sb gate`, `sb report`, `sb registry`
│   ├── registry/
│   │   ├── db.py               # SQLite schema, run IDs, trial counting
│   │   ├── prereg.py           # pre-registration parse + validation
│   │   └── manifest.py         # provenance capture and verification
│   ├── tester/
│   │   ├── ini.py              # .ini generation from a registry entry
│   │   ├── driver.py           # headless terminal invocation, timeout, retry
│   │   ├── frames.py           # optimisation frame collection
│   │   └── report.py           # tester HTML/XML report parsing
│   ├── ingest/
│   │   ├── trades.py           # TradeJournal → DataFrame
│   │   ├── rejects.py          # RejectJournal → DataFrame
│   │   └── schema.py           # versioned journal schemas; fail on mismatch
│   ├── metrics/
│   │   ├── returns.py          # equity → return series, correct compounding
│   │   ├── ratios.py           # Sharpe, Sortino, Calmar, PF, expectancy
│   │   ├── drawdown.py         # depth, duration, recovery, Ulcer
│   │   ├── concentration.py    # top-N dependency, Gini, tail contribution
│   │   └── deflated.py         # Deflated Sharpe Ratio, PSR
│   ├── validation/
│   │   ├── splits.py           # split custody + holdout unlock enforcement
│   │   ├── walkforward.py      # rolling optimise → test orchestration
│   │   ├── sensitivity.py      # parameter grids, plateau detection
│   │   ├── bootstrap.py        # block bootstrap, trade-order randomisation
│   │   ├── montecarlo.py       # path simulation, ruin probability
│   │   └── costs.py            # cost perturbation; breakeven-cost solver
│   ├── golden/
│   │   ├── indicators.py       # independent ATR / Donchian reference impls
│   │   └── export.py           # → mql5/Tests/golden/*.csv
│   └── report/
│       ├── gate.py             # gate pass/fail evaluation against 08
│       └── render.py           # HTML/Markdown artefacts
├── tests/                      # pytest — the harness needs its own tests
└── notebooks/                  # exploration ONLY; never a source of a reported result
```

**On `notebooks/`:** exploratory notebooks are permitted and useful, but no number from a
notebook may appear in a gate report. Anything that matters is promoted into
`silver_barnacle/` with a test. Notebooks are where hypotheses are *formed*, never where they
are *confirmed* — a notebook has no provenance, no trial count, and no reproducibility
guarantee.

---

## 4. `config/`

```
config/
├── instruments.yaml          # the panel: symbols, groups, risk-factor tags, session hours
├── cost_assumptions.yaml     # per-instrument spread/commission/slippage/swap; versioned
├── splits.yaml               # ★ named data splits — changing this requires an ADR
├── limits.yaml               # risk limit values per preset
└── presets/
    ├── conservative.yaml
    ├── balanced.yaml
    └── aggressive.yaml
```

`cost_assumptions.yaml` carries a version tag (`cm_v2_pessimistic`) recorded in every run
manifest, so a result can always be re-read against the cost assumptions that produced it.

`instruments.yaml` tags each symbol with **risk factors**, not just an asset class — this is
what lets the exposure model recognise that long EURUSD and short USDCHF are substantially the
same USD bet:

```yaml
- symbol: EURUSD
  group: fx_major
  factors: {usd: -1.0, eur: +1.0}
- symbol: XAUUSD
  group: metal
  factors: {usd: -1.0, gold: +1.0}
```

---

## 5. `experiments/`

```
experiments/
├── registered/
│   ├── H-001-trend-breakout-panel.yaml     # written and COMMITTED before the run
│   └── ...
├── runs/                                    # generated: manifests + result digests
└── gates/
    ├── G3-baseline-in-sample.md             # gate evidence, committed
    └── ...
```

A pre-registration is committed **before** the corresponding run executes. The registry
verifies that the pre-registration's git blob predates the run. This is the mechanism that
makes "we predicted this in advance" checkable rather than asserted.

---

## 6. `tools/`

```
tools/
├── deploy_to_terminal.sh / .ps1     # symlink mql5/ into the terminal data folder
├── gen_version_header.py            # git SHA + build stamp → Core/Version.mqh
├── compile.sh / .ps1                # metaeditor64 CLI; parses the log; nonzero on error
├── lint_invariants.py               # enforces I1/I2/I3 from 01 §2.2
└── run_mql5_tests.sh / .ps1         # deploy → compile → run RunUnitTests → parse output
```

`gen_version_header.py` writes the git SHA into `Core/Version.mqh` at build time, so a compiled
binary can state which commit produced it and the harness can refuse to record a run whose
binary does not match the working tree.

---

## 7. CI, and an honest limitation

`.github/workflows/ci.yml` runs on Linux and covers:

- `pytest` over `research/`
- `tools/lint_invariants.py` (pure text analysis — no compiler needed)
- documentation link checking
- config schema validation

**MQL5 compilation and the MQL5 unit tests do not run in CI.** MetaEditor is Windows-only;
compiling in CI would require a Windows runner with MetaTrader installed, and MetaEditor's CLI
is reported to fail quietly on large multi-file projects, which makes it a poor gate.

The compensating control is a **local pre-push gate**: `tools/run_mql5_tests.*` performs
deploy → compile → unit-test → parse, and must pass before a push. Its output (compiler log
plus test summary) is pasted into the pull request. This is weaker than CI enforcement and is
recorded as such in [`09-risk-register.md`](09-risk-register.md) (risk IB-7).

Revisiting this once a Windows runner is available is a tracked improvement, not a closed
question.
