# ADR-0002 — Signal decisions on bar close only

Status: **accepted**  ·  Date: 2026-08-18

## Context

All three source documents evaluate signals inside `OnTick`. This is conventional in retail EA
code and it is a mistake for a research system.

## Problem with per-tick decisions

1. **Non-deterministic.** Results depend on which ticks arrive, which differs between tester
   modelling modes and between backtest and live. R1 (determinism) becomes unachievable.
2. **Look-ahead becomes easy and invisible.** The forming bar's values change continuously;
   reading them is trivially done by accident and produces excellent, wrong backtests (IB-1).
3. **Untestable.** A per-tick decision cannot be reproduced from a fixture without reproducing
   the exact tick stream.
4. **Modelling-mode sensitivity.** Identical logic produces different results under "every tick"
   versus "1 minute OHLC", so the strategy's measured performance becomes partly a property of
   the tester configuration.

## Decision

- **Signal decisions occur only on the close of a completed bar.** Features derive exclusively
  from bars at index ≥ 1.
- **Execution management runs per tick**: stop and freeze-level checks, trailing-stop
  maintenance, spread guards, circuit breakers.
- **Bar-0 access is confined to `Data/BarProvider.mqh`** and enforced by the invariant linter
  (I2).

## Consequences

**Positive.** Deterministic and reproducible; look-ahead structurally prevented in one auditable
place; identical behaviour across modelling modes; fixtures are simple bar arrays; far less CPU
per tick.

**Negative.** Cannot express genuinely intrabar strategies. Entry occurs at the next bar's open
rather than at the signal price, which is a real cost — but it is also *honest*, since assuming a
fill at the signal bar's close is itself a mild look-ahead.

The excluded strategy class (intrabar) is not one this project intends to pursue, so the cost is
theoretical while the benefit is immediate.
