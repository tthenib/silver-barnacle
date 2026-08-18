# ADR-0001 — Two-tier architecture: MQL5 executes, Python researches

Status: **accepted**  ·  Date: 2026-08-18

## Context

The system must both (a) trade realistically inside MetaTrader 5 and (b) support statistical
research MQL5 cannot perform: walk-forward orchestration, bootstrap, multiple-testing
correction, experiment tracking, sensitivity surfaces.

## Options considered

**A. Everything in MQL5.** Rejected — no statistics or plotting stack; the tester cannot
orchestrate walk-forward; experiment tracking would be hand-rolled; parallel-agent file I/O is
hostile to record-keeping.

**B. Everything in Python** (MT5 only as a data source and order router). Rejected — abandons
the tester's realistic execution simulation, broker constraint semantics, and real-tick data,
which are the platform's genuine strengths. The `MetaTrader5` Python package does not run
backtests.

**C. Strategy logic in both tiers** — fast vectorised Python for research, MQL5 for trading.
**Rejected emphatically.** This is the single most common way a research pipeline lies: two
implementations drift, and every published result then describes a system that was never traded.
The divergence is usually discovered only after months of forward testing, if at all.

**D. MQL5 owns all strategy logic; Python orchestrates and analyses.** Chosen.

## Decision

Strategy logic — features, signals, sizing, exits — exists **only** in MQL5. Python drives the
terminal, ingests journals, computes statistics, and manages experiment provenance. Python never
generates a trading result.

The single exception is *verification*: Python produces independent reference values for
features which are committed as golden vectors and asserted by the MQL5 tests. That
implementation is adversarial by design and never produces a reported number.

## Consequences

**Positive.** Backtest and live run identical code, so backtest/live divergence from dual
implementations is designed out rather than managed (UB-7). Research iteration is fast where it
needs to be. The tester's execution realism is retained.

**Negative.** Research iteration requires a tester round-trip, which is slower than vectorised
Python. Headless orchestration depends on terminal CLI behaviour that varies by build
(mitigated by the semi-automated fallback). MQL5 is a worse language for numerical work than
Python, so feature implementations need the golden-vector cross-check to be trustworthy.

The negatives are accepted because they cost time, whereas option C costs correctness.
