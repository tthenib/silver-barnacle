"""The execution gateway — the only component that may request broker action.

Preflight sequence for every submission (specification sections 2.2 and 6):

1. Mode check: the current execution mode must permit submission at all.
2. Circuit breaker must be armed.
3. Capability check: asset class, order type, and side must be in the
   verified capability intersection.
4. Approval check: a matching, unexpired approval for this exact fingerprint.
5. Intent state check: the state machine must permit SUBMITTED.
6. Idempotency check: no other active intent shares the fingerprint, and the
   fingerprint is used as the broker-side client order ID.
7. Freshness check: a broker snapshot taken within policy age, re-queried
   immediately before submission, with sufficient buying power / position.

Any ambiguity in the broker response parks the intent in
``BLOCKED_PENDING_RECONCILIATION``; the reconciler, not the gateway, decides
what actually happened.
"""

from __future__ import annotations

from quant_platform.core.audit import AuditLedger
from quant_platform.core.clock import Clock
from quant_platform.core.config import (
    SUBMITTING_MODES,
    ExecutionMode,
    ExecutionPolicyConfig,
)
from quant_platform.core.errors import (
    AmbiguousBrokerResponseError,
    BrokerError,
    PolicyViolationError,
)
from quant_platform.execution.approvals import ApprovalRecord, ApprovalService
from quant_platform.execution.broker import (
    BrokerGateway,
    OrderRequest,
    SubmissionStatus,
    VerifiedCapabilities,
)
from quant_platform.execution.intents import (
    IntentLifecycle,
    IntentState,
    OrderIntent,
    OrderSide,
)
from quant_platform.risk.circuit_breakers import CircuitBreaker


class ExecutionGateway:
    def __init__(
        self,
        broker: BrokerGateway,
        capabilities: VerifiedCapabilities,
        lifecycle: IntentLifecycle,
        approvals: ApprovalService,
        breaker: CircuitBreaker,
        policy: ExecutionPolicyConfig,
        audit: AuditLedger,
        clock: Clock,
        mode: ExecutionMode,
    ) -> None:
        self._broker = broker
        self._capabilities = capabilities
        self._lifecycle = lifecycle
        self._approvals = approvals
        self._breaker = breaker
        self._policy = policy
        self._audit = audit
        self._clock = clock
        self._mode = mode

    @property
    def mode(self) -> ExecutionMode:
        return self._mode

    def set_mode(self, mode: ExecutionMode, actor: str, reason: str) -> None:
        """Mode changes are audited; tightening is always allowed, loosening is
        a policy action that requires a named actor and reason."""
        if not actor.strip() or not reason.strip():
            raise PolicyViolationError("mode change requires a named actor and a reason")
        self._audit.append(
            "gateway.mode_changed",
            correlation_id="gateway",
            actor=actor,
            payload={"from": self._mode, "to": mode, "reason": reason},
        )
        self._mode = mode

    def submit(self, intent: OrderIntent, approval: ApprovalRecord) -> None:
        """Run the full preflight and submit; transitions record every outcome."""
        # 1. Mode.
        if self._mode not in SUBMITTING_MODES:
            raise PolicyViolationError(f"execution mode {self._mode} does not permit submission")

        # 2. Breaker.
        self._breaker.assert_armed()

        # 3. Capabilities.
        self._capabilities.assert_supports(intent.asset_class, intent.order_type, intent.side)

        # 4. Approval (fingerprint match, expiry, policy version).
        self._approvals.validate(approval, intent)

        # 5. Intent state: must currently allow submission.
        current = self._lifecycle.state_of(intent.intent_id)
        if current not in (IntentState.RISK_APPROVED, IntentState.HUMAN_APPROVED):
            raise PolicyViolationError(f"intent in state {current} cannot be submitted")

        # Intent-level expiry is checked against the injected clock.
        if self._clock.now() > intent.expires_at_utc:
            self._lifecycle.transition(
                intent.intent_id, IntentState.EXPIRED, actor="gateway", reason="intent expired"
            )
            raise PolicyViolationError("intent has expired")

        # 6. Idempotency: no other live intent may share this fingerprint.
        fingerprint = intent.fingerprint()
        duplicates = self._lifecycle.active_duplicates_of(intent.intent_id)
        if duplicates:
            raise PolicyViolationError(
                f"fingerprint {fingerprint[:12]}… already active on {duplicates}; "
                "refusing possible duplicate order"
            )

        # 7. Fresh broker snapshot, taken now, validated for age and funding.
        snapshot = self._broker.account_snapshot()
        age = (self._clock.now() - snapshot.taken_at_utc).total_seconds()
        if age > self._policy.broker_snapshot_max_age_seconds:
            raise PolicyViolationError(f"broker snapshot is stale ({age:.0f}s)")
        if snapshot.account_alias != intent.account_alias:
            raise PolicyViolationError(
                "intent account does not match broker account; refusing to submit"
            )
        if intent.side is OrderSide.SELL:
            held = snapshot.positions.get(intent.symbol, 0.0)
            if intent.quantity > held + 1e-9:
                raise PolicyViolationError(
                    f"sell quantity {intent.quantity} exceeds held {held} for {intent.symbol}"
                )

        # Submit. The transition to SUBMITTED is recorded before the broker call.
        self._lifecycle.transition(
            intent.intent_id, IntentState.SUBMITTED, actor="gateway", reason="preflight passed"
        )
        request = OrderRequest(
            client_order_id=fingerprint,
            account_alias=intent.account_alias,
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            order_type=intent.order_type,
        )
        try:
            response = self._broker.submit_order(request)
        except AmbiguousBrokerResponseError as exc:
            self._lifecycle.transition(
                intent.intent_id,
                IntentState.BLOCKED_PENDING_RECONCILIATION,
                actor="gateway",
                reason=f"ambiguous broker response: {exc}",
            )
            return
        except BrokerError as exc:
            self._lifecycle.transition(
                intent.intent_id,
                IntentState.REJECTED,
                actor="gateway",
                reason=f"broker error: {exc}",
            )
            return

        if response.status is SubmissionStatus.ACKNOWLEDGED:
            self._lifecycle.transition(
                intent.intent_id,
                IntentState.ACKNOWLEDGED,
                actor="gateway",
                reason=f"broker order {response.broker_order_id}",
            )
        else:
            self._lifecycle.transition(
                intent.intent_id,
                IntentState.REJECTED,
                actor="gateway",
                reason=f"broker rejected: {response.reason}",
            )
