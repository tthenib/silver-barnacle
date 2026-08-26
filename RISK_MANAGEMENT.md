# RISK_MANAGEMENT.md — Risk Engine Design

**Status:** Policy set. Limits chosen before any backtest, deliberately.
**Last updated:** 2026-08-26
**Companion documents:** [ARCHITECTURE.md](ARCHITECTURE.md) §4.4–4.5 · [STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §5

---

## 1. Position, stated first

Risk management is not a safety wrapper around the strategy. **On the numbers in
[`results/return_target_feasibility.md`](results/return_target_feasibility.md), it is the larger
half of the expected value.** A strategy with a true Sharpe of 0.5 is capped at 13.3% CAGR at
*any* leverage; the difference between capturing that and blowing up is entirely a risk-engine
question, not a signal question.

Every limit in this document was chosen from risk tolerance **before** running a backtest and is
**never optimised against historical results.** Tuning a drawdown limit on historical data is
curve-fitting wearing a high-visibility vest.

---

## 2. A conflict in the brief, resolved

The brief asks for both **fixed-fractional 1–2% per-trade risk** and **volatility targeting**.
These are different risk frameworks and at a trend-following stop width they are not compatible.
Making the choice explicit avoids building a system that silently does neither.

From [`results/lot_granularity.md`](results/lot_granularity.md), using V1's parameters
(15% annualised volatility target, 4 × ATR stop, BTC at 3% daily ATR):

> Per-trade stop risk lands at **2.8%–3.6% of equity** across every account size and broker
> granularity tested.

That is not a bug. It is arithmetic: **if you target portfolio volatility and your stop is wide,
per-trade stop risk is an *output*, not an input.** To force per-trade risk down to 1% with a
4 × ATR stop you would need a ~4% volatility target — too low to be worth trading — or a ~1.1 ×
ATR stop, which whipsaws out of every trend the strategy exists to capture.

**Resolution — volatility targeting is primary:**

1. **Volatility targeting sets the size.** It controls the equity path, which is what actually
   determines survival and compounding.
2. **Per-trade stop risk is a derived quantity, and it is capped.** If the derived stop risk
   exceeds `max_trade_risk` (V1: **4.0%**), size is cut until it complies. The cap binds
   downward only.
3. **The 1–2% convention is retained as a *diagnostic*, not a control.** It is logged every
   trade. Sustained breaches mean the volatility target is too high for the stop width, and the
   correct response is to lower the volatility target — not to tighten the stop, which would
   change the strategy to satisfy an accounting convention.

---

## 3. The risk budget hierarchy

Five nested layers. An order must clear **all** of them. Each names the limit that bound, and
that name goes in the log — so every rejection is attributable.

```
  ┌─ L5  KILL SWITCH ──────────── peak-to-trough -30%  → flatten, halt, human only
  │  ┌─ L4  PORTFOLIO ─────────── peak DD -20%         → no new entries
  │  │  ┌─ L3  PERIODIC ───────── daily -4% / weekly -8% → no new entries
  │  │  │  ┌─ L2  EXPOSURE ────── gross ≤ 1.0x equity, ≤ 2 positions
  │  │  │  │  ┌─ L1  PER TRADE ── vol-targeted size, stop risk ≤ 4%
```

| Layer | Limit (V1) | Action | Reset |
|---|---|---|---|
| **L1** per trade | Vol-targeted size; derived stop risk ≤ 4% of equity | Reduce size; reject if minimum legal lot still breaches | n/a |
| **L2** exposure | Gross notional ≤ 1.0 × equity; ≤ 2 open positions; ≤ 1.0 × equity aggregate crypto | Reduce, then reject | n/a |
| **L3** periodic | Daily −4%, weekly −8% of period-start equity | Block **new entries**; existing positions managed normally | Daily 00:00 UTC; weekly Monday 00:00 UTC |
| **L4** portfolio | Peak-to-trough equity −20% | Block new entries; halve volatility target on recovery | Manual, after review |
| **L5** kill switch | Peak-to-trough equity −30% | **Flatten all, halt** | **Human acknowledgement only** |

**Design choices worth defending:**

- **L3 and L4 block entries rather than force-liquidating.** Forced liquidation at a drawdown
  trough is how a recoverable drawdown becomes a permanent loss — you sell the bottom and are
  flat for the recovery. Only L5 liquidates, and L5 is set where the strategy is presumed broken
  rather than merely losing.
- **L5 requires a human.** Automatic restart after an unexplained kill is how a small problem
  becomes an account. Safe mode is never exited automatically
  ([ARCHITECTURE.md](ARCHITECTURE.md) §5.3).
- **Limits are calendar-anchored to UTC**, not broker server time, and the offset is logged.
  A 24/7 market has no natural day boundary; the choice must be explicit and consistent between
  research and production.

---

## 4. Position sizing

### 4.1 The formula

```
                    equity × target_vol × vol_scalar
  ideal_notional = ─────────────────────────────────
                        max(σ_forecast, σ_floor)

  ideal_lots     = ideal_notional / (price × contract_size)

  lots           = clamp_to_broker(floor_to_step(ideal_lots))

  stop_risk      = lots × contract_size × stop_distance / equity
  if stop_risk > max_trade_risk:  scale lots down and re-round
```

| Symbol | V1 value | Type |
|---|---|---|
| `target_vol` | 15% annualised | **Policy choice.** Not fitted |
| `σ_forecast` | 30-day realised vol of daily log returns, annualised | Convention |
| `σ_floor` | 20% annualised | **Safety.** Prevents unbounded size in quiet regimes |
| `vol_scalar` | continuous, from regime module, ∈ [0.25, 1.0] | Continuous — no threshold to overfit |
| `stop_distance` | 4 × ATR(14) | Design choice; plateau-tested (EXP-0008) |
| `max_trade_risk` | 4.0% of equity | **Cap, binds downward only** |
| gross cap | 1.0 × equity | **Hard.** Binds regardless of the vol estimate |

### 4.2 Why `σ_floor` exists

Without it, sizing is `1/σ` and unbounded as σ → 0. Quiet regimes precede volatile ones (that is
what clustering *means*), so an uncapped inverse-vol rule takes its largest position immediately
before the regime that punishes it. The floor and the gross cap are two independent brakes on
the same failure, deliberately redundant.

### 4.3 Asymmetric volatility response

`σ_forecast` uses the **maximum** of a fast (10-day) and slow (30-day) estimate. Risk therefore
falls quickly when volatility rises and rises slowly when it falls. This is deliberately
suboptimal in expectation and deliberately safer in the tail: the cost is a small drag in calm
markets, the benefit is not being maximally sized into a volatility jump.

### 4.4 Gap risk — the stop is not a guarantee

Crypto gaps through stops. Broker maintenance windows, flash moves and liquidation cascades all
produce fills materially worse than the stop price. The nominal risk figure is therefore a
**lower bound** on the loss.

**Rules:**
- Size assuming realised loss can be **1.5 × nominal** on a stopped trade.
- Measure the realised-vs-nominal slippage distribution in backtest and live, and report it
  as a first-class metric rather than an anecdote.
- Never treat `max_trade_risk` as a guarantee in any communication about this system.

### 4.5 Broker constraints

All applied inside the sizer ([ARCHITECTURE.md](ARCHITECTURE.md) §4.4), all queried at runtime,
none hardcoded: `min_lot`, `lot_step`, `max_lot`, `contract_size`, `tick_value`, `tick_size`,
`stops_level`, `freeze_level`, `margin_required`, account leverage and currency.

**Rounding is always down.** Rounding up to reach a "nicer" lot silently exceeds the risk budget.

**If the minimum legal lot already breaches the budget, the correct output is `lots = 0`.**
This is a normal outcome on a small account, not an error, and it must be logged as
`REJECT: min_lot_exceeds_budget` rather than swallowed.

### 4.6 Lot granularity is a deployment blocker, not a detail

From [`results/lot_granularity.md`](results/lot_granularity.md): a ~$2,500 account on a coarse
broker (min lot 0.01 BTC = $600 notional) runs a **−21% quantisation error** against the size
volatility targeting asks for. The live system is then not running the strategy that was
validated, and the gap is permanent and uncompensated.

**Required before deployment:** query the actual symbol specs from the intended broker, re-run
the script, and confirm quantisation error stays within ±25%. If it does not, the options are a
finer-granularity symbol, a different broker, or a larger account. **Changing the strategy to
fit the lot size is the wrong answer** and must be recorded as a deviation if it happens.

---

## 5. Position sizing models — comparison (Phase 7)

| Model | Verdict | Reasoning |
|---|---|---|
| **Fixed lot** | ❌ Rejected | The same lot is a wholly different bet at 25% vs 120% vol. Indefensible in crypto |
| **Fixed % risk (1–2%)** | ⚠️ Diagnostic only | Controls per-trade loss, not portfolio volatility. Conflicts with wide trend stops (§2) |
| **ATR-based sizing** | ✅ Component | ATR sets the stop distance; a scaled version of vol targeting |
| **Volatility targeting** | ✅ **Primary** | Controls the quantity that actually governs survival and compounding |
| **Kelly / fractional Kelly** | ⚠️ Upper bound only | See §6 |

### 6. On Kelly

Full Kelly maximises expected log growth at `σ = S`, i.e. **annualised volatility equal to the
Sharpe ratio**. For a Sharpe-1.0 strategy that is 100% annualised volatility, which
[`results/return_target_feasibility.md`](results/return_target_feasibility.md) shows carries a
median 5-year maximum drawdown above 50% and a ~10–18% chance of exceeding 70%.

Three reasons full Kelly is never implemented here:

1. **It assumes the true Sharpe is known.** Ours has a 5-year standard error of ≈ 0.55. Kelly
   sized on an *estimated* Sharpe that is overstated by one standard error is severely
   over-levered, and the penalty is asymmetric — over-betting past the optimum destroys growth
   while continuing to add drawdown.
2. **It assumes returns are well-behaved.** Crypto returns are fat-tailed and volatility-clustered;
   the GARCH rows in the feasibility results show 95th-percentile drawdown rising from 75% to
   90% at the same Sharpe.
3. **It optimises for a quantity nobody actually has** — infinite-horizon log wealth, with
   perfect knowledge and no career, funding, or psychological constraint.

**Use:** Kelly is computed and **logged as a diagnostic upper bound only.** V1's 15% volatility
target sits far below quarter-Kelly for any plausible Sharpe, and that is intentional.
If we ever propose raising the target, the Kelly diagnostic is the reference against which the
proposal is argued — never the justification on its own.

---

## 7. Prohibited by design

Enforced by the risk engine's `approved_lots <= requested_lots` invariant
([ARCHITECTURE.md](ARCHITECTURE.md) §4.5), by property-based tests, and by review.

| Prohibited | Failure it prevents |
|---|---|
| **Martingale / averaging down** | Smooth equity curve for years, then the account in one event |
| **Grid without a stop** | Same failure, more code |
| **Increasing size against an open loss** | Any variant of the above |
| **Widening or removing a stop on a losing position** | Converts a bounded loss to an unbounded one |
| **Increasing risk because the backtest improved** | Backtest-driven risk escalation is the mechanism by which overfitting becomes ruin |
| **Recovery/revenge sizing after a loss** | Correlates position size with recent losses — exactly backwards |

---

## 8. Dynamic risk scaling

The brief proposes 100% / reduced / zero by regime. V1 implements the **continuous** analogue,
because discrete thresholds are fitted parameters and cliff edges
([RESEARCH.md](RESEARCH.md) §3.6):

| Condition | `vol_scalar` | Mechanism |
|---|---|---|
| Normal | 1.0 | Full target volatility |
| Elevated realised vol | continuous decay toward 0.25 | Inverse-vol sizing does this automatically |
| Realised vol > 95th percentile | entry blocked | Binary circuit breaker (safety, not alpha) |
| Spread > 3 × median | entry blocked | Cost control, measurable directly |
| After L4 (−20% DD) | 0.5 × target on recovery | Halved until reviewed |
| After L5 (−30% DD) | 0.0 | Halted, human only |

**Every breaker's historical trigger frequency and P&L cost is measured and reported before it
ships** (EXP-0005). A breaker is *insurance with a premium*; shipping one without knowing the
premium is not risk management, it is superstition.

---

## 9. Correlated exposure

BTC/ETH daily correlation runs 0.7–0.9 and converges toward 1.0 in stress — precisely when
diversification is needed ([RESEARCH.md](RESEARCH.md) §2.1).

**V1.1 rule when a second symbol is added:** cap **aggregate crypto notional** at 1.0 × equity,
not per-symbol. Two correlated positions at full size is one position at 2× size, and treating
them as independent is the standard way a "diversified" crypto book turns out to have been a
single leveraged BTC bet.

**No correlation optimiser.** Estimated correlation matrices are unstable at our sample sizes,
and optimising against them imports estimation error as if it were signal. A fixed aggregate cap
is worse in theory and better in practice.

---

## 10. Execution-related protections

| Protection | Rule |
|---|---|
| Spread gate | Block entry if spread > 3 × trailing median. Exits are **never** blocked |
| Slippage guard | Reject fills worse than a threshold; log and skip rather than chase |
| Requote handling | Re-validate the signal is still current, then retry ≤ 3 with fresh price |
| Invalid stop | Widen to broker minimum; **if that breaches the risk budget, cancel the trade** |
| Duplicate guard | Deterministic idempotency key `(magic, symbol, signal_bar_ts)` checked before send |
| Connection loss | **Never blind-resend.** Reconcile on next cycle via the idempotency key |
| Restart | Reconcile positions against persisted intent; any mismatch → safe mode |
| Stale data | If the latest bar is older than N × timeframe, do not trade |

Note the asymmetry throughout: **gates block entries, never exits.** A system that can enter but
not exit is strictly more dangerous than one that misses an entry.

---

## 11. What these limits are expected to cost

Stated in advance, so the eventual measurement is informative rather than post-rationalised:

- The circuit breakers will occasionally halt trading immediately before a recovery. This is a
  real cost, it will be visible in the results, and it is accepted.
- The spread gate will exclude some genuine breakout entries ([STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §#5).
- The volatility floor will undersize in genuinely calm, genuinely trending periods.
- Asymmetric volatility response costs a small drag in calm markets.

**Estimated total drag: 1–3% annualised.** If measurement shows materially more, the limits are
revisited *as a policy decision with the cost stated* — not quietly loosened because the
backtest would look better without them.
