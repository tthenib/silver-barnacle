"""Core primitives: audit chain integrity, secret redaction, config loading."""

from __future__ import annotations

import pytest

from quant_platform.core.audit import AuditLedger, AuditRecord
from quant_platform.core.clock import FrozenClock
from quant_platform.core.config import ExecutionMode, RiskLimitsConfig
from quant_platform.core.errors import AuditIntegrityError, ConfigurationError
from quant_platform.core.logging import REDACTED, redact
from quant_platform.core.metadata import content_hash


class TestAuditLedger:
    def test_chain_verifies_after_appends(self, audit: AuditLedger) -> None:
        for i in range(5):
            audit.append("test.event", correlation_id="case-1", actor="test", payload={"i": i})
        audit.verify_chain()  # must not raise

    def test_tampered_payload_is_detected(self, clock: FrozenClock) -> None:
        ledger = AuditLedger(clock=clock)
        ledger.append("test.event", correlation_id="c", actor="t", payload={"amount": 10})
        ledger.append("test.event", correlation_id="c", actor="t", payload={"amount": 20})
        # Simulate in-place tampering with the stored list.
        original = ledger._records[0]
        ledger._records[0] = AuditRecord(
            sequence=original.sequence,
            timestamp_utc=original.timestamp_utc,
            event_type=original.event_type,
            correlation_id=original.correlation_id,
            actor=original.actor,
            payload={"amount": 9999},
            previous_hash=original.previous_hash,
            record_hash=original.record_hash,
        )
        with pytest.raises(AuditIntegrityError):
            ledger.verify_chain()

    def test_truncation_is_detected(self, clock: FrozenClock) -> None:
        ledger = AuditLedger(clock=clock)
        for i in range(3):
            ledger.append("test.event", correlation_id="c", actor="t", payload={"i": i})
        del ledger._records[1]
        with pytest.raises(AuditIntegrityError):
            ledger.verify_chain()

    def test_correlation_filtering(self, audit: AuditLedger) -> None:
        audit.append("a", correlation_id="case-1", actor="t", payload={})
        audit.append("b", correlation_id="case-2", actor="t", payload={})
        audit.append("c", correlation_id="case-1", actor="t", payload={})
        assert [r.event_type for r in audit.records_for("case-1")] == ["a", "c"]


class TestRedaction:
    def test_secret_keys_masked_recursively(self) -> None:
        payload = {
            "api_key": "abc123",
            "nested": {"broker_token": "xyz", "symbol": "AAA"},
            "items": [{"password": "p"}],
        }
        clean = redact(payload)
        assert clean["api_key"] == REDACTED
        assert clean["nested"]["broker_token"] == REDACTED
        assert clean["nested"]["symbol"] == "AAA"
        assert clean["items"][0]["password"] == REDACTED


class TestConfig:
    def test_committed_config_loads(self, platform_config) -> None:
        assert platform_config.execution_policy.default_mode is ExecutionMode.SIMULATION
        assert platform_config.risk_limits.max_position_weight <= 1.0
        assert ExecutionMode.APPROVAL_REQUIRED in (
            platform_config.execution_policy.require_human_approval_in
        )

    def test_unknown_keys_rejected(self, tmp_path) -> None:
        bad = tmp_path / "limits.yaml"
        bad.write_text("policy_version: x\nmax_position_weight: 0.1\ntypo_key: 1\n")
        from quant_platform.core.config import load_yaml_model

        with pytest.raises(ConfigurationError):
            load_yaml_model(bad, RiskLimitsConfig)


class TestContentHash:
    def test_key_order_does_not_matter(self) -> None:
        assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})

    def test_value_change_changes_hash(self) -> None:
        assert content_hash({"a": 1}) != content_hash({"a": 2})
