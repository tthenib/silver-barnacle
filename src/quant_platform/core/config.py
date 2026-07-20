"""Typed, schema-validated configuration ("policy as data").

Configuration lives in versioned YAML files under ``config/`` and is loaded
into frozen pydantic models with ``extra="forbid"`` so that a typo in a
policy file is a startup error, never a silently ignored key. No component
reads YAML directly; everything receives typed config objects.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from quant_platform.core.errors import ConfigurationError


class ExecutionMode(StrEnum):
    """Global execution posture, ordered from safest to most permissive.

    The platform defaults to SIMULATION and *downgrades* on any doubt
    (restart, policy change, data defect, unreconciled broker event).
    Live modes (APPROVAL_REQUIRED, LIMITED_AUTOPILOT) are defined by the
    specification but are not reachable until a live broker adapter exists
    and every go-live gate in specification section 22 has evidence.
    """

    EMERGENCY_STOP = "EMERGENCY_STOP"
    EXECUTION_PAUSED = "EXECUTION_PAUSED"
    SIMULATION = "SIMULATION"
    PAPER = "PAPER"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    LIMITED_AUTOPILOT = "LIMITED_AUTOPILOT"


#: Modes in which the execution gateway may submit orders to a broker adapter.
#: Only simulated submission is currently implemented; see ADR-0003.
SUBMITTING_MODES = frozenset({ExecutionMode.SIMULATION, ExecutionMode.PAPER})


class FrozenConfig(BaseModel):
    """Base for all config models: immutable and intolerant of unknown keys."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class RiskLimitsConfig(FrozenConfig):
    """Deterministic hard limits. No agent or strategy may widen these at runtime."""

    policy_version: str
    max_position_weight: float = Field(gt=0.0, le=1.0)
    max_gross_exposure: float = Field(gt=0.0)
    max_risk_per_trade_pct: float = Field(gt=0.0, le=1.0)
    max_daily_loss_pct: float = Field(gt=0.0, le=1.0)
    max_drawdown_pct: float = Field(gt=0.0, le=1.0)
    min_cash_reserve_pct: float = Field(ge=0.0, lt=1.0)
    max_participation_of_adv: float = Field(gt=0.0, le=1.0)
    max_positions: int = Field(gt=0)


class CostModelConfig(FrozenConfig):
    """Conservative execution cost assumptions used by backtests and simulation."""

    commission_per_share: float = Field(ge=0.0)
    fee_bps: float = Field(ge=0.0)
    half_spread_bps: float = Field(ge=0.0)
    impact_bps_at_full_participation: float = Field(ge=0.0)


class ExecutionPolicyConfig(FrozenConfig):
    """Approval and freshness policy for the execution gateway."""

    policy_version: str
    default_mode: ExecutionMode
    approval_ttl_seconds: int = Field(gt=0)
    broker_snapshot_max_age_seconds: int = Field(gt=0)
    require_human_approval_in: tuple[ExecutionMode, ...]


class BrokerCapabilityAllowlist(FrozenConfig):
    """Signed-off broker capabilities. Anything not listed here is refused even
    if the broker adapter reports support for it at runtime."""

    broker_name: str
    allowed_asset_classes: tuple[str, ...]
    allowed_order_types: tuple[str, ...]
    allowed_sides: tuple[str, ...] = ("BUY", "SELL")


class PlatformConfig(FrozenConfig):
    """Root configuration aggregate."""

    environment: str
    risk_limits: RiskLimitsConfig
    costs: CostModelConfig
    execution_policy: ExecutionPolicyConfig
    broker_allowlist: BrokerCapabilityAllowlist


_T = TypeVar("_T", bound=BaseModel)


def load_yaml_model(path: Path, model: type[_T]) -> _T:
    """Load one YAML file into a config model, failing loudly on any mismatch."""
    if not path.exists():
        raise ConfigurationError(f"config file not found: {path}")
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"config root must be a mapping: {path}")
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(f"schema validation failed for {path}: {exc}") from exc


def load_platform_config(config_root: Path, environment: str = "local") -> PlatformConfig:
    """Assemble the platform configuration from the standard ``config/`` layout."""
    return PlatformConfig(
        environment=environment,
        risk_limits=load_yaml_model(config_root / "risk_limits" / "default.yaml", RiskLimitsConfig),
        costs=load_yaml_model(config_root / "policies" / "costs.yaml", CostModelConfig),
        execution_policy=load_yaml_model(
            config_root / "policies" / "execution.yaml", ExecutionPolicyConfig
        ),
        broker_allowlist=load_yaml_model(
            config_root / "broker_capabilities" / "simulated.yaml", BrokerCapabilityAllowlist
        ),
    )
