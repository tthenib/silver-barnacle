# ADR-0005: In-memory + JSONL storage now, durable backends behind the same interfaces

**Status:** accepted · **Review by:** before restart-safety work (implementation plan item 3)

## Context

The specification requires durable, restartable state (workflow must resume
after a crash between intent creation and submission) and append-only audit
retention. It does not mandate a storage technology.

## Decision

Storage-facing components — `AuditLedger`, `TradeJournal`, `MarketDataStore` —
own narrow interfaces whose *contracts* (hash chaining, append-only entries,
as-of retrieval) are the stable part. Current backing is in-memory with
optional JSONL file sinks: sufficient for simulation and CI, deterministic,
and dependency-free.

## Consequences

- The platform is not yet restart-safe; this is acceptable only while every
  mode is simulation and is called out as a blocking item before paper mode
  in the implementation plan.
- Swapping in SQLite/Postgres repositories changes constructors, not callers.
- The audit hash chain is storage-agnostic by construction: `verify_chain`
  recomputes from record content, so a durable backend inherits tamper
  evidence for free.

## Rollback

Not applicable; this ADR schedules its own supersession.
