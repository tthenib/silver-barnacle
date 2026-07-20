"""Universal event metadata and content hashing.

Every durable domain record carries the metadata fields required by
specification section 4, so that any artifact can be traced from research to
execution and back (correlation), attributed to the code and policy versions
that produced it, and verified against tampering (content hash).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"


def new_id(prefix: str) -> str:
    """Return a globally unique, prefix-tagged identifier (e.g. ``intent-…``)."""
    return f"{prefix}-{uuid.uuid4()}"


def canonical_json(payload: Any) -> str:
    """Serialize a payload deterministically for hashing and fingerprints.

    Keys are sorted and separators fixed so that logically identical payloads
    always produce identical bytes regardless of construction order.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(payload: Any) -> str:
    """Return the SHA-256 hex digest of the canonical form of ``payload``."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class EventMetadata(BaseModel):
    """Universal metadata attached to durable domain events.

    ``correlation_id`` ties every artifact of one research/trade case together;
    ``causation_id`` names the immediate upstream event. ``as_of_utc`` is the
    knowledge cutoff of the content (what the producer knew), distinct from
    ``created_at_utc`` (when the record was written).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(default_factory=lambda: new_id("event"))
    correlation_id: str
    causation_id: str | None = None
    schema_version: str = SCHEMA_VERSION
    created_at_utc: datetime
    as_of_utc: datetime
    source: str
    source_record_id: str | None = None
    content_hash: str | None = None
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    policy_version: str | None = None
    code_version: str | None = None
