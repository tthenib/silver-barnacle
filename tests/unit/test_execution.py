"""Execution plane: intent state machine, approvals, capabilities, agents."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quant_platform.agents.base import TechnicalStateAgent
from quant_platform.agents.evaluation import evaluate_outputs
from quant_platform.core.audit import AuditLedger
from quant_platform.core.clock import FrozenClock
from quant_platform.core.config import BrokerCapabilityAllowlist, ExecutionMode
from quant_platform.core.errors import ApprovalError, PolicyViolationError, StateTransitionError
from quant_platform.data.validation import BarSeriesValidator
from quant_platform.execution.approvals import ApprovalService
from quant_platform.execution.broker import BrokerCapabilities, VerifiedCapabilities
from quant_platform.execution.intents import (
    IntentLifecycle,
    IntentState,
    OrderIntent,
    OrderSide,
)
from quant_platform.risk.engine import RiskDecision
from tests.unit.test_data import weekday_series


def make_intent(clock: FrozenClock, symbol: str = "AAA", quantity: float = 10.0) -> OrderIntent:
    return OrderIntent(
        correlation_id="case-1",
        account_alias="sim-account",
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        rationale="test intent",
        max_acceptable_loss=100.0,
        expires_at_utc=clock.now() + timedelta(minutes=10),
        trading_day=clock.now().date(),
    )


def passing_risk_decision() -> RiskDecision:
    return RiskDecision(
        policy_version="risk-limits-1.0.0",
        approved_weights={"AAA": 0.05},
        evaluations=(),
        new_risk_blocked=False,
    )


class TestIntentStateMachine:
    def test_happy_path_transitions(self, clock: FrozenClock, audit: AuditLedger) -> None:
        lifecycle = IntentLifecycle(audit)
        intent = make_intent(clock)
        lifecycle.open(intent)
        for state in (
            IntentState.VALIDATED,
            IntentState.RISK_APPROVED,
            IntentState.SUBMITTED,
            IntentState.ACKNOWLEDGED,
            IntentState.FILLED,
        ):
            lifecycle.transition(intent.intent_id, state, actor="test", reason="step")
        assert lifecycle.state_of(intent.intent_id) is IntentState.FILLED

    def test_illegal_transition_rejected(self, clock: FrozenClock, audit: AuditLedger) -> None:
        lifecycle = IntentLifecycle(audit)
        intent = make_intent(clock)
        lifecycle.open(intent)
        with pytest.raises(StateTransitionError):
            lifecycle.transition(intent.intent_id, IntentState.FILLED, actor="test", reason="skip")

    def test_terminal_states_are_final(self, clock: FrozenClock, audit: AuditLedger) -> None:
        lifecycle = IntentLifecycle(audit)
        intent = make_intent(clock)
        lifecycle.open(intent)
        lifecycle.transition(intent.intent_id, IntentState.REJECTED, actor="test", reason="no")
        with pytest.raises(StateTransitionError):
            lifecycle.transition(
                intent.intent_id, IntentState.VALIDATED, actor="test", reason="undo"
            )

    def test_every_transition_is_audited(self, clock: FrozenClock, audit: AuditLedger) -> None:
        lifecycle = IntentLifecycle(audit)
        intent = make_intent(clock)
        lifecycle.open(intent)
        lifecycle.transition(intent.intent_id, IntentState.VALIDATED, actor="test", reason="ok")
        events = [r.event_type for r in audit.records_for("case-1")]
        assert events == ["intent.opened", "intent.transition"]
        audit.verify_chain()

    def test_fingerprint_deterministic_and_metadata_free(self, clock: FrozenClock) -> None:
        a = make_intent(clock)
        b = make_intent(clock)  # different intent_id, same economics
        assert a.intent_id != b.intent_id
        assert a.fingerprint() == b.fingerprint()
        c = make_intent(clock, quantity=11.0)
        assert a.fingerprint() != c.fingerprint()


class TestApprovals:
    def _service(self, clock: FrozenClock, audit: AuditLedger, platform_config) -> ApprovalService:
        return ApprovalService(platform_config.execution_policy, audit, clock)

    def test_simulation_allows_policy_approval(
        self, clock: FrozenClock, audit: AuditLedger, platform_config
    ) -> None:
        service = self._service(clock, audit, platform_config)
        intent = make_intent(clock)
        record = service.grant(
            intent,
            passing_risk_decision(),
            ExecutionMode.SIMULATION,
            approver="simulation-policy",
            approver_is_human=False,
        )
        service.validate(record, intent)  # must not raise

    def test_paper_mode_requires_human(
        self, clock: FrozenClock, audit: AuditLedger, platform_config
    ) -> None:
        service = self._service(clock, audit, platform_config)
        with pytest.raises(ApprovalError):
            service.grant(
                make_intent(clock),
                passing_risk_decision(),
                ExecutionMode.PAPER,
                approver="bot",
                approver_is_human=False,
            )

    def test_blocked_risk_decision_cannot_be_approved(
        self, clock: FrozenClock, audit: AuditLedger, platform_config
    ) -> None:
        service = self._service(clock, audit, platform_config)
        blocked = passing_risk_decision().model_copy(update={"new_risk_blocked": True})
        with pytest.raises(ApprovalError):
            service.grant(make_intent(clock), blocked, ExecutionMode.SIMULATION, "policy", False)

    def test_expired_approval_rejected(
        self, clock: FrozenClock, audit: AuditLedger, platform_config
    ) -> None:
        service = self._service(clock, audit, platform_config)
        intent = make_intent(clock)
        record = service.grant(
            intent, passing_risk_decision(), ExecutionMode.SIMULATION, "policy", False
        )
        clock.advance(seconds=platform_config.execution_policy.approval_ttl_seconds + 1)
        with pytest.raises(ApprovalError):
            service.validate(record, intent)

    def test_mutated_intent_invalidates_approval(
        self, clock: FrozenClock, audit: AuditLedger, platform_config
    ) -> None:
        service = self._service(clock, audit, platform_config)
        intent = make_intent(clock)
        record = service.grant(
            intent, passing_risk_decision(), ExecutionMode.SIMULATION, "policy", False
        )
        mutated = make_intent(clock, quantity=999.0)
        with pytest.raises(ApprovalError):
            service.validate(record, mutated)


class TestVerifiedCapabilities:
    def test_intersection_and_refusal(self, clock: FrozenClock) -> None:
        reported = BrokerCapabilities(
            broker_name="simulated",
            account_alias="sim-account",
            asset_classes=("EQUITY", "CRYPTO"),  # broker claims more than reviewed
            order_types=("MARKET", "LIMIT"),
            sides=("BUY", "SELL"),
            discovered_at_utc=clock.now(),
        )
        allowlist = BrokerCapabilityAllowlist(
            broker_name="simulated",
            allowed_asset_classes=("EQUITY",),
            allowed_order_types=("MARKET",),
        )
        verified = VerifiedCapabilities(reported, allowlist)
        verified.assert_supports("EQUITY", "MARKET", "BUY")
        with pytest.raises(PolicyViolationError):
            verified.assert_supports("CRYPTO", "MARKET", "BUY")
        with pytest.raises(PolicyViolationError):
            verified.assert_supports("EQUITY", "LIMIT", "BUY")

    def test_broker_name_mismatch_rejected(self, clock: FrozenClock) -> None:
        reported = BrokerCapabilities(
            broker_name="other",
            account_alias="x",
            asset_classes=("EQUITY",),
            order_types=("MARKET",),
            sides=("BUY",),
            discovered_at_utc=clock.now(),
        )
        allowlist = BrokerCapabilityAllowlist(
            broker_name="simulated",
            allowed_asset_classes=("EQUITY",),
            allowed_order_types=("MARKET",),
        )
        with pytest.raises(PolicyViolationError):
            VerifiedCapabilities(reported, allowlist)


class TestAgents:
    def test_agent_emits_cited_claims(self) -> None:
        series, _ = BarSeriesValidator().validate("AAA", weekday_series(60))
        agent = TechnicalStateAgent(series)
        output = agent.run("case-1", datetime(2025, 7, 1, tzinfo=UTC))
        assert not output.abstained
        assert all(claim.sources for claim in output.claims)

    def test_agent_abstains_on_short_history(self) -> None:
        series, _ = BarSeriesValidator().validate("AAA", weekday_series(10))
        output = TechnicalStateAgent(series).run("case-1", datetime(2025, 7, 1, tzinfo=UTC))
        assert output.abstained
        assert output.abstention_reason

    def test_evaluation_harness_measures_schema_validity(self) -> None:
        series, _ = BarSeriesValidator().validate("AAA", weekday_series(60))
        good = TechnicalStateAgent(series).run("c", datetime(2025, 7, 1, tzinfo=UTC))
        raw = [good.model_dump(), {"agent_name": "broken"}]  # one valid, one invalid
        report = evaluate_outputs(raw)
        assert report.outputs_evaluated == 2
        assert report.schema_valid_rate == pytest.approx(0.5)
        assert report.citation_coverage == 1.0
