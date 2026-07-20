# Quant Platform

A research-first, evidence-gated, **simulation-default** AI-assisted quantitative
trading platform, built to the specification in
[`docs/specification/institutional-blueprint.md`](docs/specification/institutional-blueprint.md).

> **Operating boundary.** This repository is an engineering system, not investment
> advice or a claim of profitability. Every trading decision is uncertain. The
> platform requires evidence, enforces deterministic risk limits, preserves human
> oversight, and defaults to simulation. No live broker adapter exists yet, and
> live modes are unreachable until every go-live gate in the specification has
> recorded evidence.

## Core philosophy

**Automation is not authority.** AI agents may propose; only policy-governed
deterministic services approve; only the execution gateway may request broker
action — and today the only broker is a simulator.

| Guarantee | Enforced by |
|---|---|
| No look-ahead in research or backtests | `MarketDataStore.bars_as_of` serves history strictly as-of a date; signals execute at the *next* open |
| Untrusted data cannot drive decisions | `BarSeriesValidator` assigns eligibility; the store refuses data below its bar |
| No agent can trade | Agents emit `ResearchClaim`s only; the `ExecutionGateway` accepts signed intents, not agent output |
| Risk can only tighten | `RiskEngine` scales down or blocks; there is no code path that widens a limit |
| No duplicate or ambiguous orders | Intent fingerprints, broker-side idempotency keys, and `BLOCKED_PENDING_RECONCILIATION` + `Reconciler` |
| Every decision is auditable | Hash-chained append-only `AuditLedger`; tampering fails `verify_chain()` |
| Policy is data, not code | Versioned YAML in `config/` validated into frozen models; unknown keys are startup errors |

## Repository layout

```
config/                 Policy as data: risk limits, execution policy, costs, broker allowlists
docs/
  specification/        The authoritative blueprint and research notes
  architecture/         Architecture assessment, gap analysis, implementation plan
  adr/                  Architecture decision records
  runbooks/             Operational procedures (emergency stop, …)
src/quant_platform/
  core/                 Metadata, clock, config, audit ledger, structured logging, errors
  data/                 Provider adapters, validation, point-in-time store, synthetic data
  strategies/           Pure signal logic (trend, mean reversion, momentum) + lifecycle registry
  backtesting/          Point-in-time engine, conservative costs, metrics, walk-forward
  risk/                 Deterministic limit engine, circuit breakers, kill switch
  portfolio/            Accounting, conservative sizing, explainable allocation
  execution/            Order intents + state machine, approvals, gateway, simulated broker, reconciliation
  agents/               Propose-only agent contracts, deterministic reference agent, evaluation harness
  memory/               Append-only trade journal (episodic memory)
  monitoring/           Metrics registry
tests/                  Unit, integration, and full-lifecycle acceptance tests
scripts/                run_simulation.py — deterministic end-to-end demo
```

## Quick start

```bash
make install      # pip install -e ".[dev]"
make check        # ruff + mypy --strict + pytest (76 tests)
make simulate     # deterministic end-to-end lifecycle on synthetic data
```

The simulation runs: synthetic data → validation → research claims → signals →
sizing → allocation → risk review → backtest + walk-forward → signed intent →
approval → gateway preflight → simulated broker fill → reconciliation → audit
chain verification.

## Current scope and what is deliberately absent

Implemented now (specification phases 1–5, simulation only):
data plane, strategy framework, backtesting with walk-forward, deterministic
risk, portfolio construction, the full execution state machine against a
simulated broker, propose-only agent contracts, episodic journal, audit ledger.

Deliberately deferred, with rationale recorded in
[`docs/architecture/implementation-plan.md`](docs/architecture/implementation-plan.md):
real data providers, LLM-backed agents (ADR-0004), the Robinhood Trading MCP
adapter (ADR-0003), dashboard, and durable external storage (ADR-0005).

## Development standards

- Python 3.11+, `pydantic` v2 frozen models with `extra="forbid"` everywhere.
- `ruff` (lint + format) and `mypy --strict` are CI gates, as is the simulation
  smoke test.
- Commits follow `type(scope): imperative summary` (`feat`, `fix`, `test`,
  `docs`, `risk`, `security`, `data`, `strategy`, `ops`).
- Every behavioural change needs tests; risk/execution changes need failure-path
  tests, not just happy paths.
