"""Reconciliation of intent state against broker-reported executions.

The reconciler is the authority for resolving ambiguity. It matches broker
executions to intents by client order ID (the intent fingerprint) and:

- confirms acknowledged intents as filled,
- resolves ``BLOCKED_PENDING_RECONCILIATION`` intents definitively — filled
  when the broker reports an execution, cancelled when the broker confirms it
  never saw the order,
- flags any broker execution with no matching intent as a critical
  discrepancy (something traded outside the platform's authority).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from quant_platform.core.audit import AuditLedger
from quant_platform.execution.broker import BrokerGateway
from quant_platform.execution.intents import IntentLifecycle, IntentState


class ReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    confirmed_fills: tuple[str, ...]  # intent IDs confirmed FILLED
    resolved_cancellations: tuple[str, ...]  # blocked intents confirmed never-executed
    unmatched_broker_executions: tuple[str, ...]  # broker order IDs with no intent
    still_blocked: tuple[str, ...]  # intent IDs that remain unresolved

    @property
    def clean(self) -> bool:
        return not self.unmatched_broker_executions and not self.still_blocked


class Reconciler:
    def __init__(
        self, broker: BrokerGateway, lifecycle: IntentLifecycle, audit: AuditLedger
    ) -> None:
        self._broker = broker
        self._lifecycle = lifecycle
        self._audit = audit

    def reconcile(self) -> ReconciliationReport:
        executions_by_client_id = {e.client_order_id: e for e in self._broker.executions()}
        confirmed: list[str] = []
        cancelled: list[str] = []
        matched_client_ids: set[str] = set()

        # Resolve acknowledged and blocked intents against broker truth.
        for intent in list(self._lifecycle.blocked_intents()):
            fingerprint = intent.fingerprint()
            execution = executions_by_client_id.get(fingerprint)
            if execution is not None:
                matched_client_ids.add(fingerprint)
                self._lifecycle.transition(
                    intent.intent_id,
                    IntentState.FILLED,
                    actor="reconciler",
                    reason=f"broker execution {execution.broker_order_id} confirms fill",
                )
                confirmed.append(intent.intent_id)
            else:
                # The broker has no record: the order never executed.
                self._lifecycle.transition(
                    intent.intent_id,
                    IntentState.CANCELLED,
                    actor="reconciler",
                    reason="broker reports no execution for this client order id",
                )
                cancelled.append(intent.intent_id)

        # Confirm acknowledged intents whose fills the broker reports.
        for client_id, execution in executions_by_client_id.items():
            for intent_id, state in list(self._states_snapshot().items()):
                intent = self._lifecycle.intent(intent_id)
                if intent.fingerprint() != client_id:
                    continue
                matched_client_ids.add(client_id)
                if state is IntentState.ACKNOWLEDGED:
                    self._lifecycle.transition(
                        intent_id,
                        IntentState.FILLED,
                        actor="reconciler",
                        reason=f"broker execution {execution.broker_order_id} confirms fill",
                    )
                    confirmed.append(intent_id)

        unmatched = sorted(
            e.broker_order_id
            for cid, e in executions_by_client_id.items()
            if cid not in matched_client_ids
        )
        if unmatched:
            self._audit.append(
                "reconciliation.discrepancy",
                correlation_id="reconciler",
                actor="reconciler",
                payload={
                    "unmatched_broker_order_ids": unmatched,
                    "severity": "CRITICAL",
                    "detail": "broker executions exist with no corresponding intent",
                },
            )

        still_blocked = [i.intent_id for i in self._lifecycle.blocked_intents()]
        report = ReconciliationReport(
            confirmed_fills=tuple(confirmed),
            resolved_cancellations=tuple(cancelled),
            unmatched_broker_executions=tuple(unmatched),
            still_blocked=tuple(still_blocked),
        )
        self._audit.append(
            "reconciliation.completed",
            correlation_id="reconciler",
            actor="reconciler",
            payload=report.model_dump(),
        )
        return report

    def _states_snapshot(self) -> dict[str, IntentState]:
        return {
            intent_id: self._lifecycle.state_of(intent_id)
            for intent_id in self._lifecycle.known_intent_ids()
        }
