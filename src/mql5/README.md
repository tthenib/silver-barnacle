# src/mql5 — the Expert Advisor

A **port** of the Python signal logic, not the source of truth.

Layout:
- `Experts/` — EA entry point. Thin: wiring only.
- `Include/CryptoEA/` — ported modules (`Core/`, `Signals/`, `Regime/`, `Risk/`,
  `Execution/`, `Logging/`, `Config/`).

No file here may ship until the parity harness
([ARCHITECTURE.md](../../ARCHITECTURE.md) §6.2) shows 100% signal-direction agreement with
the Python implementation across the full history.
