# ROADMAP.md — Incremental Delivery Plan

**Status:** Stage 0 complete (this document set). Stage 1 not started.
**Last updated:** 2026-08-26

---

## 1. Sequencing principle

Complexity is earned, one component at a time, against a frozen baseline. The order below is
chosen so that **the experiments most likely to kill the project run first and cheapest.**

If the broker feed doesn't track the exchange (EXP-0001), if costs are double what we modelled
(EXP-0002), or if the pipeline manufactures edge from random data (EXP-0006), we want to know in
week two, not month four. Finding out early is the cheapest possible outcome.

---

## 2. Stages and gates

Each stage has an explicit gate. **A failed gate stops the stage; it does not get relaxed to let
work continue.** If a gate is ever relaxed, the relaxation and its reasoning are recorded in
[EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) so the decision is visible later.

### Stage 0 — Research and architecture ✅ COMPLETE

**Delivered:** the seven charter documents; the feasibility arithmetic
([`results/return_target_feasibility.md`](results/return_target_feasibility.md)); the lot-granularity
analysis ([`results/lot_granularity.md`](results/lot_granularity.md)); 19 pre-registered experiments.

**Gate — passed:** we can state what we expect to achieve *and why*, before writing strategy code.

---

### Stage 1 — Data pipeline and honesty infrastructure

Build: exchange data loader with a manifest and checksums; MT5 bar exporter; data quality gates;
the cost model; the metrics library (including Deflated and Probabilistic Sharpe); the results
directory structure; **the null-data generator.**

**Experiments:** EXP-0001 (feed reconciliation), EXP-0002 (cost measurement), EXP-0006
(null-pipeline control).

**Gate:**
- Broker/exchange daily return correlation > 0.98, with tracking difference not systematically
  related to volatility
- Measured costs within 1.5× of modelled
- **The null-pipeline control passes: no strategy survives acceptance on data with no edge**

> **If the null-pipeline control fails, everything stops until it passes.** A pipeline that finds
> edge in randomness invalidates every result it will ever produce.

---

### Stage 2 — Benchmarks before strategies

Build and measure **B1** (buy & hold), **B2** (vol-targeted buy & hold), **B3** (random-entry
control, 1,000 seeds).

**Deliberately before any strategy work.** Building the benchmark first removes the temptation to
define it favourably once we know what our strategy scores. B2 in particular is the number most
crypto strategies quietly fail against, and it must be fixed before we have a stake in it.

**Gate:** all three benchmarks computed, documented, and frozen with a config hash.

---

### Stage 3 — V1 in Python

Build the V1 specification ([STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §5.1): feature
engine, trend ensemble, vol-scaled sizing, risk engine, simulated execution.

**Experiments:** EXP-0003, 0004, 0005, 0007, 0008, 0009, 0010, 0011, 0012.

**Gate:** all seven V1 pass criteria ([STRATEGY_HYPOTHESES.md](STRATEGY_HYPOTHESES.md) §5.3),
most importantly **out-of-sample Sharpe above B2, surviving the Deflated Sharpe correction at the
logged trial count.**

**If this gate fails: STOP AND REPORT.** The honest deliverable is then "vol-targeted buy & hold
is the better product, and here is the evidence." Do not proceed to Stage 4 with a broken V1 on
the theory that later components will rescue it. They will not; they will only make the failure
harder to see.

---

### Stage 4 — Adversarial review

Full attack per [docs/ADVERSARIAL_REVIEW.md](docs/ADVERSARIAL_REVIEW.md), conducted as if trying
to prove the result false. Ideal division of labour: whoever built it does not lead the review
(see §5).

**Gate:** every attack documented with its outcome; no unresolved look-ahead, survivorship, or
selection-bias finding.

---

### Stage 5 — MQL5 port and parity

Port V1 to MQL5 following [ARCHITECTURE.md](ARCHITECTURE.md) §2. Build the parity harness.

**Gate:** **100% signal-direction parity** between Python and MQL5 across the full history;
continuous values within 1e-6 relative tolerance; parity test running in CI.

---

### Stage 6 — MT5 historical validation

Strategy Tester on real ticks where available; restart/recovery testing; error-path testing
(invalid stops, insufficient margin, requotes, disconnects); state persistence verification.

**Gate:** MT5 results match the Python backtest within the tolerance explained by tick modelling
and execution differences — **and any residual gap is explained, not averaged away.** An
unexplained difference between the research result and the tester result is a defect, not noise.

---

### Stage 7 — Demo forward test

≥ 90 days on demo with live data and full logging.

**Gate:** live behaviour inside the backtest's predicted distribution (trade frequency, win rate,
average trade duration, realised volatility); **zero execution defects**; every trade
reconstructable end to end from the log.

> Forward-test underperformance versus backtest is **expected and normal**. Underperformance
> *outside the predicted distribution* is a finding that sends us back to Stage 4.

---

### Stage 8 — Component promotion (iterative)

Now, and only now, components are added one at a time — EXP-0013 through EXP-0019.

**Promotion rule for each:** beats the frozen V1 baseline out of sample, survives its own
adversarial review, and its trial cost is added to the cumulative counter. **A component that
does not clearly beat the baseline is rejected, not retained "because it doesn't hurt."**
Neutral components add parameters, maintenance burden, and failure modes for nothing.

---

### Stage 9 — Small controlled live deployment

Only after Stages 1–8. Minimum viable capital. Predefined stop conditions agreed in writing
before funding. Daily reconciliation of live results against the expected distribution.

**Gate before scaling:** ≥ 6 months live within the predicted distribution.

---

## 3. Indicative timeline

Calendar estimates assume part-time effort and **exclude waiting time on demo and live stages**,
which cannot be compressed.

| Stage | Effort | Elapsed |
|---|---|---|
| 1 — Data + honesty infrastructure | 1–2 weeks | 2 weeks |
| 2 — Benchmarks | 3–4 days | 3 weeks |
| 3 — V1 Python + experiments | 2–3 weeks | 6 weeks |
| 4 — Adversarial review | 1 week | 7 weeks |
| 5 — MQL5 port + parity | 2 weeks | 9 weeks |
| 6 — MT5 validation | 1 week | 10 weeks |
| 7 — Demo forward test | **90 days, unskippable** | ~23 weeks |
| 8 — Component promotion | 1 week per component | ongoing |
| 9 — Live | — | 6+ months monitoring |

**Realistic time to a defensible live decision: 6–9 months.** Any plan materially shorter than
this is skipping a gate — most often Stage 7, because waiting is the least satisfying part.

---

## 4. Component promotion process

```
  hypothesis ──► pre-register in EXPERIMENT_LOG ──► implement in /research
       │                                                    │
       │                                                    ▼
       │                                          test vs FROZEN baseline
       │                                                    │
       │                         ┌──────────────────────────┴────────┐
       │                         ▼                                   ▼
       │              beats baseline OOS?                    does not beat it
       │                         │                                   │
       │                         ▼                                   ▼
       │              adversarial review                    REJECT + record why
       │                         │                          (rejections are results
       │                         ▼                           and stay in the log)
       │              promote: rewrite into /src with tests
       │                         │
       │                         ▼
       └──────────────  new frozen baseline
```

**Promotion means rewriting into `/src` with tests, not moving the research file.** That boundary
is what keeps experimental logic out of production ([ARCHITECTURE.md](ARCHITECTURE.md) §2).

---

## 5. Working with ChatGPT and Codex (Phase 20)

| Role | Best used for | Not used for |
|---|---|---|
| **Claude Code (this repo)** | Implementation plans, interfaces, tests, adversarial review, honest reporting of results | Deciding risk appetite; approving live deployment |
| **ChatGPT** | Independent literature checks, architecture critique, **challenging our conclusions** | Being a second opinion that agrees — that has no value |
| **Codex** | Mechanical implementation against a specified interface, refactoring, test generation | Deciding strategy logic |

**Handover format.** Every completed component is reported as: (1) what was built, (2) why,
(3) files changed, (4) how to test it, (5) results **including failures**, (6) known limitations,
(7) next experiment.

**Two standing rules for collaboration:**

1. **Never silently change strategy logic.** If an implementation detail forces a deviation from
   the specification, it is raised and recorded, not absorbed. Silent deviation is how the EA
   ends up trading something the research never validated.
2. **Independent review means independent.** The highest-value use of a second model is asking
   it to *attack* a result we like, with the evidence in front of it — not to confirm it. A
   review that returns agreement without having tried to falsify anything should be re-run with
   a sharper prompt.

---

## 6. What would make us stop

Written down now, while nothing is invested, because these judgements are much harder to make
after months of work.

| Trigger | Response |
|---|---|
| Null-pipeline control fails | **Stop.** Fix the pipeline; all prior results void |
| V1 does not beat B2 out of sample | **Stop and report.** Vol-targeted buy & hold is the better product |
| Measured costs > 2× modelled | Re-run all feasibility arithmetic before continuing |
| Edge requires > 1.5× gross leverage to be interesting | **Stop.** The drawdown mathematics do not support it |
| Results depend on a specific parameter value | **Stop.** Overfit, by definition |
| Live results outside the predicted distribution for 3 months | Halt live, return to Stage 4 |
| We find ourselves relaxing a gate to keep going | **Stop and re-read this table** |

**The most likely outcome of this project is a well-evidenced "no."** That is a real result: it
costs a few months and saves an account. The failure mode to guard against is not building
something that doesn't work — it is building something that doesn't work and adjusting it until
the backtest says otherwise.

---

## 7. Immediate next actions

1. Confirm the target broker and export real symbol specifications for BTCUSD — feeds directly
   into [`results/lot_granularity.md`](results/lot_granularity.md), which may be a deployment blocker on a
   small account.
2. Confirm account size and **maximum tolerable drawdown**. Per
   [RESEARCH.md](RESEARCH.md) §6, drawdown tolerance is the parameter that actually determines
   achievable return — it needs to be a stated decision, not an emergent one.
3. Build Stage 1 infrastructure.
4. Run EXP-0001, EXP-0002, EXP-0006.
5. Report results — including, and especially, failures.
