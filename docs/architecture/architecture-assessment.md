# Architecture Assessment and Gap Analysis

**Status:** current as of the initial platform implementation.
**Inputs reviewed:** `docs/specification/institutional-blueprint.md` (v1.0),
`docs/specification/architecture-outline.md`, `docs/specification/research-notes.md`,
and the original generation prompt supplied with the specification bundle.

This document records the repository analysis, architecture validation, and gap
analysis that the engineering directive requires before implementation, together
with the decisions taken where the specification was challenged. Each challenge
follows the required structure: problem, reason, evidence, tradeoffs,
recommendation, expected benefits, risks.

## 1. Repository analysis

The repository was empty apart from a placeholder README. The uploaded
specification bundle contained five documents. Findings:

| Document | Disposition |
|---|---|
| Institutional Blueprint (601 lines) | Authoritative specification. Committed to `docs/specification/institutional-blueprint.md`. |
| Architecture outline | Condensed, consistent restatement of the blueprint. Committed alongside it. |
| Research notes | Provider findings (EDGAR rate guidance, FRED/ALFRED vintages, Robinhood Agentic constraints). Committed. |
| `SKILL.md` (automation-and-scheduling) | **Not a platform document.** It is an internal skill file from the "Manus" tool that authored the specification, concerning that tool's own scheduling products. Excluded from the repository. |
| `tighten_specification.py` | A one-off editing script used to produce the blueprint text; references a `/home/ubuntu` path from the authoring environment. Not a platform component. Excluded. |

No inconsistencies were found *between* the blueprint and the outline; the
outline is a faithful summary. The inconsistencies worth recording are internal
to the blueprint and are addressed in section 3.

## 2. Architecture validation

The blueprint's plane separation (control / data / research / decision /
execution / observability / learning) is sound and was preserved. Its strongest
ideas — and the ones the implementation treats as non-negotiable invariants —
are:

1. **Deterministic authority, generative proposal.** Codified by making the
   agent layer emit `ResearchClaim`s only, and the execution gateway the sole
   broker caller.
2. **Fail closed.** Ambiguity (stale snapshots, unknown capabilities, lost
   broker responses) becomes a blocked state, never a retry or a guess.
3. **Policy as data.** Risk limits, execution policy, cost assumptions, and
   broker allowlists are versioned YAML validated into frozen models.
4. **Point-in-time discipline.** The data store's as-of contract makes
   look-ahead a type-level impossibility rather than a review checklist item.
5. **Evidence gates on lifecycle transitions.** Strategy promotion requires an
   evidence artifact reference; approvals bind to intent fingerprints.

## 3. Challenged specification items

### 3.1 Repository layout: ~25 top-level directories

- **Problem.** The blueprint's section 3 mandates ~25 top-level directories,
  mixing Python packages (`agents/`, `risk/`), generated artifacts (`logs/`,
  `reports/`), and infrastructure (`compose/`, `pipelines/`).
- **Reason to challenge.** Top-level Python packages without a namespace root
  invite import collisions and blur the boundary between versioned code,
  configuration, and runtime output. The blueprint itself prohibits committing
  runtime state, yet reserves committed directories for it.
- **Evidence.** Python packaging guidance (src-layout) and the blueprint's own
  rule that "runtime state, credentials, raw records, and generated reports
  must not be committed."
- **Tradeoffs.** Deviating from the literal layout costs one indirection
  (`src/quant_platform/…`) but gains import hygiene, a single installable
  package, and a clean separation of code from policy (`config/`) and docs.
- **Recommendation (adopted).** src-layout with domain subpackages mirroring
  the blueprint's ownership table; `logs/`, `reports/`, and state directories
  exist only in `.gitignore`. Recorded as ADR-0001.
- **Benefits.** Installable, type-checkable package; no accidental imports of
  generated artifacts. **Risks.** None material; the blueprint's ownership
  boundaries are preserved as subpackages.

### 3.2 Thirty-agent catalog as an implementation target

- **Problem.** Section 5.2 defines 30 agent roles. Implementing 30 LLM-backed
  agents before the deterministic substrate exists would invert the
  blueprint's own trust model.
- **Reason.** The blueprint states agent outputs are untrusted until
  schema-validated and that deterministic services are authoritative. The
  substrate (schemas, evaluation harness, audit, orchestration budget
  enforcement) must exist before any model is attached, or agent output cannot
  be governed.
- **Evidence.** Blueprint sections 5.1 (mandatory card elements, metrics),
  18 (prompt evaluation suites as release gates), and 22 (phase 3 places agent
  contracts before strategy/risk phases only as *contracts*).
- **Tradeoffs.** Deferring model-backed agents delays research-synthesis
  functionality; but attaching models first would produce ungoverned output
  with no evaluation harness to gate releases.
- **Recommendation (adopted).** Implement the typed contracts
  (`AgentCard`, `ResearchClaim`, `AgentOutput` with mandatory citation and
  abstention semantics), a deterministic reference agent proving the contract,
  and the evaluation harness measuring schema-valid rate, citation coverage,
  and abstention rate. The 30-role catalog becomes a registry-driven roadmap.
  Recorded as ADR-0004.

### 3.3 Robinhood Trading MCP as the initial broker

- **Problem.** The blueprint targets Robinhood Trading MCP but also requires
  runtime capability discovery, a signed allowlist, and read-only-first
  rollout; no Robinhood connector is configured in this environment (confirmed
  by the bundled research notes).
- **Reason.** Building a live adapter without the ability to exercise it would
  produce untested execution code — the single worst place for untested code.
- **Evidence.** Research notes: "The current task configuration contains no
  configured Robinhood connector." Blueprint phase 5 places the broker adapter
  after simulator-based execution is proven.
- **Recommendation (adopted).** Implement the provider-neutral
  `BrokerGateway` protocol, capability-allowlist intersection
  (`VerifiedCapabilities`), and a deterministic `SimulatedBroker` with fault
  injection (rejects, ambiguous-lost-response, ambiguous-but-filled). The
  Robinhood adapter later implements the same protocol behind the same
  allowlist. Recorded as ADR-0003.

### 3.4 Heavy infrastructure (Docker Compose, queues, databases) on day one

- **Problem.** Sections 3 and 19 imply Compose files, migrations, and durable
  queues from the start.
- **Reason.** Premature infrastructure would freeze storage schemas before the
  domain contracts stabilise, and none of the current workloads (deterministic
  simulation, tests) need external services.
- **Tradeoffs.** In-memory + JSONL storage cannot survive process crashes;
  acceptable in simulation, unacceptable later. The repository pattern keeps
  the swap cheap.
- **Recommendation (adopted).** Storage is behind narrow interfaces
  (`AuditLedger` sink, `TradeJournal` sink, `MarketDataStore`); the hash-chain
  and as-of contracts are the stable part. Postgres/object-storage backends are
  scheduled in the implementation plan before any paper-mode work. Recorded as
  ADR-0005.

## 4. Gap analysis (specification vs. current implementation)

| Blueprint area | Status | Gap and next step |
|---|---|---|
| §3 Repository structure | Adapted (ADR-0001) | — |
| §4 Contracts (`ResearchClaim`, `SignalProposal`, `OrderIntent`, `ExecutionRecord`) | Implemented; `ExecutionRecord` is represented by broker executions + audit transitions | Consolidate into a single exported record type when reporting lands |
| §5 Multi-agent architecture | Contracts + reference agent + evaluation harness | LLM binding, orchestrator budgets, debate protocol |
| §6 Operating workflow | Stages 1–12 exercised end-to-end in simulation (acceptance tests) | Stages 13–15 (continuous monitoring, post-trade attribution, learning proposals) |
| §7 Data layer | Canonical contract, validation, eligibility, point-in-time store, synthetic provider | EDGAR/FRED/Stooq adapters with rate limiting and cross-source checks; corporate-action pipeline |
| §8 Memory | Episodic journal | Semantic/market/strategy tiers, retrieval filters, retention policy |
| §9 Strategy engine | Framework + 3 families + lifecycle registry | Remaining families; strategy DSL consideration |
| §10 Portfolio | Sizing (most-conservative-bound), allocator with explanations, accounting | Correlation clustering, marginal risk contribution, rebalancing calendars |
| §11 Risk | Pre-trade engine, loss/drawdown blocks, breakers, kill switch | Intraday monitoring loop, scenario library |
| §12 Backtesting | Point-in-time engine, conservative costs, walk-forward with decay reporting | Monte Carlo paths, benchmark-relative attribution, experiment registry persistence |
| §13 ML guardrails | Not started (deliberately; no ML models exist yet) | Model cards, drift monitoring — blocked on real data |
| §14 Learning | Not started | Blocked on post-trade attribution |
| §15 Dashboard | Not started | Blocked on API layer; metrics registry provides the data source |
| §16 Observability | Structured logs w/ redaction, audit ledger, metrics registry | Tracing, alert routing |
| §17 Security | Secret redaction, placeholder-only `.env.example`, no credentials anywhere | Secret store integration, SBOM, dependency scanning in CI |
| §18 Testing | 76 tests incl. failure-path acceptance tests; CI gates | Property-based tests for the state machine; performance tests |
| §19 Deployment | CI workflow | Containers and staging — deferred with ADR-0005 |
| §22 Gates | Simulation-phase evidence accumulating in-repo | Go-live gates intentionally out of reach |

## 5. Standing risks and assumptions

- Synthetic data validates mechanics only; **no result in this repository is
  market evidence**, and every backtest report carries that warning.
- Sharpe and drawdown statistics on short windows are noisy; the walk-forward
  runner reports objective decay and selection instability rather than hiding
  them (the current demo run shows decay **+0.56** and unstable selection —
  correctly flagged, and exactly why promotion gates exist).
- The eligibility ceiling for all current data is `VALID_FOR_BACKTEST`;
  `VALID_FOR_LIVE` requires cross-source verification that no current provider
  supports. This is enforced in code, not convention.
