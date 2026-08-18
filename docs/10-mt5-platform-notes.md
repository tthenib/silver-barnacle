# 10 — MT5 / MQL5 Platform Notes: Verified Facts and Source-Document Corrections

Status: **living document**  ·  Last verified: 2026-08-18

Everything in Part 1 was checked against MetaQuotes documentation on the date above. Anything
not verified is marked **[UNVERIFIED]** and must be confirmed before it is relied on. Nothing
here is asserted from recall.

Part 2 records defects found in the code contained in the three source documents. It exists
because those documents will otherwise be treated as reference material, and their code does not
compile as MQL5.

---

# Part 1 — Verified platform facts

## 1.1 Indicators return handles, not values

```mql5
int iMA(string symbol, ENUM_TIMEFRAMES period, int ma_period, int ma_shift,
        ENUM_MA_METHOD ma_method, ENUM_APPLIED_PRICE applied_price);
```

Returns an **indicator handle** (`INVALID_HANDLE` on failure), not a price. Values are read with
`CopyBuffer()`; the handle is released with `IndicatorRelease()`.
Source: [MQL5 Reference — iMA](https://www.mql5.com/en/docs/indicators/ima)

**Consequence for us.** Handles are created once at init and owned by `IndicatorHandles`
(never per call, which leaks). `CopyBuffer` returns the number of elements actually copied —
routinely fewer than requested during warm-up — and every short read sets
`FeatureVector.valid = false`. This is IB-2 in [`09`](09-risk-register.md), and it is the single
most dangerous silent failure in the platform.

## 1.2 Trade calculation functions

```mql5
bool OrderCalcProfit(ENUM_ORDER_TYPE action, string symbol, double volume,
                     double price_open, double price_close, double &profit);
```
Source: [MQL5 Reference — OrderCalcProfit](https://www.mql5.com/en/docs/trading/ordercalcprofit)

`OrderCalcMargin` exists as a companion function. **[UNVERIFIED]** — its exact signature was not
confirmed and must be checked before the margin-utilisation check (RiskEngine check 12) is
implemented.

`OrderCalcProfit` performs currency conversion authoritatively, which is why the position sizer
cross-checks its own arithmetic against it rather than trusting a hand-rolled tick-value
calculation.

## 1.3 Symbol properties and their accessors

Getting the accessor wrong is a compile error at best and a silent zero at worst.

| Property | Accessor |
|----------|----------|
| `SYMBOL_VOLUME_MIN` / `_MAX` / `_STEP` / `_LIMIT` | `SymbolInfoDouble` |
| `SYMBOL_TRADE_TICK_SIZE` | `SymbolInfoDouble` |
| `SYMBOL_TRADE_TICK_VALUE` | `SymbolInfoDouble` |
| `SYMBOL_TRADE_TICK_VALUE_PROFIT` / `_LOSS` | `SymbolInfoDouble` |
| `SYMBOL_TRADE_CONTRACT_SIZE` | `SymbolInfoDouble` |
| `SYMBOL_POINT` | `SymbolInfoDouble` |
| `SYMBOL_SWAP_LONG` / `_SHORT` | `SymbolInfoDouble` |
| `SYMBOL_MARGIN_INITIAL` / `_MAINTENANCE` / `_HEDGED` | `SymbolInfoDouble` |
| **`SYMBOL_TRADE_STOPS_LEVEL`** | **`SymbolInfoInteger`** |
| **`SYMBOL_TRADE_FREEZE_LEVEL`** | **`SymbolInfoInteger`** |
| **`SYMBOL_SPREAD`** | **`SymbolInfoInteger`** (points) |

Source: [MQL5 Reference — Symbol Properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants)

Notes that matter for sizing:

- `SYMBOL_TRADE_TICK_VALUE` is in **account currency** and for instruments whose profit currency
  differs it moves with the cross rate. Re-read per sizing call; never cache. (IB-3.)
- `SYMBOL_TRADE_TICK_VALUE_PROFIT` and `_LOSS` can differ. For risk sizing, the **loss** variant
  is the correct one — we are sizing against the adverse case.
- Tick size and point are not the same thing. Price normalisation uses **tick size**.

## 1.4 Tester and optimisation event handlers

```mql5
double OnTester(void);       // custom optimisation criterion; higher is better
void   OnTesterInit(void);   // before optimisation; can set ranges via ParameterSetRange
void   OnTesterPass(void);   // per pass; collects frames
void   OnTesterDeinit(void); // after optimisation
```
Sources: [OnTester](https://www.mql5.com/en/docs/event_handlers/ontester),
[OnTesterInit](https://www.mql5.com/en/docs/event_handlers/ontesterinit)

Per-pass results are returned to the master terminal via the **frames** mechanism (`FrameAdd`
in `OnTester`, collected in `OnTesterPass`); `TesterStatistics()` exposes standard tester
metrics inside `OnTester`.

**Consequence.** Frames are how the harness collects optimisation results without racing on
files across parallel tester agents. Detailed per-pass journals go to the agent-local sandbox;
aggregate metrics come back through frames.

## 1.5 Strategy Tester modelling modes

Five modes: *Every tick*, *Every tick based on real ticks*, *1 minute OHLC*, *Open prices only*,
*Math calculations*. Real-tick mode uses ticks accumulated by the broker. The tester is
multi-currency: it downloads data for whatever symbols the EA touches. Forward testing can split
the period (1/2, 1/3, 1/4, or a custom date).
Source: [MetaTrader 5 Help — Testing](https://www.metatrader5.com/en/terminal/help/algotrading/testing)

**Consequences.** Real-tick availability is broker- and symbol-dependent and **must be measured**
(UB-2), which is what `ExportTickStats.mq5` is for. The tester's built-in forward split is *not*
used as our validation mechanism — split custody lives in `config/splits.yaml` under version
control, because a split defined in a GUI has no provenance.

## 1.6 Commission in the tester

For broker-supplied symbols, commission comes from the broker's symbol specification. For
**custom symbols** there is no commission section in the specification; commission must be
configured through the Strategy Tester's own custom commission settings, and symbol properties
**cannot be changed dynamically inside the tester**.
Sources: [Configuring trading fees in the MT5 Strategy Tester](https://www.mql5.com/en/blogs/post/746300),
[MQL5 forum — MT5 custom commission settings](https://www.mql5.com/en/forum/431220)

**Consequence.** Results must not depend on the tester's commission configuration being correct.
The EA computes commission independently from `config/cost_assumptions.yaml`, and
`HistoryDealGetDouble(DEAL_COMMISSION)` is compared against the model to detect double-counting
or omission. (UB-4.)

## 1.7 File sandbox

File functions can access only `<terminal_data>\MQL5\Files\` and the shared
`...\Terminal\Common\Files\` (with `FILE_COMMON`). Access elsewhere is prohibited.
Source: [MQL5 Reference — File Functions](https://www.mql5.com/en/docs/files)

Under optimisation each tester agent has its own sandbox. **[UNVERIFIED]** — the precise
behaviour of the common folder under parallel agents was not confirmed; concurrent writes are
assumed unsafe and frames are used instead (§1.4). Verify before any design depends on it.

## 1.8 ONNX

MQL5 supports ONNX inference (`OnnxCreate`, `OnnxCreateFromBuffer`, `OnnxRun`, `OnnxRelease`,
shape and type introspection), and models can be exercised in the Strategy Tester.
Source: [MQL5 Reference — ONNX models](https://www.mql5.com/en/docs/onnx)

Documented operator coverage and type restrictions were **not** enumerated; treat as
**[UNVERIFIED]** if ML work ever reaches its preconditions (R-401).

## 1.9 Custom symbols

`CustomSymbolCreate`, `CustomSymbolSetInteger/Double/String`, `CustomSymbolSetMarginRate`,
`CustomRatesUpdate/Replace/Delete`, `CustomTicksAdd/Replace/Delete`, `CustomBookAdd`.
Source: [MQL5 Reference — Custom Symbols](https://www.mql5.com/en/docs/customsymbols)

Useful later for stress testing against synthetic price series (including the seeded random walk
of G2.10). Commission caveat as in §1.6.

## 1.10 Interfaces and abstract classes

MQL5 has an `interface` keyword. An interface may **not** contain data members, a constructor, or
a destructor; all its methods are implicitly public and pure virtual. A class with at least one
pure virtual method (`= 0` or `= NULL`) is abstract and cannot be instantiated.
Sources: [Abstract Classes and Pure Virtual Functions](https://www.mql5.com/en/docs/basis/oop/abstract_type),
[MQL5 Book — Abstract classes and interfaces](https://www.mql5.com/en/book/oop/classes_and_interfaces/classes_abstract_interfaces)

**Consequence.** `IStrategy` is an `interface`. Contracts needing state use abstract base classes.

## 1.11 `CTrade` result inspection

`CTrade` provides `ResultRetcode()`, `ResultRetcodeDescription()`, `ResultDeal()`,
`ResultOrder()`, `ResultVolume()`, `ResultPrice()`, plus `SetTypeFilling()`,
`SetDeviationInPoints()`, `SetExpertMagicNumber()`.

**There is no `CTrade::LastError()`.**
Source: [MQL5 Reference — CTrade](https://www.mql5.com/en/docs/standardlibrary/tradeclasses/ctrade)

## 1.12 Command-line build and run

```bash
metaeditor64.exe /compile:"<path>" /inc:"<MQL5 dir>" /log:"<logfile>"
terminal64.exe   /config:"<tester .ini>"
```
Source: [MetaEditor Help — Compilation](https://www.metatrader5.com/en/metaeditor/help/development/compile)

**[PARTIALLY VERIFIED]** — switches are documented, but headless behaviour varies by build and
MetaEditor's CLI is reported to fail quietly on large multi-file projects
([MQL5 forum](https://www.mql5.com/en/forum/491543)). Confirm end-to-end on the target machine as
the first task of S3; the semi-automated fallback preserves every provenance property if it
proves unreliable.

## 1.13 Regulatory leverage (context, not a hard-coded value)

The FCA restricts retail CFD leverage to between **30:1 and 2:1** depending on the underlying
asset (COBS 22.5).
Source: [FCA PS19/18](https://www.fca.org.uk/publications/policy-statements/ps19-18-restricting-contract-difference-products)

**Consequence.** Neither D1's "1:100–1:500" nor D3's flat "30:1" is hard-coded. Actual margin
requirements are read from the terminal at runtime and validated at startup. Available leverage
is an observed property of the environment.

---

# Part 2 — Defects in the source documents' code

The three PDFs contain MQL5 code presented as guidance. **None of it compiles as MQL5.** The
defects below are concrete and verifiable, and they are the reason those documents are treated
as statements of intent rather than as reference implementation.

| # | Found in | Defect | Correct form |
|---|----------|--------|--------------|
| 1 | D1, D2, D3 | `double ma = iMA(...)` — treats indicator functions as returning values. This is MQL4 style. | `int h = iMA(...); CopyBuffer(h, 0, shift, n, buf);` (§1.1) |
| 2 | D1 | `TimeCurrent().hour` — `datetime` is not a struct in MQL5 | `MqlDateTime t; TimeToStruct(TimeCurrent(), t); t.hour;` |
| 3 | D2 | `trade.LastError()` — no such method on `CTrade` | `trade.ResultRetcode()` / `ResultRetcodeDescription()` (§1.11) |
| 4 | D3 | `PositionCalcLot()` — no such MQL5 function | `OrderCalcProfit` / `OrderCalcMargin` plus explicit tick-value arithmetic |
| 5 | D3 | `OrderSend(..., lot, SYMBOL_BID, SL, TP, ...)` — passes a property enum where a price is required; also the wrong `OrderSend` signature (MQL5 takes `MqlTradeRequest` / `MqlTradeResult`) | `MqlTradeRequest req; ... OrderSend(req, res);` |
| 6 | D1, D2 | `extern` for EA inputs | `input` (`extern` is MQL4) |
| 7 | D2 | `SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE)` described as "pipValue per point" | Tick value is per **tick**, not per point, and tick size ≠ point |
| 8 | D2 | `lots = MathFloor(lots/step)*step` with no `NormalizeDouble` | Floating-point residue can produce a volume the server rejects; normalise to the step's precision |
| 9 | D1, D2 | `iATR/iRSI` value semantics, and indicator handles created inside `OnTick` | Create handles at init; leak otherwise (IB-8) |
| 10 | D1, D2, D3 | Signal decisions taken on every tick | Bar-close decisioning (ADR-0002) |
| 11 | D2 | `signalTrend + signalMR` — summing opposing strategies | Silent cancellation; destroys attribution (conflict C12 in [`00`](00-consolidated-understanding.md)) |
| 12 | D2 | `static double todayPL = 0;` with a comment that it should be computed later | A static that is never updated: the daily loss limit never triggers. A limit that silently does nothing is worse than no limit |
| 13 | D1, D2 | Order placed with no check that the returned retcode indicates a fill | Never assume success (execution state machine, [`03`](03-module-specifications.md) §11) |
| 14 | D2 | Uses `SYMBOL_BID`/`SYMBOL_ASK` for both entry price and SL/TP reference without accounting for spread direction | Longs enter at ask and stop at bid; conflating them mis-states risk by the spread |

Defect 12 is the most instructive. It is not a typo — it is a risk control that *appears* to
exist, passes casual review, and does nothing. That is exactly the class of failure the
architecture in [`03`](03-module-specifications.md) is designed to prevent, and it is why every
risk check has a mandatory test that *trips* it (G2.4). A limit without a test proving it can
fire is decoration.

---

## 1.14 Account access: there is no MT5 "API key"

MetaTrader 5 has no API-key model. Account access is a **terminal login**: account number,
password, and broker server name, with an optional read-only *investor password*. The MQL5
Python integration exposes a `login()` function taking those account parameters — not a token.

The Python package obtains data "via interprocessor communication **directly from the
MetaTrader 5 terminal**", i.e. it requires a MetaTrader 5 terminal installed, running, and
logged in **on the same machine**. It is a client for a local terminal, not a remote API client.
Source: [MQL5 Reference — MetaTrader for Python](https://www.mql5.com/en/docs/python_metatrader5)

*Measured in this build environment (2026-08-18):* Linux x86_64, no terminal present, and
`pip install MetaTrader5` resolves to **no matching distribution**. The package cannot be
installed here at all.

### Consequence for how this project is operated

Credentials must **not** be pasted into a session transcript, and would be useless here if they
were. The correct division of labour:

- **The operator's machine** runs the terminal, the Strategy Tester, and the demo account.
- **This environment** produces the source, the harness, and the analysis.
- **The interface between them is data, not access** — journals and CSV exports move in;
  code and configuration move out.

What is genuinely needed from the operator's terminal is a set of **non-secret environment
facts**, produced by scripts this project supplies and resolving open items V-5 to V-7 below:

| Script (stage) | Produces | Resolves |
|---|---|---|
| `ExportSymbolSpecs.mq5` (S1) | Per-symbol volume min/max/step/limit, tick size, tick value, contract size, digits, stops level, freeze level, margin rates, swap rates | Sizing golden table; `SelfTest` fixtures; V-6 |
| `ExportTickStats.mq5` (S1) | Real-tick history depth and spread distribution per symbol | Backtest modelling strategy; cost tolerance baseline; V-5 |
| Account properties dump (S1) | `ACCOUNT_MARGIN_MODE` (hedging vs netting), account currency, leverage, broker + server name, terminal build | V-7; execution semantics; run manifest provenance |

None of these are secrets. All are recorded in the run manifest so that every result carries the
environment it was measured in.

---

# Part 3 — Open items to verify before they are relied upon

| # | Item | Needed by | Status |
|---|------|-----------|--------|
| V-1 | `OrderCalcMargin` exact signature | RiskEngine check 12 | **[UNVERIFIED]** |
| V-2 | Full trade-server retcode table and per-broker behaviour | Execution state machine | **[UNVERIFIED]** — validate empirically on the demo broker |
| V-3 | Common-folder write behaviour under parallel tester agents | Telemetry | **[UNVERIFIED]** — assumed unsafe |
| V-4 | Headless `terminal64 /config:` reliability on the target build | S3 harness | **[PARTIALLY VERIFIED]** |
| V-5 | Real-tick history depth per instrument on the target broker | Backtest design | **To be measured** (`ExportTickStats.mq5`) |
| V-6 | Triple-swap day convention on the target broker | Cost model | **To be measured** |
| V-7 | `ACCOUNT_MARGIN_MODE` on the demo account (hedging vs netting) | Execution semantics | **To be measured at init** |
| V-8 | ONNX operator coverage and type restrictions | R-401 only | **[UNVERIFIED]** |

Items marked "to be measured" are deliberately not resolved by research: they are properties of
the specific broker account, and the correct engineering response is a measurement script whose
output is recorded in the run manifest — not an assumption, however well sourced.
