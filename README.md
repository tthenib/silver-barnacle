# silver-barnacle

A MetaTrader 5 / MQL5 **quantitative trading research and paper-trading system**.

Starting capital: **£100,000, demo/paper only.**

---

## What this project is

An apparatus for answering one question honestly:

> Does a systematic trading strategy with genuinely positive out-of-sample expectancy exist,
> for a retail account, on this broker's instruments, after realistic transaction costs?

The deliverable is **the apparatus and the verdict** — not a profitable bot.

A well-built apparatus that returns *"no detectable edge"* has succeeded. An apparatus that
returns *"large edge found"* and is wrong has failed badly, because it will be believed.

The system is therefore optimised for the **reliability of its own conclusions** before
anything else.

### What it is not

- Not a live-money trading system. No real-capital path is built; the EA refuses to initialise
  on a non-demo account.
- Not driven by return targets. No CAGR or profit figure appears anywhere as a design input.
- Not a strategy collection. Complexity must earn its place through evidence.

There is no guaranteed profitable trading strategy, and nothing here claims otherwise.

---

## Current status

**Architecture and planning complete. No implementation code yet — by design.**

| Stage | Description | Status |
|-------|-------------|--------|
| — | Architecture, conflict resolution, planning | ✅ complete |
| S0 | Scaffolding: core types, config, logging, test framework, tooling | ⬜ next |
| S1 | Risk and execution spine (proven with *injected* signals, no alpha) | ⬜ |
| S2 | Baseline strategy + full telemetry | ⬜ |
| S3 | Research harness (Python): registry, tester driver, metrics | ⬜ |
| S4 | Validation machinery: walk-forward, Monte Carlo, deflated Sharpe | ⬜ |
| S5 | Demo forward testing | ⬜ |
| S6+ | Gated on evidence — see the roadmap | 🔒 locked |

---

## Documentation

Read in this order:

| # | Document | Contents |
|---|----------|----------|
| 00 | [Consolidated understanding](docs/00-consolidated-understanding.md) | Source reconciliation, **13 contradictions resolved**, the statistical constraint that shapes everything |
| 01 | [Architecture](docs/01-architecture.md) | Two-tier design, structural invariants, state and restart model |
| 02 | [Repository layout](docs/02-repository-layout.md) | Directory and file structure |
| 03 | [Module specifications](docs/03-module-specifications.md) | Every module: responsibility, must-nots, interfaces, tests |
| 04 | [Build order](docs/04-build-order.md) | What to build first — and **what must not be built yet, with reasons** |
| 05 | [Testing and validation](docs/05-testing-and-validation.md) | Software testing, statistical validation, the gate system |
| 06 | [Baseline strategy](docs/06-baseline-strategy.md) | The minimum viable strategy, and why it is a *test of the test harness* |
| 07 | [Research roadmap](docs/07-research-roadmap.md) | Advanced work, each with preconditions and a removal criterion |
| 08 | [Acceptance criteria](docs/08-acceptance-criteria.md) | Numeric, pre-committed pass/fail thresholds for all 8 gates |
| 09 | [Risk register](docs/09-risk-register.md) | Overfitting, false discovery, implementation bugs, unrealistic backtests |
| 10 | [MT5 platform notes](docs/10-mt5-platform-notes.md) | Verified MQL5 facts, and 14 defects found in the source documents' code |

Architecture decisions: [`docs/adr/`](docs/adr/)

---

## The five decisions that shape everything else

**1 · Two tiers, one source of truth.**
MQL5 executes and owns *all* strategy logic. Python orchestrates, ingests and analyses — and
never re-implements a signal. Dual implementations that quietly diverge are the most common way
a research pipeline lies to its owner, so the possibility is designed out.
→ [ADR-0001](docs/adr/ADR-0001-two-tier-research-architecture.md)

**2 · Ten years of data cannot prove a Sharpe of 0.5.**
`SE(SR) ≈ sqrt((1 + SR²/2)/T)` gives a 95% CI of roughly `[-0.16, 1.16]` — indistinguishable
from zero. This single fact drives the instrument panel, the shared-parameter rule, mandatory
trial counting, and the expectation that "no edge found" is the most likely honest outcome.
→ [00 §5](docs/00-consolidated-understanding.md)

**3 · Risk before alpha.**
The risk and execution spine is built and proven *first*, with deliberately stupid injected
signals. A strategy arrives into a system that already constrains it, rather than having
constraints bolted on afterwards.
→ [04](docs/04-build-order.md)

**4 · The risk engine cannot be bypassed — structurally.**
`<Trade/Trade.mqh>` may be included by exactly one file. Strategies emit opinions, never orders.
Enforced by a CI linter, not by convention. Every risk limit has a mandatory test that *fires*
it, because a limit nobody has seen trigger is decoration.
→ [ADR-0004](docs/adr/ADR-0004-risk-engine-as-sole-order-gateway.md)

**5 · The harness must fail on noise.**
A seeded random walk is fed through the entire validation pipeline as a permanent regression
test. If it passes any gate, the harness is broken and every result it ever produced is void.
→ [05 §1.5](docs/05-testing-and-validation.md)

---

## Source documents

Three research PDFs were provided and reconciled under the priority
**revised spec > research foundation > original spec**. Thirteen contradictions were identified
and resolved in [00](docs/00-consolidated-understanding.md), including the capital figure (now
£100,000 per the current instruction, superseding both the £20 and £2,000 in the documents), return targets (removed), fixed reward:risk ratios (rejected), and signal summation
(rejected).

Two caveats apply to all three documents and are carried throughout:

- Their citation markers are retrieval artefacts, not resolvable references. **Every numeric
  performance claim in them is treated as a hypothesis to test, never as evidence, and never as
  a target.**
- Their MQL5 code does not compile — 14 specific defects are catalogued in
  [10](docs/10-mt5-platform-notes.md), including MQL4-style indicator calls, a non-existent
  `CTrade::LastError()`, and a daily-loss limit that can never trigger.

---

## Contributing rules

1. Every component traces to a requirement or to experimental evidence. Components that cannot
   demonstrate they improve out-of-sample performance after costs are **removed**.
2. Every experiment is pre-registered and committed **before** it runs.
3. Gate criteria are fixed before data is seen. Changing one requires an ADR stating what was
   seen and why the change is not motivated by it.
4. Negative results are written up with the same care as positive ones.
5. Every claimed MT5/MQL5 behaviour is verified against MetaQuotes documentation, or marked
   `[UNVERIFIED]`.
