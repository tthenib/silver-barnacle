# ADR-0002: pydantic v2 frozen models as the schema technology

**Status:** accepted · **Review by:** if cross-language consumers appear

## Context

Specification section 4 requires versioned schemas for every domain object,
with universal metadata and backward-compatible evolution. Candidates:
dataclasses + manual validation, attrs, pydantic, protobuf/JSON-schema.

## Decision

pydantic v2 `BaseModel` with `frozen=True` and `extra="forbid"` for every
domain contract and configuration model. `SCHEMA_VERSION` is carried in
`core.metadata`; canonical JSON + SHA-256 (`content_hash`) provides stable
fingerprints for intents, bars, and specs.

## Consequences

- Validation at construction: malformed data cannot exist in memory, which is
  the cheapest place to fail closed.
- `extra="forbid"` makes config typos startup errors (tested).
- Immutability makes accounting and intents value-semantic; mutations are new
  objects, which matches the append-only audit posture.
- Cost: pydantic is a runtime dependency; serialization of exotic types needs
  care. Accepted — it is the platform's only non-stdlib runtime dependency
  besides PyYAML.

## Rollback

Contracts are plain field declarations; migrating to another schema system is
mechanical but touches every module. Avoid by keeping pydantic idioms shallow
(no custom validators where a plain check function works).
