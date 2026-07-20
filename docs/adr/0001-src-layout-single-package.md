# ADR-0001: src-layout single package instead of ~25 top-level directories

**Status:** accepted · **Review by:** when a second deployable service appears

## Context

Specification section 3 mandates a repository with ~25 top-level directories
mixing Python packages, generated artifacts, and infrastructure. The
specification also prohibits committing runtime state and reports.

## Decision

One installable package, `src/quant_platform/`, with domain subpackages that
mirror the specification's ownership table (core, data, strategies,
backtesting, risk, portfolio, execution, agents, memory, monitoring).
`config/`, `docs/`, `tests/`, `scripts/` stay top-level. `logs/`, `reports/`,
and state directories exist only in `.gitignore`.

## Consequences

Import hygiene and a single mypy/ruff target; the ownership boundaries and
prohibited couplings from the specification's table are preserved at the
subpackage level (e.g. strategies do not import execution). Directories the
specification reserves for future services (`api/`, `dashboard/`,
`pipelines/`) are created when the service exists, not before.

## Rollback

Mechanical: subpackages can be promoted to top-level packages without code
changes beyond imports.
