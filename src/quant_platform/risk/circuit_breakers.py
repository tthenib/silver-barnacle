"""Circuit breaker and kill switch.

The breaker is a latching state machine: once tripped it stays tripped until
a human resets it with a recorded identity and reason. Tripping halts new
submissions while reconciliation and monitoring continue (specification
section 11). The kill switch is the isolated manual path — it can only trip,
never auto-reset, and requires the same audited human reset.
"""

from __future__ import annotations

from enum import StrEnum

from quant_platform.core.audit import AuditLedger
from quant_platform.core.errors import PolicyViolationError


class BreakerState(StrEnum):
    ARMED = "ARMED"
    TRIPPED = "TRIPPED"


class TripReason(StrEnum):
    DAILY_LOSS = "DAILY_LOSS"
    DRAWDOWN = "DRAWDOWN"
    DATA_QUALITY = "DATA_QUALITY"
    BROKER_DISCREPANCY = "BROKER_DISCREPANCY"
    MANUAL_KILL_SWITCH = "MANUAL_KILL_SWITCH"


class CircuitBreaker:
    """Latching global submission breaker with an audited reset path."""

    def __init__(self, audit: AuditLedger, name: str = "global") -> None:
        self._audit = audit
        self._name = name
        self._state = BreakerState.ARMED
        self._trip_reason: TripReason | None = None

    @property
    def state(self) -> BreakerState:
        return self._state

    @property
    def trip_reason(self) -> TripReason | None:
        return self._trip_reason

    def trip(self, reason: TripReason, detail: str, correlation_id: str) -> None:
        """Trip the breaker. Idempotent: re-tripping records but does not error."""
        self._state = BreakerState.TRIPPED
        self._trip_reason = reason
        self._audit.append(
            "circuit_breaker.tripped",
            correlation_id=correlation_id,
            actor=f"circuit_breaker:{self._name}",
            payload={"reason": reason, "detail": detail},
        )

    def reset(self, human_identity: str, reason: str, correlation_id: str) -> None:
        """Reset requires a named human and a reason; both are audited."""
        if not human_identity.strip() or not reason.strip():
            raise PolicyViolationError("breaker reset requires a named human identity and a reason")
        if self._state is BreakerState.ARMED:
            raise PolicyViolationError("breaker is not tripped")
        self._audit.append(
            "circuit_breaker.reset",
            correlation_id=correlation_id,
            actor=f"human:{human_identity}",
            payload={"previous_reason": self._trip_reason, "reset_reason": reason},
        )
        self._state = BreakerState.ARMED
        self._trip_reason = None

    def assert_armed(self) -> None:
        """Raise :class:`PolicyViolationError` when submissions are halted."""
        if self._state is BreakerState.TRIPPED:
            raise PolicyViolationError(
                f"circuit breaker '{self._name}' is TRIPPED ({self._trip_reason}); "
                "new submissions are halted"
            )


class KillSwitch:
    """Isolated manual emergency stop; delegates to the breaker for latching."""

    def __init__(self, breaker: CircuitBreaker) -> None:
        self._breaker = breaker

    def engage(self, human_identity: str, reason: str, correlation_id: str) -> None:
        if not human_identity.strip() or not reason.strip():
            raise PolicyViolationError("kill switch requires a named human identity and a reason")
        self._breaker.trip(
            TripReason.MANUAL_KILL_SWITCH,
            detail=f"engaged by {human_identity}: {reason}",
            correlation_id=correlation_id,
        )
