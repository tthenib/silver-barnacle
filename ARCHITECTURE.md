# ARCHITECTURE.md — System Design

**Status:** Design approved for V1 scaffolding. No strategy code written yet.
**Last updated:** 2026-08-26
**Companion documents:** [RESEARCH.md](RESEARCH.md) · [STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) · [RISK_MANAGEMENT.md](RISK_MANAGEMENT.md)

---

## 1. Design principles

These are binding constraints, not aspirations. Each exists because a specific, common failure
mode is being designed out.

| # | Principle | Failure mode it prevents |
|---|---|---|
| 1 | **Research is the source of truth; MQL5 is a port.** Signal logic is specified and validated in Python. The EA reproduces it. | The classic failure: the EA quietly does something different from the research, and nobody notices until live money is lost |
| 2 | **Every module is replaceable and separately testable.** No module reaches around another. | Spaghetti coupling that makes it impossible to attribute a result to a change |
| 3 | **Closed bars only.** Signals are computed from bar `t−1` and earlier, acted on at bar `t` open. | Look-ahead bias. This is enforced structurally, not by discipline (§6.1) |
| 4 | **The system must be able to say NO TRADE**, and flat must be a first-class state. | Overtrading; the assumption that capital must always be deployed |
| 5 | **Risk vetoes signal. Always.** The risk engine can reduce or reject any order; it can never increase one. | Signal logic finding ways to talk itself into more exposure |
| 6 | **No component may assume data the platform does not provide.** Unavailable data is a stub that returns "unavailable", never a simulated value. | Silently backtesting on data that will not exist in production |
| 7 | **Complexity must be earned by out-of-sample evidence**, one component at a time. | Building the ensemble before the baseline works |
| 8 | **Every decision is logged with its inputs.** A trade that cannot be explained from the log is a bug. | Unfalsifiable live behaviour |

---

## 2. Repository layout

```
/                              ← the seven charter documents live at root
  RESEARCH.md  ARCHITECTURE.md  STRATEGY_HYPOTHESES.md
  RISK_MANAGEMENT.md  BACKTESTING_PROTOCOL.md  EXPERIMENT_LOG.md  ROADMAP.md

/src
  /python                      ← production-grade shared library (NOT experiments)
    /core                      ← types, clock, bar/series primitives, config loading
    /indicators                ← pure functions: ATR, MA, realised vol, percentile
    /signals                   ← signal generators (trend ensemble, breakout, ...)
    /regime                    ← volatility state, abnormality detector
    /risk                      ← position sizing, exposure caps, circuit breakers
    /portfolio                 ← multi-symbol exposure aggregation
    /execution                 ← order intent model + simulated broker
    /analytics                 ← metrics, DSR/PSR, drawdown analysis, tearsheets
    /logging                   ← structured event log schema shared with MQL5
    /configuration             ← config schema + validation
  /mql5
    /Experts                   ← the EA entry point (thin: wiring only)
    /Include/CryptoEA          ← the ported module implementations
      Core/  Signals/  Regime/  Risk/  Execution/  Logging/  Config/
/research                      ← EXPERIMENTS. Disposable. Never imported by /src
  /analysis                    ← standalone analyses (e.g. return_target_feasibility.py)
  /notebooks                   ← exploratory work
  /config                      ← experiment configs, one file per experiment ID
/tests                         ← unit + property + parity tests for /src
/data                          ← immutable raw data + manifest (gitignored except manifest)
/results                       ← generated experiment outputs, committed
/docs                          ← supporting reference material
```

**The `/research` → `/src` rule.** Research code may import from `/src`. `/src` may **never**
import from `/research`. A finding is promoted by *rewriting* it into `/src` with tests, not by
moving the file. This is the boundary that keeps experimental logic out of production.

---

## 3. Pipeline

```
                    ┌─────────────────────────────────────────┐
                    │  DATA LAYER                             │
                    │  exchange OHLCV (research)              │
                    │  broker bars (production)               │
                    │  external data provider  [STUB]         │
                    └────────────────┬────────────────────────┘
                                     │  Bar(t-1) and history only
                    ┌────────────────▼────────────────────────┐
                    │  FEATURE ENGINE                         │
                    │  returns · realised vol · ATR           │
                    │  vol percentile · MA distances          │
                    └────────────────┬────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
    ┌─────────▼─────────┐  ┌─────────▼─────────┐  ┌─────────▼─────────┐
    │ REGIME DETECTOR   │  │ STRATEGY ENGINES  │  │ MARKET CONTEXT    │
    │ vol state (cont.) │  │ A: trend ensemble │  │ spread, session   │
    │ abnormality (bin) │  │ B: breakout  [V2] │  │ symbol specs      │
    └─────────┬─────────┘  │ C: mean rev  [✗]  │  └─────────┬─────────┘
              │            └─────────┬─────────┘            │
              │                      │                      │
              │            ┌─────────▼─────────┐            │
              │            │ SIGNAL ENSEMBLE   │            │
              │            │ score ∈ [-1, +1]  │            │
              │            │ or NO_TRADE       │            │
              │            └─────────┬─────────┘            │
              └──────────────────────┼──────────────────────┘
                                     │
                    ┌────────────────▼────────────────────────┐
                    │  TRADE FILTERS (veto only)              │
                    │  spread gate · abnormality gate         │
                    │  min-hold · duplicate guard             │
                    └────────────────┬────────────────────────┘
                    ┌────────────────▼────────────────────────┐
                    │  POSITION SIZING                        │
                    │  target_risk / (vol_forecast × price)   │
                    │  → broker-legal lot size                │
                    └────────────────┬────────────────────────┘
                    ┌────────────────▼────────────────────────┐
                    │  RISK ENGINE (hard veto, can only cut)  │
                    │  per-trade · daily · weekly · peak DD   │
                    │  gross exposure · correlated exposure   │
                    │  kill switch                            │
                    └────────────────┬────────────────────────┘
                    ┌────────────────▼────────────────────────┐
                    │  EXECUTION ENGINE                       │
                    │  order intent → broker order            │
                    │  retries · error mapping · reconcile    │
                    └────────────────┬────────────────────────┘
                    ┌────────────────▼────────────────────────┐
                    │  POSITION MANAGEMENT                    │
                    │  stop maintenance · exit on reversal    │
                    │  state persistence · restart recovery   │
                    └────────────────┬────────────────────────┘
                    ┌────────────────▼────────────────────────┐
                    │  MONITORING / LOGGING (structured)      │
                    └─────────────────────────────────────────┘
```

Data flows **one way**. The risk engine is the only module with veto power, and it exercises it
after sizing so that every rejection is attributable to a named limit.

---

## 4. Module contracts

Interfaces are given in Python (the specification) with the MQL5 counterpart noted. Both
implementations must satisfy the same parity tests (§6.2).

### 4.1 `FeatureEngine`

```python
@dataclass(frozen=True)
class FeatureSet:
    timestamp: datetime          # bar close time, UTC, of the LAST CLOSED bar
    close: float
    atr: float                   # Wilder ATR, in price units
    realised_vol: float          # annualised, from log returns
    vol_percentile: float        # [0,1] rank of realised_vol in its trailing window
    ma_distances: dict[int, float]   # lookback -> (close/MA - 1)
    breakout_state: dict[int, int]   # lookback -> {-1,0,+1}

class FeatureEngine(Protocol):
    def compute(self, bars: BarSeries) -> FeatureSet | None:
        """Return features from CLOSED bars only. None if insufficient history."""
```

**Contract:** `compute` must be a pure function of `bars[:-0]` where the final element is the
last *closed* bar. It must never read the forming bar. Returns `None` rather than partial
features — a half-warmed indicator is a silent bias source.

### 4.2 `SignalEngine`

```python
class Direction(IntEnum):
    SHORT = -1
    FLAT  =  0
    LONG  =  1

@dataclass(frozen=True)
class Signal:
    direction: Direction
    score: float                 # [-1.0, +1.0]; |score| is conviction, not size
    components: dict[str, float] # per-lookback contributions, for logging/attribution
    reason: str                  # human-readable, appears in the log

class SignalEngine(Protocol):
    def evaluate(self, features: FeatureSet) -> Signal:
        """Pure. No I/O, no order state, no account state."""
```

**Contract:** the signal engine knows nothing about account equity, open positions, or risk
limits. It answers only "what does the market look like." `score` conveys conviction; the
mapping from conviction to size is the sizing module's job, and V1 deliberately uses a
**binary** mapping (see [STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §5) until
conviction-scaling is shown to help out of sample.

### 4.3 `RegimeDetector`

```python
@dataclass(frozen=True)
class RegimeState:
    vol_scalar: float            # continuous multiplier in [vol_floor, 1.0]
    is_abnormal: bool            # circuit breaker: block NEW entries
    label: str                   # descriptive only; MUST NOT drive V1 logic
```

**Contract for V1:** `vol_scalar` is continuous (no thresholds to overfit) and `is_abnormal` is
the *only* binary output. `label` exists for logging and future analysis and is explicitly
forbidden from influencing V1 behaviour. Directional regime classification is a V2 experiment
(see [RESEARCH.md](RESEARCH.md) §3.6 for why nine discrete regimes is an overfitting machine).

### 4.4 `PositionSizer`

```python
@dataclass(frozen=True)
class SizingRequest:
    signal: Signal
    features: FeatureSet
    regime: RegimeState
    account: AccountState
    symbol: SymbolSpec

@dataclass(frozen=True)
class SizingResult:
    lots: float                  # already rounded to broker lot step
    risk_fraction: float         # fraction of equity at risk if stop is hit exactly
    notional: float
    stop_price: float
    rationale: dict[str, float]  # every input to the calculation, for the log
```

**Contract:** all broker constraints (`min_lot`, `lot_step`, `max_lot`, `contract_size`,
`tick_value`, `stops_level`, `freeze_level`) are applied **inside** the sizer, and
`tick_value` is queried from the symbol at runtime, never hardcoded. If rounding to a legal lot
would exceed the risk budget, the sizer rounds **down**, and returns `lots = 0` if the minimum
legal lot already breaches the budget. Returning zero is a correct and expected outcome on a
small account — it must not be treated as an error.

### 4.5 `RiskEngine`

```python
class RiskDecision(IntEnum):
    ALLOW = 0
    REDUCE = 1
    REJECT = 2

@dataclass(frozen=True)
class RiskVerdict:
    decision: RiskDecision
    approved_lots: float         # <= requested lots, ALWAYS
    binding_limit: str | None    # which named limit bound, for the log
```

**Contract — the load-bearing invariant of the whole system:**

```
approved_lots <= requested_lots,  for every input, always.
```

This is enforced by a property-based test that fuzzes account state, symbol specs, and sizing
requests. The risk engine can *only* subtract. It is stateful (it tracks daily/weekly P&L and
the equity high-water mark) and that state is persisted (§5.3).

### 4.6 `IExternalDataProvider` — **stub, deliberately unimplemented**

```python
class IExternalDataProvider(Protocol):
    def funding_rate(self, symbol: str, at: datetime) -> float | None: ...
    def open_interest(self, symbol: str, at: datetime) -> float | None: ...
    def btc_dominance(self, at: datetime) -> float | None: ...
    def spot_basis(self, symbol: str, at: datetime) -> float | None: ...
```

**Every method returns `None` in V1, and every caller must handle `None` by degrading, not by
substituting a default.** A test asserts that the system's behaviour is identical with the stub
provider and with no provider at all. This keeps the seam honest: when we later have exchange
data, the interface is ready; until then, nothing can quietly depend on data we do not have.

### 4.7 `ExecutionEngine`

Responsibilities: translate an approved order intent into broker orders; classify and handle
broker errors; reconcile intended state against actual broker state on every cycle and after
restart.

**Contract:** the execution engine is the *only* module that talks to the broker, and it is
**idempotent by design** — every order carries a deterministic client-side identity derived
from `(magic_number, symbol, signal_bar_timestamp)`. Before sending, it checks whether that
identity already exists as a position or pending order. This is what prevents the duplicate-order
failure mode after a restart, a requote, or an ambiguous timeout.

Error handling is table-driven, not ad hoc:

| Broker condition | Handling |
|---|---|
| Requote / price changed | Re-validate signal is still current, retry ≤ N with fresh price |
| Invalid stops / below `stops_level` | Widen stop to the legal minimum; **if that breaches the risk budget, cancel the trade** — never silently accept more risk |
| Not enough money | Reduce to affordable size if still within risk budget, else reject and log |
| Market closed / trade disabled | Skip cycle, log, no retry |
| Timeout / no connection | **Do not resend.** Reconcile on next cycle via the idempotency key |
| Partial fill | Accept, record actual filled volume, recompute stop on actual size |

---

## 5. Cross-cutting concerns

### 5.1 Time

The single most underrated source of research-to-production divergence.

- Research data is timestamped **UTC**, bar-close convention.
- MT5 bars are timestamped in **broker server time**, which is broker-specific and may observe DST.
- A "daily bar" therefore covers a different 24 hours in research than in production.

**Rule:** the EA records its server-time offset at init and logs it. A named V1 experiment
(EXP-0003) measures how much the signal changes under different daily-bar cut times. If the
strategy is sensitive to the cut time, that is *itself* evidence of overfitting — a real edge at
a multi-week horizon should not care whether the day ends at 00:00 or 22:00 UTC.

### 5.2 Configuration

One typed, validated config object per experiment, serialised to `/research/config/<EXP-ID>.yaml`
and hashed. The hash appears in the results file and in the experiment log. The EA's `input`
parameters are generated from the same schema so that a research config and an EA parameter set
cannot drift apart silently.

### 5.3 State persistence and restart recovery

The EA must survive a terminal restart mid-position without duplicating or orphaning trades.

Persisted (to file, written atomically): equity high-water mark, daily/weekly P&L anchors and
their reset timestamps, kill-switch state and reason, last processed bar timestamp per symbol.

**Recovery sequence on `OnInit`:**
1. Load persisted state; if absent or corrupt, enter **safe mode** — manage existing positions,
   open nothing new, log loudly.
2. Enumerate live positions and orders carrying our magic number.
3. Reconcile against persisted intent. Any position we did not intend, or any intent without a
   position, is logged as a `RECONCILIATION_MISMATCH` and the EA enters safe mode.
4. Re-derive the high-water mark from account history if persisted state is missing.

**Safe mode is never exited automatically.** It requires human acknowledgement. Auto-recovery
from an unexplained state is how an EA turns a small problem into an account.

### 5.4 Logging

Structured, one JSON object per event, same schema in Python and MQL5 so that backtest logs and
live logs are analysed by identical tooling.

```json
{"ts":"2026-08-26T00:00:00Z","ev":"SIGNAL","sym":"BTCUSD","dir":1,"score":0.62,
 "components":{"ma_20":1,"ma_40":1,"ma_60":1,"ma_90":0,"ma_120":1,"ma_160":0,"ma_200":1},
 "atr":1834.2,"rvol":0.47,"cfg":"a91c4f"}
```

Mandatory events: `SIGNAL`, `REGIME`, `SIZE`, `RISK_VERDICT`, `ORDER_INTENT`, `ORDER_RESULT`,
`FILL`, `EXIT`, `KILL_SWITCH`, `RECONCILIATION_MISMATCH`, `SAFE_MODE`, `HEARTBEAT`.

**Rule:** every trade in the live log must be reconstructable end-to-end — signal → size →
risk verdict → order → fill. If it cannot be reconstructed, that is a defect with the same
priority as a losing bug.

---

## 6. The two controls that make this architecture worth having

### 6.1 Structural look-ahead prevention

Discipline does not prevent look-ahead bias; structure does.

- The backtest harness passes each module a `BarSeries` **view truncated at the last closed
  bar**. Future bars are not merely unused — they are not present in the object.
- A test constructs a series, computes a signal, then mutates all future bars to extreme values
  and recomputes. **The signal must be bit-identical.** Any leak fails this test immediately.
- Orders execute at the *open of the following bar* plus modelled cost, never at the signal
  bar's close.
- The same test runs against the MQL5 port via the parity harness.

### 6.2 The Python ↔ MQL5 parity harness

This is the highest-value engineering control in the project, and it is why "research is the
source of truth" is enforceable rather than aspirational.

```
MT5 bars ──► export to CSV ──► Python engine ──► signal series S_py
     │
     └─────► MT5 Strategy Tester (EA in PARITY_LOG mode) ──► signal series S_mq5

                        assert S_py ≡ S_mq5
```

**Acceptance criteria:**
- Direction must match on **100%** of bars. Any mismatch is a blocking defect.
- Continuous values (ATR, realised vol, score) must match within `1e-6` relative tolerance,
  after accounting for documented differences in indicator warm-up conventions.
- The harness runs in CI on every change to either implementation.

Without this, we will eventually deploy an EA whose behaviour differs from the validated
research and we will not know it. Every mismatch found here is a live loss prevented.

---

## 7. What V1 actually contains

Deliberately small. Complexity is added only by the promotion process in
[ROADMAP.md](ROADMAP.md) §4.

| Module | V1 |
|---|---|
| Data layer | Exchange OHLCV (research) + MT5 bars (production) + reconciliation report |
| Feature engine | Returns, ATR, realised vol, vol percentile, MA distances |
| Regime | Continuous `vol_scalar` + binary `is_abnormal`. No directional labels |
| Strategy engines | **One**: multi-lookback trend ensemble |
| Ensemble | Equal-weight average across lookbacks. No cross-strategy weighting |
| Filters | Spread gate, abnormality gate, duplicate guard |
| Sizing | Volatility-scaled, capped |
| Risk engine | Per-trade, daily, weekly, peak-DD, gross exposure, kill switch |
| Execution | Idempotent order placement, table-driven error handling, reconciliation |
| Position mgmt | Exit on signal reversal; wide ATR catastrophe stop |
| Logging | Full structured event log |
| External data | Stub returning `None` |

Explicitly **not** in V1: mean reversion, breakout as a separate module, directional regimes,
multi-timeframe confirmation, partial profit taking, break-even stops, conviction-scaled sizing,
Kelly sizing, correlation-optimised allocation, martingale/grid anything.
