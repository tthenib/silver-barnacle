"""Order intents and their authoritative state machine.

An :class:`OrderIntent` is a proposal to trade, identified by a deterministic
fingerprint over its economic fields. The state machine — not any chat
transcript or log line — is authoritative for the trade lifecycle, and every
transition is recorded to the audit ledger *before* callers act on it
(specification section 4).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.core.audit import AuditLedger
from quant_platform.core.errors import StateTransitionError
from quant_platform.core.metadata import content_hash, new_id


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class IntentState(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    RISK_APPROVED = "RISK_APPROVED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    BLOCKED_PENDING_RECONCILIATION = "BLOCKED_PENDING_RECONCILIATION"


#: Allowed transitions. HUMAN_APPROVED is optional: in modes where policy does
#: not require a human, RISK_APPROVED may proceed directly to SUBMITTED.
_TRANSITIONS: dict[IntentState, frozenset[IntentState]] = {
    IntentState.DRAFT: frozenset(
        {IntentState.VALIDATED, IntentState.REJECTED, IntentState.EXPIRED}
    ),
    IntentState.VALIDATED: frozenset(
        {IntentState.RISK_APPROVED, IntentState.REJECTED, IntentState.EXPIRED}
    ),
    IntentState.RISK_APPROVED: frozenset(
        {
            IntentState.HUMAN_APPROVED,
            IntentState.SUBMITTED,
            IntentState.REJECTED,
            IntentState.EXPIRED,
        }
    ),
    IntentState.HUMAN_APPROVED: frozenset(
        {IntentState.SUBMITTED, IntentState.REJECTED, IntentState.EXPIRED}
    ),
    IntentState.SUBMITTED: frozenset(
        {
            IntentState.ACKNOWLEDGED,
            IntentState.REJECTED,
            IntentState.BLOCKED_PENDING_RECONCILIATION,
        }
    ),
    IntentState.ACKNOWLEDGED: frozenset(
        {
            IntentState.PARTIALLY_FILLED,
            IntentState.FILLED,
            IntentState.CANCELLED,
            IntentState.REJECTED,
            IntentState.BLOCKED_PENDING_RECONCILIATION,
        }
    ),
    IntentState.PARTIALLY_FILLED: frozenset(
        {
            IntentState.FILLED,
            IntentState.CANCELLED,
            IntentState.BLOCKED_PENDING_RECONCILIATION,
        }
    ),
    IntentState.FILLED: frozenset(),
    IntentState.CANCELLED: frozenset(),
    IntentState.REJECTED: frozenset(),
    IntentState.EXPIRED: frozenset(),
    IntentState.BLOCKED_PENDING_RECONCILIATION: frozenset(
        {IntentState.FILLED, IntentState.CANCELLED, IntentState.REJECTED}
    ),
}

TERMINAL_STATES = frozenset(
    {IntentState.FILLED, IntentState.CANCELLED, IntentState.REJECTED, IntentState.EXPIRED}
)


class OrderIntent(BaseModel):
    """Immutable economic description of a proposed order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: str = Field(default_factory=lambda: new_id("intent"))
    correlation_id: str
    account_alias: str
    symbol: str
    side: OrderSide
    quantity: float = Field(gt=0)
    order_type: str = "MARKET"
    asset_class: str = "EQUITY"
    rationale: str = Field(min_length=1)
    max_acceptable_loss: float = Field(gt=0)
    expires_at_utc: datetime
    trading_day: date

    def fingerprint(self) -> str:
        """Deterministic identity over the economic fields.

        Two intents that would place the same order on the same day produce
        the same fingerprint, which is what idempotency and duplicate
        suppression key on. Metadata (IDs, rationale) is excluded.
        """
        return content_hash(
            {
                "account_alias": self.account_alias,
                "symbol": self.symbol,
                "side": self.side,
                "quantity": self.quantity,
                "order_type": self.order_type,
                "asset_class": self.asset_class,
                "trading_day": self.trading_day.isoformat(),
                "correlation_id": self.correlation_id,
            }
        )


class IntentLifecycle:
    """Tracks and enforces the state of every intent; audit-first transitions."""

    def __init__(self, audit: AuditLedger) -> None:
        self._audit = audit
        self._states: dict[str, IntentState] = {}
        self._intents: dict[str, OrderIntent] = {}

    def open(self, intent: OrderIntent) -> None:
        if intent.intent_id in self._states:
            raise StateTransitionError(f"intent already open: {intent.intent_id}")
        self._states[intent.intent_id] = IntentState.DRAFT
        self._intents[intent.intent_id] = intent
        self._audit.append(
            "intent.opened",
            correlation_id=intent.correlation_id,
            actor="intent_lifecycle",
            payload={
                "intent_id": intent.intent_id,
                "fingerprint": intent.fingerprint(),
                "symbol": intent.symbol,
                "side": intent.side,
                "quantity": intent.quantity,
                "state": IntentState.DRAFT,
            },
        )

    def state_of(self, intent_id: str) -> IntentState:
        return self._states[intent_id]

    def intent(self, intent_id: str) -> OrderIntent:
        return self._intents[intent_id]

    def transition(self, intent_id: str, to_state: IntentState, actor: str, reason: str) -> None:
        """Move an intent to ``to_state``; recorded before the caller proceeds."""
        current = self._states.get(intent_id)
        if current is None:
            raise StateTransitionError(f"unknown intent: {intent_id}")
        if to_state not in _TRANSITIONS[current]:
            raise StateTransitionError(
                f"illegal transition {current} -> {to_state} for {intent_id}"
            )
        intent = self._intents[intent_id]
        self._audit.append(
            "intent.transition",
            correlation_id=intent.correlation_id,
            actor=actor,
            payload={
                "intent_id": intent_id,
                "from": current,
                "to": to_state,
                "reason": reason,
            },
        )
        self._states[intent_id] = to_state

    def active_duplicates_of(self, intent_id: str) -> list[str]:
        """IDs of *other* non-terminal intents sharing this intent's fingerprint.

        A non-empty result means submitting ``intent_id`` could double an
        order that is already in flight; the gateway must refuse.
        """
        fingerprint = self._intents[intent_id].fingerprint()
        return [
            other_id
            for other_id, state in self._states.items()
            if other_id != intent_id
            and state not in TERMINAL_STATES
            and self._intents[other_id].fingerprint() == fingerprint
        ]

    def blocked_intents(self) -> list[OrderIntent]:
        return [
            self._intents[intent_id]
            for intent_id, state in self._states.items()
            if state is IntentState.BLOCKED_PENDING_RECONCILIATION
        ]

    def known_intent_ids(self) -> list[str]:
        """All intent IDs ever opened (read-only view for reconciliation/reporting)."""
        return list(self._intents.keys())
