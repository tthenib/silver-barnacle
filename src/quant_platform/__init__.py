"""Research-first, evidence-gated, simulation-default quantitative trading platform.

The package is organised by domain, mirroring the plane separation in
``docs/specification/institutional-blueprint.md``:

- ``core``: cross-cutting contracts — metadata, clock, config, audit, logging.
- ``data``: provider adapters, validation, and the point-in-time data store.
- ``strategies``: pure signal logic; strategies never touch brokers or secrets.
- ``backtesting``: point-in-time, cost-aware evaluation and walk-forward testing.
- ``risk``: deterministic limits, circuit breakers, and the kill switch.
- ``portfolio``: accounting, conservative sizing, and target allocation.
- ``execution``: order intents, approvals, the execution gateway, and brokers.
- ``agents``: propose-only AI agent contracts and evaluation harness.
- ``memory``: append-only journals and durable evidence records.
- ``monitoring``: metrics registry for observability.
"""

__version__ = "0.1.0"
