"""Provider-neutral broker gateway contract.

A broker adapter reports its capabilities at startup; the platform exposes
only the intersection of the report and the reviewed allowlist
(config/broker_capabilities/). The contract is deliberately minimal — the
future Robinhood Trading MCP adapter implements exactly this protocol behind
capability discovery, without strategies or agents ever importing it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.core.config import BrokerCapabilityAllowlist
from quant_platform.core.errors import PolicyViolationError
from quant_platform.execution.intents import OrderSide


class BrokerCapabilities(BaseModel):
    """What a broker adapter reports it can currently do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_name: str
    account_alias: str
    asset_classes: tuple[str, ...]
    order_types: tuple[str, ...]
    sides: tuple[str, ...]
    discovered_at_utc: datetime


class AccountSnapshot(BaseModel):
    """Fresh broker-side account state captured immediately before submission."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_alias: str
    cash: float
    buying_power: float
    positions: dict[str, float]
    open_order_count: int
    taken_at_utc: datetime


class SubmissionStatus(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"


class OrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    client_order_id: str  # the intent fingerprint — broker-side idempotency key
    account_alias: str
    symbol: str
    side: OrderSide
    quantity: float = Field(gt=0)
    order_type: str


class BrokerResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SubmissionStatus
    broker_order_id: str | None = None
    reason: str = ""


class BrokerExecution(BaseModel):
    """A broker-side execution record used by reconciliation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    filled_quantity: float
    average_price: float
    timestamp_utc: datetime


class BrokerGateway(Protocol):
    """The only interface through which the platform touches a broker."""

    def capabilities(self) -> BrokerCapabilities: ...

    def account_snapshot(self) -> AccountSnapshot: ...

    def submit_order(self, request: OrderRequest) -> BrokerResponse:
        """Submit an order. May raise :class:`AmbiguousBrokerResponseError` when the
        outcome is unknown (timeout, lost response) — callers must reconcile,
        never retry blindly."""
        ...

    def executions(self) -> list[BrokerExecution]:
        """All executions the broker reports for this account (for reconciliation)."""
        ...


class VerifiedCapabilities:
    """The intersection of reported capabilities and the reviewed allowlist."""

    def __init__(self, reported: BrokerCapabilities, allowlist: BrokerCapabilityAllowlist) -> None:
        if reported.broker_name != allowlist.broker_name:
            raise PolicyViolationError(
                f"capability allowlist is for '{allowlist.broker_name}', "
                f"broker reports '{reported.broker_name}'"
            )
        self.broker_name = reported.broker_name
        self.account_alias = reported.account_alias
        self.asset_classes = frozenset(reported.asset_classes) & frozenset(
            allowlist.allowed_asset_classes
        )
        self.order_types = frozenset(reported.order_types) & frozenset(
            allowlist.allowed_order_types
        )
        self.sides = frozenset(reported.sides) & frozenset(allowlist.allowed_sides)

    def assert_supports(self, asset_class: str, order_type: str, side: str) -> None:
        missing = []
        if asset_class not in self.asset_classes:
            missing.append(f"asset class '{asset_class}'")
        if order_type not in self.order_types:
            missing.append(f"order type '{order_type}'")
        if side not in self.sides:
            missing.append(f"side '{side}'")
        if missing:
            raise PolicyViolationError(
                f"capability not verified for {self.broker_name}: {', '.join(missing)}"
            )
