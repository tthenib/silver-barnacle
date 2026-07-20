# Implementation Plan

Phases follow specification section 22. Each phase has acceptance evidence;
work in a later phase must not begin until the previous phase's evidence
exists (tests, reports, or ADRs referenced from the PR that closes the phase).

## Phase status

| Phase | Blueprint scope | Status |
|---|---|---|
| 1 | Repo structure, config, canonical schemas, audit ledger, secret handling, simulator, observability | **Done** — this repository |
| 2 | Source adapters, validation, data catalog, reproducible backtest foundations | **Partial** — validation, catalog, backtesting done on synthetic data; real adapters pending |
| 3 | Research workflow, agent contracts, evidence memory, evaluation harnesses | **Partial** — contracts, reference agent, harness, episodic journal done; LLM binding and orchestration pending |
| 4 | Strategies, walk-forward, stress testing, portfolio, risk engine | **Mostly done** — stress-scenario library pending |
| 5 | Broker adapter read-only mode, capability discovery, reconciliation, full simulated execution | **Done in simulation** — real broker adapter deliberately absent (ADR-0003) |
| 6 | Dashboard, runbooks, staging, formal acceptance | **Started** — emergency-stop runbook only |

## Next increments, in order

1. **Real data adapters (Phase 2 completion).** Stooq end-of-day and FRED
   adapters behind `MarketDataProvider`, with on-disk raw payload cache,
   request throttling, and cross-source checks feeding the existing
   eligibility model. EDGAR client with the SEC fair-access limits from the
   research notes (≤10 req/s, descriptive user agent, cache-first).
2. **Corporate actions.** Split/dividend event records, adjustment policy
   propagation, and re-validation triggers — prerequisite for any real
   backtest being trustworthy.
3. **Durable storage (ADR-0005 follow-up).** SQLite/Postgres repositories for
   audit ledger, journal, and experiment registry behind the existing
   interfaces; restart-safety tests (kill the process mid-lifecycle, resume
   from durable state).
4. **Stress testing.** Scenario library (historical shock replays, volatility
   and liquidity shocks, correlation spikes) run against target portfolios;
   scenario results wired into the promotion gate for `STRESS_TESTED`.
5. **Monte Carlo and experiment registry.** Resampled-path robustness for
   backtests; persist every run (including failures) keyed by spec hash and
   data fingerprint.
6. **Orchestrated research workflow (Phase 3 completion).** Deterministic
   orchestrator enforcing evidence slots, iteration/time budgets, and
   abstention-on-impasse; LLM-backed agents join behind the existing
   `Agent` protocol only after the prompt evaluation corpus exists
   (specification §18: adversarial, stale, contradictory, prompt-injection
   inputs).
7. **Post-trade attribution and learning records (workflow stages 14–15).**
   Attribution against ex-ante thesis; lesson records that open tracked tasks
   and never mutate production state.
8. **API + dashboard (Phase 6).** Read-only API over journal/metrics/risk
   state first; state-changing actions require reauthentication and reason
   capture per specification §15.
9. **Broker adapter (read-only first).** Robinhood Trading MCP client
   implementing `BrokerGateway` behind capability discovery, exercised in
   read-only reconciliation mode against the Agentic account, with the
   simulator remaining the CI double. Live submission stays gated on the §22
   go-live evidence table and explicit human authorization.

## Definition of done for every increment

Tests written with the change (failure paths included), `make check` green,
documentation current (README, ADR when a decision is made, runbook when an
operational surface is added), and no widening of any risk or policy default.
