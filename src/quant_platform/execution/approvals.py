"""Approval records and the approval policy.

An approval is granted against an intent's *fingerprint*, so any mutation of
the intent invalidates it. Approvals expire; the gateway re-checks expiry at
submission time. In SIMULATION mode policy-based auto-approval is permitted
and recorded as such; modes listed in ``require_human_approval_in`` demand a
human identity, which the platform cannot fabricate.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from quant_platform.core.audit import AuditLedger
from quant_platform.core.clock import Clock
from quant_platform.core.config import ExecutionMode, ExecutionPolicyConfig
from quant_platform.core.errors import ApprovalError
from quant_platform.core.metadata import new_id
from quant_platform.execution.intents import OrderIntent
from quant_platform.risk.engine import RiskDecision


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: str
    intent_fingerprint: str
    approver: str
    approver_is_human: bool
    mode: ExecutionMode
    policy_version: str
    granted_at_utc: datetime
    expires_at_utc: datetime
    risk_policy_version: str


class ApprovalService:
    """Grants and validates approvals under the execution policy."""

    def __init__(self, policy: ExecutionPolicyConfig, audit: AuditLedger, clock: Clock) -> None:
        self._policy = policy
        self._audit = audit
        self._clock = clock

    def grant(
        self,
        intent: OrderIntent,
        risk_decision: RiskDecision,
        mode: ExecutionMode,
        approver: str,
        approver_is_human: bool,
    ) -> ApprovalRecord:
        """Grant an approval for an intent that has passed risk review."""
        if not risk_decision.passed:
            raise ApprovalError("cannot approve an intent whose risk decision blocked new risk")
        if mode in self._policy.require_human_approval_in and not approver_is_human:
            raise ApprovalError(f"mode {mode} requires a human approver")
        now = self._clock.now()
        record = ApprovalRecord(
            approval_id=new_id("approval"),
            intent_fingerprint=intent.fingerprint(),
            approver=approver,
            approver_is_human=approver_is_human,
            mode=mode,
            policy_version=self._policy.policy_version,
            granted_at_utc=now,
            expires_at_utc=now + timedelta(seconds=self._policy.approval_ttl_seconds),
            risk_policy_version=risk_decision.policy_version,
        )
        self._audit.append(
            "approval.granted",
            correlation_id=intent.correlation_id,
            actor=f"{'human' if approver_is_human else 'policy'}:{approver}",
            payload={
                "approval_id": record.approval_id,
                "intent_id": intent.intent_id,
                "fingerprint": record.intent_fingerprint,
                "mode": mode,
                "expires_at_utc": record.expires_at_utc.isoformat(),
            },
        )
        return record

    def validate(self, approval: ApprovalRecord, intent: OrderIntent) -> None:
        """Raise :class:`ApprovalError` unless the approval covers this intent now."""
        if approval.intent_fingerprint != intent.fingerprint():
            raise ApprovalError("approval fingerprint does not match intent")
        if self._clock.now() > approval.expires_at_utc:
            raise ApprovalError("approval has expired")
        if approval.policy_version != self._policy.policy_version:
            raise ApprovalError("approval was granted under a different execution policy version")
