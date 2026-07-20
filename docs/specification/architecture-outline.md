# Architecture Blueprint — AI-Assisted Quantitative Trading Platform

## Architectural stance

The platform is a **research-first, evidence-gated trading system**, not an autonomous profit engine. It separates data collection, feature construction, research, model inference, portfolio optimization, risk approval, broker execution, surveillance, and learning into independently testable modules. Every live action is governed by explicit policies, reproducible artifacts, immutable audit records, and human-configurable approval requirements.

The initial live-execution scope is restricted to the broker capabilities that can be verified at runtime through the Robinhood Trading MCP. The broker adapter must discover its available tools and schemas at startup, run a non-mutating health check, and refuse any action outside its allowlist. Design-time material indicates that Robinhood Agentic Trading uses a dedicated Agentic account and initially supports equities; the architecture will therefore treat other asset classes, margin behavior, and advanced order features as unavailable until a capability contract confirms them.[1][2]

## Primary layers

1. **Control plane:** configuration, policy-as-data, feature flags, environment management, identity, secrets, change control, and kill switches.
2. **Data plane:** source adapters, rate limiting, validation, canonical schemas, immutable raw capture, quality scoring, revision/vintage management, caching, and cataloging.
3. **Research plane:** reproducible notebooks/workspaces, event and factor studies, agent outputs as cited hypotheses, experiment registry, and curated research memory.
4. **Decision plane:** strategy registry, signal generation, cross-agent debate, portfolio construction, deterministic risk controls, approval workflows, and a final decision record.
5. **Execution plane:** order-intent validation, broker adapter, idempotency, state reconciliation, execution-quality measurement, and emergency stop paths.
6. **Observability plane:** structured logs, traces, metrics, alerts, dashboards, evidence bundles, incident records, and immutable audit retention.
7. **Learning plane:** post-trade attribution, drift monitoring, strategy scorecards, lesson extraction, engineering task proposals, and controlled promotion. It may propose but never modify production configurations, code, prompts, or risk limits automatically.

## Trust zones and state

Data enters as untrusted and is quarantined until validated. Research outputs, LLM claims, and external news are hypotheses with citations, confidence, timestamps, and expiry. A signal becomes a trade candidate only after all tests and policy gates pass. A trade candidate becomes an order intent only after independent risk, compliance, portfolio, and human approval conditions are met. An order intent becomes an execution request only through the broker adapter. No agent can mutate broker state directly.

The canonical lifecycle is: `COLLECTED → VALIDATED → RESEARCHED → PROPOSED → BACKTESTED → TESTED → RISK_REVIEWED → APPROVED/REJECTED → SUBMITTED → ACKNOWLEDGED → FILLED/CANCELLED/REJECTED → RECONCILED → REVIEWED → LEARNED`. Every transition has an actor identity, timestamp, correlation ID, input hashes, policy version, and an explicit reason.

## Governance and human control

Human approval is required by default for any live order, material strategy promotion, risk-limit increase, broker connector change, model/prompt deployment, credential rotation, and production data-source change. A narrowly-scoped autopilot option may be enabled only with an approved policy profile, maximum capital allocation, permitted symbol universe, order-type allowlist, hard daily/weekly loss caps, circuit breakers, documented owner, and an automatic reversion-to-approval condition. The default policy is simulation-only.

The Final Decision agent may issue one of three statuses: `REJECT`, `RESEARCH_ONLY`, or `PROPOSE_FOR_APPROVAL`; it may not issue a broker call. The Execution agent may only translate a signed approved order intent into a broker request after a final fresh-account, fresh-position, market-hours, risk, and idempotency check.

## Data and research choices

Use source adapters behind a canonical data contract. Prefer official/public sources for fundamentals and macro data: SEC EDGAR (subject to fair-access rate control), FRED/ALFRED for macro series and vintage awareness, public market feeds for low-cost prototyping, and OpenBB as an optional connector normalization layer rather than a source of truth.[4][5][6] Treat free or unofficial price feeds as unsuitable for assumptions of exchange-grade real-time accuracy. Compare each critical field against an independent source where available, track staleness and provider provenance, and suppress live decisions when required data quality thresholds fail.

## Agent operating model

The agent ensemble is organized into four rings. Analytical agents produce cited, time-bounded assessments. Challenge agents produce independent objections and alternative explanations. Control agents assess risk, compliance, sizing, and execution feasibility. Orchestrating agents synthesize evidence without overriding deterministic policies. Each agent has a constrained input contract, read-only scope by default, output schema, quality metrics, declared uncertainty, and retention policy.

## Deployment model

Local development and CI use synthetic data and a simulator. A staging environment uses paper/sandbox brokerage behavior where available and controlled replay scenarios. Production uses isolated service identities, immutable versioned artifacts, encrypted state, centralized observability, separate broker credentials, and manual go-live promotion. Workload scheduling should separate high-frequency deterministic ingestion from lower-frequency AI analysis; background workers must be durable, idempotent, and independently monitored.

## Acceptance conditions for the final specification

The specification must document all requested repositories, agents, workflows, data sources, memory design, strategy and risk frameworks, backtesting and ML controls, dashboard, logging, security, testing, deployment, documentation, and future extensibility. It must include deployment gates, clear limitations, visible no-guarantee language, and authoritative source citations.

## References

[1] Robinhood, “Agentic Trading overview,” https://robinhood.com/us/en/support/articles/agentic-trading-overview/
[2] Robinhood, “Robinhood is Now Open to Agents,” https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/
[4] U.S. Securities and Exchange Commission, “Developer Resources,” https://www.sec.gov/about/developer-resources
[5] Federal Reserve Bank of St. Louis, “FRED API Overview,” https://fred.stlouisfed.org/docs/api/fred/overview.html
[6] OpenBB, “Providers,” https://docs.openbb.co/odp/python/extensions/providers
