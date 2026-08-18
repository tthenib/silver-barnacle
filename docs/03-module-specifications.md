# 03 — Module Specifications and Interfaces

Status: **accepted**  ·  Last reviewed: 2026-08-18

Every module below states: **responsibility**, **must not**, **interface**, and **tests**.
The "must not" lines are as load-bearing as the responsibilities — most architectural decay in
trading systems is a module quietly acquiring a capability it was designed not to have.

MQL5 note: `interface` is a real language keyword, but an MQL5 interface may not contain data
members, constructors or destructors, and all its methods are implicitly public and pure
virtual. Where a contract needs state, an abstract base class with pure virtual methods
(`= 0`) is used instead. Both forms are noted below.

---

## Core types

The vocabulary that crosses module boundaries. Defined once in `Core/Types.mqh`.

```mql5
//--- A feature vector for one symbol at one closed bar.
//    `valid` is the contract: if false, NOTHING downstream may act on this.
struct FeatureVector {
   bool      valid;
   string    symbol;
   datetime  bar_time_utc;       // open time of the CLOSED bar these features describe
   int       bars_available;     // for warm-up gating
   double    close;
   double    atr;                // ATR(atr_period) on closed bars
   double    donchian_hi;        // highest high of the lookback, EXCLUDING current bar
   double    donchian_lo;
   double    realised_vol;       // stdev of log returns, annualised
   double    spread_points;      // observed at decision time
   int       invalid_reason;     // ENUM_SB_ERROR when valid == false
};

//--- A strategy's opinion. Contains NO sizing and NO order details.
struct Signal {
   int       direction;          // +1 long, -1 short, 0 flat/none
   double    confidence;         // [0,1]; 1.0 for binary strategies — NOT a sizing input
                                 // until an experiment shows it predicts outcome
   double    stop_price;         // absolute price; strategy owns stop PLACEMENT
   double    target_price;       // 0.0 = no fixed target (rule-based exit)
   int       expected_bars_held; // for turnover/cost projection
   string    strategy_id;
   string    reason;             // human-readable; goes into the journal verbatim
};

//--- What the portfolio layer hands to sizing. Still not an order.
struct OrderIntent {
   string    symbol;
   int       direction;
   double    stop_price;
   double    target_price;
   string    strategy_id;
   string    reason;
   datetime  decision_time_utc;
   string    intent_id;          // deterministic hash — the idempotency key
};

//--- Sizing output. Reports the GAP between intent and achievable reality.
struct SizingResult {
   bool      ok;
   double    lots;
   double    intended_risk_ccy;  // what we wanted to risk
   double    achieved_risk_ccy;  // what the quantised lot actually risks
   double    quantisation_error; // achieved / intended - 1  (always <= 0: we round DOWN)
   double    est_cost_ccy;       // round-turn cost estimate from CostModel
   int       reject_reason;      // ENUM_SIZING_REJECT
};

//--- The ONLY object the execution engine will act on.
//    Produced exclusively by RiskEngine. Invariant I1.
struct ApprovedOrder {
   OrderIntent  intent;
   double       lots;
   double       stop_price;
   double       target_price;
   string       approval_id;
   datetime     approved_at_utc;
   double       risk_ccy;
   double       portfolio_heat_after;   // recorded for the journal
};

struct RiskDecision {
   bool           approved;
   ApprovedOrder  order;
   int            reject_reason;        // ENUM_RISK_REJECT
   string         reject_detail;
};
```

**Why `Signal` carries no size.** A strategy that could express size could express leverage,
and would eventually be tuned to do so. Separating opinion from magnitude means the risk engine
is the only thing that can make a position large — which is the whole point of having one.

**Why `confidence` is not a sizing input yet.** Confidence-weighted sizing is a reasonable
hypothesis but it is *a hypothesis*: it asserts that the strategy's self-assessment predicts
realised outcome. That is testable (bucket trades by confidence, compare realised expectancy)
and until it is tested, confidence is logged and ignored. Wiring it into sizing before testing
it would add a free parameter and a plausible story, which is exactly the combination that
produces overfitting.

---

## 1. Configuration — `Config/`

**Responsibility.** Declare every tunable in one place; copy into an immutable struct at init;
validate fail-closed before any other module initialises.

**Must not.** Be read from disk at runtime; be mutated after init; be duplicated as magic
numbers elsewhere.

```mql5
class CConfigValidator {
public:
   // Returns false and populates `errors` if ANY check fails.
   // The EA returns INIT_FAILED on false. No partial starts, ever.
   bool  Validate(const SConfig &cfg, string &errors[]);
private:
   bool  CheckRanges(const SConfig &cfg, string &e[]);
   bool  CheckCrossParameter(const SConfig &cfg, string &e[]);   // exit_n < entry_n, etc.
   bool  CheckEnvironment(const SConfig &cfg, string &e[]);      // demo mode, margin mode
   bool  CheckInstruments(const SConfig &cfg, string &e[]);      // exists, tradeable, sane specs
};
```

`CheckEnvironment` asserts `ACCOUNT_TRADE_MODE == ACCOUNT_TRADE_MODE_DEMO` (C10) and records
`ACCOUNT_MARGIN_MODE`. Hedging and netting accounts have *different position semantics* — on a
netting account a second buy adds to an existing position rather than creating a new one, which
silently breaks per-trade risk accounting. The mode is detected, recorded in the manifest, and
the execution engine's behaviour depends on it explicitly rather than by accident.

**Tests.** Every validation rule has a rejecting case. A config that should fail and does not
is a test failure.

---

## 2. Market data — `Data/`

**Responsibility.** Provide closed-bar OHLCV and validated symbol specifications; detect data
that should not be traded on.

**Must not.** Expose bar 0 outside `BarProvider`; return values without a validity indication;
silently pad or interpolate gaps.

```mql5
class CBarProvider {
public:
   bool  Init(const string &symbols[], ENUM_TIMEFRAMES tf);
   // True exactly once per newly closed bar for `symbol`.
   bool  IsNewClosedBar(const string symbol, datetime &closed_bar_time_utc);
   // Copies `count` CLOSED bars ending at the most recent close. shift>=1 enforced internally.
   BoolResult  GetClosedBars(const string symbol, int count, MqlRates &out[]);
   int   BarsAvailable(const string symbol);
};

class CSymbolCatalog {
public:
   bool  Init(const string &symbols[]);
   // Cached at init: volume min/max/step, tick size, tick value (profit/loss),
   // contract size, digits, point, stops level, freeze level, margin rates.
   BoolResult  Get(const string symbol, SSymbolSpec &out);
   bool  IsTradeable(const string symbol);   // session open + trade mode + not disabled
};

class CDataQuality {
public:
   // Evaluated before every decision. Failure blocks the decision (R8).
   SDataQualityVerdict  Evaluate(const string symbol, const MqlRates &bars[]);
   // Checks: bar gaps vs expected session calendar; stale last tick;
   //         zero/negative prices; high<low; absurd bar range vs trailing ATR;
   //         spread > configured absolute ceiling.
};
```

**On tick value.** `SYMBOL_TRADE_TICK_VALUE` is expressed in the *account currency* and, for
instruments whose profit currency differs from the account currency, it varies with the
prevailing cross rate. Caching it once at init and reusing it for months is a real and
frequently-made sizing bug. The catalog caches *static* specifications; tick value is re-read at
each sizing call. Sizing is additionally cross-checked against `OrderCalcProfit`, which performs
the conversion authoritatively.

**Tests.** Gap detection against a synthetic calendar with known holidays; staleness under a
frozen feed; rejection of `high < low`; bar-0 access refused.

---

## 3. Features — `Features/`

**Responsibility.** Compute derived quantities from closed bars, with explicit validity.

**Must not.** Read bar 0; return a value when the underlying copy was short; leak indicator
handles.

```mql5
class CFeatureEngine {
public:
   bool  Init(const string &symbols[], ENUM_TIMEFRAMES tf, const SFeatureConfig &cfg);
   void  Deinit();                                   // IndicatorRelease for every handle
   // Returns a vector whose `valid` is false unless EVERY component succeeded
   // and bars_available >= warmup.
   FeatureVector  Compute(const string symbol, datetime closed_bar_time_utc);
};
```

**The critical implementation rule.** `CopyBuffer` and `CopyRates` return the number of
elements actually copied, which is routinely fewer than requested during indicator warm-up,
after a history gap, or when the terminal is still synchronising. Any short copy sets
`valid = false` with `invalid_reason = SB_ERR_INSUFFICIENT_HISTORY`. It never yields a default
`0.0`.

An ATR of `0.0` propagates into the position sizer as a division by zero or, worse, as an
enormous position — this single defect is capable of destroying an account, and it originates
in a return value that a naive implementation never inspects.

**Tests.** Golden vectors from `research/golden/indicators.py`, asserted to 1e-9 across a
multi-year window. Deliberate short-history fixtures asserting `valid == false`. A handle-leak
test that initialises and deinitialises 1,000 times and checks handle count.

---

## 4. Strategy — `Strategy/`

**Responsibility.** Map features to a signal. Nothing else.

**Must not.** Perform I/O, read account state, call trade functions, know about risk limits,
know about other strategies, or hold state that is not reconstructible from history.

```mql5
interface IStrategy {
   string  Id();
   int     WarmupBars();
   // Pure: same features in ⇒ same signal out. No side effects.
   bool    Evaluate(const FeatureVector &fv, const SPositionView &current, Signal &out);
   // Exit evaluation for an open position owned by this strategy.
   bool    EvaluateExit(const FeatureVector &fv, const SPositionView &pos, SExitDecision &out);
   // Machine-readable self-description — see below.
   void    Describe(StrategyManifest &m);
};
```

### The strategy manifest

The brief requires every strategy to declare its entry logic, exit logic, stop logic, sizing
requirements, expected holding period, applicability, parameters, assumptions, failure
conditions, and cost sensitivity. `Describe()` makes those **machine-readable and mandatory**
rather than prose in a document that drifts out of date:

```mql5
struct StrategyManifest {
   string  id;
   string  family;                  // trend | mean_reversion | breakout | volatility | ...
   string  entry_logic;
   string  exit_logic;
   string  stop_logic;
   string  economic_rationale;      // WHY this might work. Empty ⇒ config validation FAILS.
   int     param_count;             // enters the overfitting budget
   string  param_names[];
   int     expected_hold_bars;
   string  applicable_instruments[];
   ENUM_TIMEFRAMES applicable_timeframes[];
   string  assumptions[];
   string  failure_conditions[];    // conditions under which we EXPECT this to lose
   double  est_round_turns_per_year;
};
```

`Describe()` output is written into the run manifest, so every result carries the strategy's own
declared assumptions alongside it. `economic_rationale` being mandatory is a deliberate
tripwire: a rule that cannot be given a reason for existing is a data-mined pattern, and this
forces that admission at compile time rather than after three months of testing.

`failure_conditions` is used at gate review: if a strategy does *not* lose money under the
conditions it declared it should, that is evidence the backtest is wrong, not that the strategy
is unusually good.

**Tests.** Purity (same input ⇒ same output, 1,000 iterations); no signal before warm-up; no
signal on `valid == false`; the specific entry/exit conditions against hand-computed fixtures.

---

## 5. Portfolio — `Portfolio/`

**Responsibility.** Maintain the aggregate exposure view; arbitrate between competing intents.

**Stage 0–5:** `Allocator` is a pass-through. `PortfolioState` and `ExposureModel` are *real*
from stage 1, because the risk engine needs them.

**Must not.** Optimise weights, estimate correlations from short samples, or exist as
speculative machinery before a second strategy justifies it.

```mql5
class CPortfolioState {
public:
   void    Refresh();                              // from broker truth, not cache
   int     OpenPositionCount();
   int     OpenPositionCount(const string symbol);
   double  TotalRiskCcy();                         // Σ distance-to-stop × value
   double  GrossNotionalCcy();
   double  MarginUtilisation();                    // used / equity
   // Net exposure to a named risk factor across all open positions.
   double  FactorExposure(const string factor);
};

class CExposureModel {
public:
   bool    Init(const SInstrumentConfig &instruments[]);
   // Maps a symbol to signed risk-factor loadings from config/instruments.yaml.
   void    Factors(const string symbol, int direction, SFactorLoading &out[]);
   // Correlated heat: risk if all positions sharing a factor move adversely together.
   double  CorrelatedHeat(const CPortfolioState &state, const OrderIntent &candidate);
};
```

**Why factor loadings rather than a correlation matrix.** A correlation matrix estimated from
a few hundred daily observations is unstable, and it will happily tell you that EURUSD and
GBPUSD were uncorrelated during the sample where they happened not to be. The *structural*
fact — that long EURUSD and short USDCHF are both short USD — is known a priori and does not
need estimating. Stage 1 uses declared structure. Measured correlation is a later candidate
enhancement that must beat the structural model out-of-sample to be adopted.

**Tests.** Long EURUSD + short USDCHF reports roughly doubled USD exposure, not offsetting.
Correlated heat exceeds naive summed heat for same-factor positions.

---

## 6. Position sizing — `Risk/PositionSizer.mqh`, `Risk/LotQuantiser.mqh`

**Responsibility.** Convert a risk budget and a stop distance into a broker-legal volume, and
report honestly what that volume actually risks.

**Must not.** Round up; ignore volume limits; use cached tick values; use martingale or any
loss-dependent adjustment.

```mql5
class CPositionSizer {
public:
   // risk_basis comes from CapitalLedger, NOT from AccountInfoDouble(ACCOUNT_EQUITY).
   SizingResult  Size(const OrderIntent &intent,
                      double risk_basis_ccy,
                      double risk_fraction,
                      const SSymbolSpec &spec);
};

class CLotQuantiser {
public:
   // Always rounds DOWN to volume_step, then clamps to [min,max] and SYMBOL_VOLUME_LIMIT.
   // Returns ok=false if the result is below minimum volume — a trade we cannot size
   // correctly is a trade we do not take.
   SizingResult  Quantise(double desired_lots, const SSymbolSpec &spec);
};
```

### Lot quantisation: resolved at £100,000, but the checks stay

At the original £2,000 this was a first-class constraint. It no longer is, and the arithmetic
is worth recording so the change is understood rather than assumed.

EURUSD, 0.5% risk target, 50-pip stop. One 0.01-lot step risks ≈ $5 ≈ **£4**:

| Basis | Risk target | Desired lots | Quantised (step 0.01) | Realised risk | Grid width |
|-------|------------|--------------|----------------------|---------------|-----------|
| £2,000 | £10 | 0.025 | **0.02** | £8 = **80% of intended** | 0.20% of equity |
| £100,000 | £500 | 1.25 | **1.25** | £500 = **100%** | 0.004% of equity |

The grid is ~50× finer and ceases to bind for liquid instruments.

**The constraint inverts rather than disappearing.** At £2,000 the danger was the volume
*floor* — trades too small to size correctly. At £100,000 it is the volume *ceiling*:
`SYMBOL_VOLUME_MAX`, `SYMBOL_VOLUME_LIMIT` (aggregate one-directional exposure), and margin
now bind first. A 0.5% risk against a tight stop — say 5 pips on a volatile instrument — is
~10 lots rather than ~1.25, and that is where a cap will actually be hit.

All four behaviours below are retained unchanged, because they are ratio-based and a future
change of basis, instrument, or stop width can make any of them bind again:

1. `SizingResult.quantisation_error` is logged on every trade and its distribution reported.
   Expected to be ≈0 now; a non-zero distribution is a signal that something (a coarse
   instrument, an unusually wide stop) is behaving unlike the rest of the panel.
2. Rounding is **always down**. Rounding to nearest would let realised risk exceed the
   configured cap, which would make the cap a suggestion.
3. Sub-minimum sizing produces a **rejection** logged with `SIZE_BELOW_MINIMUM` — never a
   silent minimum-lot trade. Silently trading the minimum is how a "0.5% risk" system ends up
   taking 2% risk on its most volatile instruments, which are precisely the ones where a wide
   stop forces the smallest size.
4. Sizing **clamped at the ceiling** produces a rejection or a logged clamp with
   `SIZE_ABOVE_MAXIMUM`, never a silently truncated position. A position capped at 60% of its
   intended size is a different trade from the one the strategy asked for, and the journal must
   say so or the realised strategy diverges from the tested one without trace.

**Tests.** Golden table of (equity, risk %, stop distance, symbol spec) → expected lots,
covering 5-digit FX, JPY pairs (different pip scale), gold, and an index. Rounding is never up.
Sub-minimum returns `ok=false`. Achieved risk never exceeds intended.

---

## 7. Risk engine — `Risk/RiskEngine.mqh`

**Responsibility.** The mandatory chokepoint. Consumes an intent plus full system state, emits
`ApprovedOrder` or a typed rejection. It is the only producer of `ApprovedOrder`.

**Must not.** Be bypassed; be optional; approve anything it cannot fully evaluate.

```mql5
class CRiskEngine {
public:
   bool  Init(const SRiskLimits &limits,
              CPortfolioState *portfolio, CExposureModel *exposure,
              CCapitalLedger *ledger, CDrawdownGuard *dd, CCircuitBreaker *cb,
              CCostModel *costs);

   // The single entry point. Evaluates ALL checks; on rejection returns the
   // FIRST-BINDING reason, and logs every check's outcome for research.
   RiskDecision  Evaluate(const OrderIntent &intent, const SSymbolSpec &spec);

   // Called on every tick — can force-close or halt independent of any signal.
   SRiskAction   Supervise();
};
```

### Checks, in evaluation order

| # | Check | Rejection reason |
|---|-------|------------------|
| 1 | Global trading enabled | `TRADING_DISABLED` |
| 2 | Circuit breaker clear (spread, price jump, exec errors, data quality) | `CIRCUIT_BREAKER_<x>` |
| 3 | Drawdown state (daily / weekly / peak-to-trough) | `DRAWDOWN_LIMIT_<x>` |
| 4 | Consecutive-loss cooldown active | `LOSS_STREAK_COOLDOWN` |
| 5 | Max open positions (total and per symbol) | `MAX_POSITIONS` |
| 6 | Duplicate intent already in flight | `DUPLICATE_INTENT` |
| 7 | Sizing succeeded, above minimum and within volume/`VOLUME_LIMIT` ceiling | `SIZE_BELOW_MINIMUM` / `SIZE_ABOVE_MAXIMUM` |
| 8 | Achieved risk ≤ per-trade cap | `PER_TRADE_RISK_EXCEEDED` |
| 9 | Portfolio heat after this trade ≤ cap | `PORTFOLIO_HEAT_EXCEEDED` |
| 10 | Correlated (factor) heat ≤ cap | `CORRELATED_EXPOSURE_EXCEEDED` |
| 11 | Per-instrument exposure ≤ cap | `INSTRUMENT_EXPOSURE_EXCEEDED` |
| 12 | Margin utilisation after this trade ≤ cap (`OrderCalcMargin`) | `MARGIN_LIMIT` |
| 13 | Stop respects `SYMBOL_TRADE_STOPS_LEVEL` / freeze level | `INVALID_STOP_DISTANCE` |
| 14 | Estimated cost ≤ configured fraction of expected edge | `COST_EXCEEDS_EDGE` |
| 15 | Session / time-of-day permitted | `OUTSIDE_SESSION` |

Every rejection is written to `RejectJournal` **with the full decision context**. Rejections are
primary research data (R9): a strategy rejected 400 times for `PORTFOLIO_HEAT_EXCEEDED` has an
entirely different realised return stream from its unconstrained backtest, and this is the only
place that fact is visible.

Check 14 deserves emphasis: it compares the modelled round-turn cost against the strategy's
declared expected edge per trade. A trade whose expected cost consumes most of its expected
edge is not worth its execution risk, and blocking it at the risk layer means no strategy can
quietly rely on trades that only look profitable under optimistic cost assumptions.

**`Supervise()`** runs on every tick and is what makes the risk engine capable of *overriding*
strategies rather than merely filtering them: it can trip the breaker, force a flatten, or move
the system to `HALTED`, with no strategy involvement.

**Tests.** Each of the 15 checks has a case that trips it and a case that passes it.
Ordering test: when several checks would fail, the first-binding reason is reported. A
fuzz test asserting `ApprovedOrder` is never produced when any limit is breached.

---

## 8. Drawdown and circuit breakers — `Risk/DrawdownGuard.mqh`, `Risk/CircuitBreaker.mqh`

```mql5
class CDrawdownGuard {
public:
   void    OnEquityUpdate(double equity, datetime now_utc);
   bool    DailyLimitBreached();      // resets at configured UTC hour, not broker midnight
   bool    WeeklyLimitBreached();
   bool    PeakToTroughBreached();
   double  CurrentDrawdownPct();
   void    Persist();  void  Restore();   // survives restart — a restart must not reset a limit
};

class CCircuitBreaker {
public:
   void  OnTick(const string symbol, const MqlTick &tick);
   void  OnExecutionResult(const SExecutionResult &r);
   void  OnDataQuality(const SDataQualityVerdict &v);
   bool  IsTripped(ENUM_BREAKER &which);
   // Deliberately MANUAL. An auto-resetting breaker is not a breaker.
   void  Reset(const string operator_reason);
};
```

Breakers: spread exceeds `k ×` its trailing median; price jump exceeds `k ×` ATR within one
tick; `N` execution errors within a window; data-quality failure; realised slippage exceeding
threshold over a rolling window; equity change inconsistent with recorded positions.

**Two decisions worth stating.** Drawdown state is *persisted*: a system that resets its daily
loss limit by restarting has no daily loss limit. And breakers require manual reset: automatic
recovery from a condition nobody diagnosed is how a system trades through the event it was
built to sit out.

**Tests.** Daily reset at the configured UTC hour across a DST boundary. Limit survives a
simulated restart. Breaker trips at threshold and not below.

---

## 9. Capital ledger — `Capital/CapitalLedger.mqh`

**Responsibility.** Paper accounting for the 80/20 allocation, and derivation of the sizing
basis. Entirely separate from the broker account (C11).

**Must not.** Attempt any transfer or withdrawal; let compounding raise risk without passing
the risk engine's absolute caps.

```mql5
class CCapitalLedger {
public:
   bool    Init(double initial_capital, double retain_fraction /*0.80*/,
                ENUM_ALLOC_FREQ freq, double max_capital_scale /*e.g. 2.0*/);
   void    OnPeriodEnd(datetime now_utc, double account_equity);

   double  TradingEquity();        // live account equity
   double  RetainedCapital();      // initial + reinvested share of realised profit
   double  ReservedCapital();      // notionally withdrawn — one-way, HWM-based
   double  TotalGeneratedProfit(); // gross strategy profit since inception

   // THE sizing basis. Never AccountInfoDouble(ACCOUNT_EQUITY) directly.
   double  SizingBasis();
};
```

### Three rules that prevent the obvious failure modes

**High-water-mark allocation.** Reserve 20% only of *new* profit above the previous high-water
mark. Without this, a system that gains £100, loses it, and regains it reserves £40 against £100
of profit — steadily draining trading capital through a flat period.

**One-way reserves.** Reserved capital is never returned to trading capital. Un-reserving on a
drawdown would mean increasing risk *because* the system is losing, which is martingale wearing
an accounting disguise.

**Capped compounding.** The brief requires that a larger account must not silently mean
proportionally larger risk. Concretely:

```
SizingBasis = min( account_equity,
                   retained_capital,
                   initial_capital × max_capital_scale )
```

- `min(equity, retained)` means reserved profit stops sizing positions, as intended.
- `equity` in the `min` means a drawdown reduces size immediately, without waiting for a
  period-end allocation event.
- `initial_capital × max_capital_scale` is the hard ceiling: risk cannot more than double
  without a human changing a parameter and re-validating. Growth from £100,000 to £200,000
  scales risk; growth beyond that requires a deliberate decision, because a strategy validated
  at one position-size regime has not been validated at another — margin behaviour, the volume
  ceiling, and (if the system were ever run with real capital) fill quality all change with
  size.

**Tests.** HWM logic across gain → loss → regain (reserve must not double-count). One-way
property under drawdown. `SizingBasis` never exceeds the scale ceiling. Ledger identity
`retained + reserved == initial + total_profit` holds after every event.

---

## 10. Transaction costs — `Costs/`

**Responsibility.** Estimate round-turn cost per candidate trade, pessimistically, and expose
the parameters the harness perturbs.

```mql5
class CCostModel {
public:
   bool    Init(const SCostConfig &cfg);   // per-instrument, versioned, from config/
   // Pessimistic estimate: spread at decision + commission + expected slippage
   //                       (entry AND exit) + swap × expected holding nights.
   double  EstimateRoundTurnCcy(const string symbol, double lots,
                                int expected_bars_held, ENUM_TIMEFRAMES tf);
   double  ObservedSpreadCcy(const string symbol, double lots);
   void    RecordRealised(const SExecutionResult &r);   // for backtest-vs-live comparison
};

class CSlippageModel {
public:
   // Deterministic given the seed. Asymmetric by default: adverse slippage is
   // modelled larger than favourable, because that is what execution actually does.
   double  ExpectedSlippagePoints(const string symbol, double lots, double spread_points);
};
```

### The metric that matters: cost tolerance

Rather than the "±20% of baseline spread" perturbation the source documents propose, the
harness solves for a single interpretable scalar:

> **Cost tolerance** = the additional round-turn cost, in price units, that reduces the
> strategy's net expectancy to exactly zero.

It is then compared against the *observed* distribution of real spreads for that instrument
(measured by `ExportTickStats.mq5`, not assumed):

| Cost tolerance vs observed spread distribution | Verdict |
|---|---|
| < 1 SD of the spread distribution | **Fragile** — normal spread variation destroys the edge |
| 1–3 SD | Marginal — passes only with strong evidence elsewhere |
| > 3 SD | Robust to execution assumptions |

This is strictly more informative than a percentage perturbation, because it answers the actual
question — *how wrong can my cost assumption be before my conclusion flips?* — in units that can
be compared to measured reality.

**Tests.** Cost estimate against hand-computed values per instrument class. Cost tolerance
solver against a synthetic strategy with a known analytic breakeven. Swap accrual over
weekends (triple-swap Wednesday behaviour is broker-specific — measured, not assumed).

---

## 11. Execution — `Execution/`

**Responsibility.** Turn `ApprovedOrder` into a broker position, track it through an explicit
state machine, reconcile against broker truth, and never place an order twice.

**Must not.** Accept anything but an `ApprovedOrder`; assume success from a return value;
retry blindly.

```mql5
class CExecutionEngine {
public:
   SExecutionResult  Submit(const ApprovedOrder &order);
   void  OnTradeTransaction(const MqlTradeTransaction &t,
                            const MqlTradeRequest &r, const MqlTradeResult &res);
   void  OnTick();                 // stop maintenance, freeze-level awareness
   SReconcileReport  Reconcile();  // startup + periodic
};
```

### The state machine

```
                    ┌──────────┐
                    │ APPROVED │
                    └────┬─────┘
                         │ journal intent to disk BEFORE sending  ◄── crash-safety point
                    ┌────▼─────┐
              ┌─────┤ SUBMITTED├─────┐
              │     └────┬─────┘     │
       retcode error     │ DEAL_ADD  │ timeout / no response
              │          │           │
        ┌─────▼────┐ ┌───▼──────┐ ┌──▼──────────┐
        │ REJECTED │ │ PARTIAL  │ │ UNCERTAIN   │──► reconcile before ANY further action
        └──────────┘ └───┬──────┘ └─────────────┘
                         │ remaining volume filled / cancelled
                    ┌────▼─────┐
                    │  OPEN    │◄──► MODIFYING (stop moves)
                    └────┬─────┘
                    ┌────▼─────┐
                    │ CLOSING  │──► CLOSED ──► journalled
                    └──────────┘
```

`UNCERTAIN` is the state most implementations omit and the one that matters most. A request that
times out, or a terminal that disconnects mid-submission, leaves the system genuinely not
knowing whether a position exists. The only correct response is to stop and reconcile against
the broker — not to retry (which risks a duplicate) and not to assume failure (which risks an
unmanaged, unstopped position).

### Idempotency

`intent_id` is a deterministic hash of `(strategy_id, symbol, decision_bar_time, direction)`.
It is written to `IdempotencyJournal` **before** the order is sent. On restart, any journalled
intent without a matching position or a recorded terminal outcome enters reconciliation.

Because the key is derived from the *decision bar*, the same bar cannot generate two orders even
across a restart — which is the specific scenario in which duplicate-order bugs actually occur.

**Verification note.** MQL5's `MqlTradeResult.retcode` distinguishes `TRADE_RETCODE_DONE`,
`TRADE_RETCODE_PLACED`, `TRADE_RETCODE_DONE_PARTIAL` and a large set of error codes; fills are
confirmed through `OnTradeTransaction` with `TRADE_TRANSACTION_DEAL_ADD`. The exact retcode
handling table is to be built against the MQL5 trade-server return-codes reference during
implementation, and against the actual demo broker's observed behaviour — retcode semantics vary
between brokers in practice, so the table is validated empirically before it is trusted.

**Tests.** State machine transition table (legal transitions succeed, illegal ones assert).
Duplicate submission with the same `intent_id` is refused. Simulated restart mid-`SUBMITTED`
resolves to reconciliation, never to a duplicate. Partial fill leaves consistent state.

---

## 12. Telemetry — `Telemetry/`

**Responsibility.** Make every decision reconstructible.

```mql5
class CTradeJournal {
public:
   // One row per trade. Sufficient to reconstruct WHY, not merely WHAT.
   void  WriteEntry(const ApprovedOrder &o, const FeatureVector &fv,
                    const SExecutionResult &r, const CPortfolioState &p,
                    const SRiskSnapshot &risk, double est_cost);
   void  WriteExit(const SPositionView &pos, const SExecutionResult &r,
                   const string exit_reason, double realised_cost);
};

class CRejectJournal {
public:
   // Rejections are DATA. Same context depth as an accepted trade.
   void  Write(const OrderIntent &i, const RiskDecision &d,
               const FeatureVector &fv, const CPortfolioState &p);
};

class CRunManifest {
public:
   void  WriteAtInit();   // git SHA, terminal build, account/margin mode, symbol specs,
                          // full parameter set + hash, cost model version, seed,
                          // measured server-UTC offset, every strategy's Describe()
};
```

Journals are newline-delimited JSON with a **versioned schema**. `research/ingest/schema.py`
fails loudly on a version mismatch rather than silently mis-parsing — a research pipeline that
misreads a renamed column produces confidently wrong numbers.

**On file paths in the tester.** MQL5 file access is sandboxed to `MQL5/Files/` or the common
folder (`FILE_COMMON`). Under optimisation, each tester agent has its own sandbox, and
concurrent writes to the common folder race. Therefore: per-pass detail journals are written to
the **agent-local** sandbox, while aggregate per-pass metrics return to the master terminal via
the sanctioned **frames** mechanism (`FrameAdd` in `OnTester`, collected in `OnTesterPass`).

**Tests.** Round-trip: journal → Python ingest → identical values. Schema-version mismatch
raises. Every `ENUM_RISK_REJECT` value appears in at least one journal test.

---

## 13. Diagnostics — `Diagnostics/`

```mql5
#define SB_ASSERT(cond, msg)   // logs, journals, HALTS. Never continues in release.
class CHealthCheck {  SHealthReport Run();  };   // on timer
class CSelfTest    {  bool RunAtInit();      };  // broker-spec sanity before trading
```

`SelfTest` runs at init against the *live broker specification*, not against fixtures: size a
notional trade on each instrument and assert the computed risk matches the intent within
tolerance; verify `OrderCalcProfit` agrees with the sizer's own arithmetic; verify stops-level
constraints are satisfiable at current volatility. A broker whose specifications make the
configured risk unachievable is detected before the first trade, not after it.

Assertions **halt**. A trading system that continues past a violated invariant is placing
orders based on a state its author believed impossible.

---

## 14. Module dependency rules

```
Core         ← everything (no dependencies of its own)
Config       ← Core
Data         ← Core, Config
Features     ← Core, Data
Strategy     ← Core, Features                    (I3: nothing else — enforced)
Portfolio    ← Core, Config, Data
Costs        ← Core, Config, Data
Capital      ← Core, Config
Risk         ← Core, Config, Portfolio, Capital, Costs, Data
Execution    ← Core, Config, Risk (types only), Data     (I1: sole Trade.mqh includer)
Telemetry    ← Core  (+ read-only views passed as parameters)
Diagnostics  ← Core
```

Enforced by `tools/lint_invariants.py`. There are no cycles, and `Strategy` sits at a leaf —
which is what makes strategies safe to write quickly and safe to delete.
