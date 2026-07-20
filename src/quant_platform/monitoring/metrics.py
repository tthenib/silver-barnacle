"""In-process metrics registry (counters and gauges)."""

from __future__ import annotations

import threading


class MetricsRegistry:
    """Thread-safe counters and gauges with a stable snapshot export.

    Metric names follow ``domain.subject.action`` (e.g.
    ``execution.intent.submitted``); labels are encoded by the caller into
    the name for now, which keeps the registry trivially replaceable.
    """

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._lock = threading.Lock()

    def increment(self, name: str, amount: float = 1.0) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + amount

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def counter(self, name: str) -> float:
        with self._lock:
            return self._counters.get(name, 0.0)

    def gauge(self, name: str) -> float | None:
        with self._lock:
            return self._gauges.get(name)

    def snapshot(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return {"counters": dict(self._counters), "gauges": dict(self._gauges)}
