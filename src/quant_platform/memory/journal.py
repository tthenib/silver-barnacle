"""Append-only trade journal (episodic memory).

Every lifecycle stage writes a dated entry keyed by correlation ID, so a
trade can be replayed end-to-end: which signals fired, what sizing decided,
what risk said, what was approved, what the broker did, and how it
reconciled. Entries are immutable; corrections are new entries referencing
the original.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.core.clock import Clock
from quant_platform.core.metadata import new_id


class JournalEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str = Field(default_factory=lambda: new_id("journal"))
    correlation_id: str
    stage: str
    recorded_at_utc: datetime
    payload: dict[str, Any]
    corrects_entry_id: str | None = None


class TradeJournal:
    """In-memory journal with optional JSONL persistence (medium per ADR-0005)."""

    def __init__(self, clock: Clock, file_path: Path | None = None) -> None:
        self._clock = clock
        self._file_path = file_path
        self._entries: list[JournalEntry] = []

    def record(
        self,
        correlation_id: str,
        stage: str,
        payload: dict[str, Any],
        corrects_entry_id: str | None = None,
    ) -> JournalEntry:
        entry = JournalEntry(
            correlation_id=correlation_id,
            stage=stage,
            recorded_at_utc=self._clock.now(),
            payload=payload,
            corrects_entry_id=corrects_entry_id,
        )
        self._entries.append(entry)
        if self._file_path is not None:
            with self._file_path.open("a", encoding="utf-8") as handle:
                handle.write(entry.model_dump_json() + "\n")
        return entry

    def entries_for(self, correlation_id: str) -> list[JournalEntry]:
        return [e for e in self._entries if e.correlation_id == correlation_id]

    def stages_for(self, correlation_id: str) -> list[str]:
        return [e.stage for e in self.entries_for(correlation_id)]
