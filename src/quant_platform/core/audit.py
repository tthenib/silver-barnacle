"""Append-only, hash-chained audit ledger.

The ledger is the authoritative record of state transitions: intents,
approvals, risk decisions, broker interactions, and reconciliation results
are appended *before* their side effects are taken. Each record embeds the
hash of its predecessor so that truncation or in-place edits are detectable
via :meth:`AuditLedger.verify_chain`.

The default sink is an in-memory list plus an optional JSONL file. The
storage medium is intentionally replaceable (see ADR-0005); the chain format
is the contract, not the file.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from quant_platform.core.clock import Clock, WallClock
from quant_platform.core.errors import AuditIntegrityError
from quant_platform.core.metadata import canonical_json

GENESIS_HASH = "0" * 64


class AuditRecord(BaseModel):
    """One immutable ledger entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int
    timestamp_utc: datetime
    event_type: str
    correlation_id: str
    actor: str
    payload: dict[str, Any]
    previous_hash: str
    record_hash: str

    @staticmethod
    def compute_hash(
        sequence: int,
        timestamp_utc: datetime,
        event_type: str,
        correlation_id: str,
        actor: str,
        payload: dict[str, Any],
        previous_hash: str,
    ) -> str:
        body = canonical_json(
            {
                "sequence": sequence,
                "timestamp_utc": timestamp_utc.isoformat(),
                "event_type": event_type,
                "correlation_id": correlation_id,
                "actor": actor,
                "payload": payload,
                "previous_hash": previous_hash,
            }
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


class AuditLedger:
    """Thread-safe append-only ledger with hash chaining.

    Appending is the only mutation. Records are never updated or deleted;
    corrections are represented as new records referencing the original.
    """

    def __init__(self, clock: Clock | None = None, file_path: Path | None = None) -> None:
        self._clock = clock or WallClock()
        self._file_path = file_path
        self._records: list[AuditRecord] = []
        self._lock = threading.Lock()

    def append(
        self,
        event_type: str,
        correlation_id: str,
        actor: str,
        payload: dict[str, Any],
    ) -> AuditRecord:
        """Append one record and return it. Payload must be JSON-serializable."""
        with self._lock:
            sequence = len(self._records)
            previous_hash = self._records[-1].record_hash if self._records else GENESIS_HASH
            timestamp = self._clock.now()
            record_hash = AuditRecord.compute_hash(
                sequence, timestamp, event_type, correlation_id, actor, payload, previous_hash
            )
            record = AuditRecord(
                sequence=sequence,
                timestamp_utc=timestamp,
                event_type=event_type,
                correlation_id=correlation_id,
                actor=actor,
                payload=payload,
                previous_hash=previous_hash,
                record_hash=record_hash,
            )
            self._records.append(record)
            if self._file_path is not None:
                with self._file_path.open("a", encoding="utf-8") as handle:
                    handle.write(record.model_dump_json() + "\n")
            return record

    def records(self) -> Iterator[AuditRecord]:
        with self._lock:
            snapshot = list(self._records)
        return iter(snapshot)

    def records_for(self, correlation_id: str) -> list[AuditRecord]:
        return [r for r in self.records() if r.correlation_id == correlation_id]

    def verify_chain(self) -> None:
        """Raise :class:`AuditIntegrityError` if any record was altered or removed."""
        previous_hash = GENESIS_HASH
        for expected_sequence, record in enumerate(self.records()):
            if record.sequence != expected_sequence:
                raise AuditIntegrityError(
                    f"sequence gap at {record.sequence}, expected {expected_sequence}"
                )
            if record.previous_hash != previous_hash:
                raise AuditIntegrityError(f"chain break at sequence {record.sequence}")
            recomputed = AuditRecord.compute_hash(
                record.sequence,
                record.timestamp_utc,
                record.event_type,
                record.correlation_id,
                record.actor,
                record.payload,
                record.previous_hash,
            )
            if recomputed != record.record_hash:
                raise AuditIntegrityError(f"content hash mismatch at sequence {record.sequence}")
            previous_hash = record.record_hash
