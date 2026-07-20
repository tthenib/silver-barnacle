"""Deterministic simulated broker.

Fills market orders at a caller-supplied reference price adjusted by the
shared cost model's slippage assumptions, maintains its own account state,
and supports scripted fault injection (rejects and ambiguous submissions) so
failure paths are as testable as happy paths.
"""

from __future__ import annotations

from collections import deque
from enum import StrEnum

from quant_platform.core.clock import Clock
from quant_platform.core.errors import AmbiguousBrokerResponseError, BrokerError
from quant_platform.core.metadata import new_id
from quant_platform.execution.broker import (
    AccountSnapshot,
    BrokerCapabilities,
    BrokerExecution,
    BrokerResponse,
    OrderRequest,
    SubmissionStatus,
)
from quant_platform.execution.intents import OrderSide


class InjectedFault(StrEnum):
    REJECT = "REJECT"
    AMBIGUOUS_THEN_FILLED = "AMBIGUOUS_THEN_FILLED"
    AMBIGUOUS_THEN_NOTHING = "AMBIGUOUS_THEN_NOTHING"


class SimulatedBroker:
    """In-memory broker with deterministic fills and scripted faults.

    ``AMBIGUOUS_THEN_FILLED`` simulates a lost acknowledgement where the order
    actually executed — the case idempotent reconciliation exists for.
    """

    def __init__(
        self,
        clock: Clock,
        initial_cash: float,
        slippage_bps: float = 2.5,
        account_alias: str = "sim-account",
    ) -> None:
        self._clock = clock
        self._cash = initial_cash
        self._positions: dict[str, float] = {}
        self._slippage_bps = slippage_bps
        self._account_alias = account_alias
        self._executions: list[BrokerExecution] = []
        self._seen_client_order_ids: set[str] = set()
        self._reference_prices: dict[str, float] = {}
        self._fault_queue: deque[InjectedFault] = deque()

    # -- test/simulation controls -------------------------------------------------

    def set_reference_price(self, symbol: str, price: float) -> None:
        if price <= 0:
            raise ValueError("reference price must be positive")
        self._reference_prices[symbol] = price

    def inject_fault(self, fault: InjectedFault) -> None:
        """Queue a fault consumed by the next ``submit_order`` call."""
        self._fault_queue.append(fault)

    # -- BrokerGateway protocol ---------------------------------------------------

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            broker_name="simulated",
            account_alias=self._account_alias,
            asset_classes=("EQUITY",),
            order_types=("MARKET",),
            sides=("BUY", "SELL"),
            discovered_at_utc=self._clock.now(),
        )

    def account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            account_alias=self._account_alias,
            cash=self._cash,
            buying_power=self._cash,
            positions=dict(self._positions),
            open_order_count=0,
            taken_at_utc=self._clock.now(),
        )

    def submit_order(self, request: OrderRequest) -> BrokerResponse:
        if request.account_alias != self._account_alias:
            raise BrokerError(f"unknown account: {request.account_alias}")
        # Broker-side idempotency: a duplicate client order ID is not re-executed.
        if request.client_order_id in self._seen_client_order_ids:
            return BrokerResponse(
                status=SubmissionStatus.REJECTED,
                reason="duplicate client_order_id",
            )

        fault = self._fault_queue.popleft() if self._fault_queue else None
        if fault is InjectedFault.REJECT:
            return BrokerResponse(status=SubmissionStatus.REJECTED, reason="injected reject")
        if fault is InjectedFault.AMBIGUOUS_THEN_FILLED:
            # The order executes, but the caller never learns of it.
            self._seen_client_order_ids.add(request.client_order_id)
            self._fill(request)
            raise AmbiguousBrokerResponseError("injected: response lost after execution")
        if fault is InjectedFault.AMBIGUOUS_THEN_NOTHING:
            raise AmbiguousBrokerResponseError(
                "injected: response lost, order never reached broker"
            )

        self._seen_client_order_ids.add(request.client_order_id)
        broker_order_id = self._fill(request)
        return BrokerResponse(status=SubmissionStatus.ACKNOWLEDGED, broker_order_id=broker_order_id)

    def executions(self) -> list[BrokerExecution]:
        return list(self._executions)

    # -- internals ----------------------------------------------------------------

    def _fill(self, request: OrderRequest) -> str:
        reference = self._reference_prices.get(request.symbol)
        if reference is None:
            raise BrokerError(f"no reference price for {request.symbol}")
        adjustment = self._slippage_bps / 10_000.0
        fill_price = reference * (
            1.0 + adjustment if request.side is OrderSide.BUY else 1.0 - adjustment
        )
        signed_quantity = request.quantity if request.side is OrderSide.BUY else -request.quantity
        cost = signed_quantity * fill_price
        if request.side is OrderSide.BUY and cost > self._cash:
            raise BrokerError("insufficient buying power")
        held = self._positions.get(request.symbol, 0.0)
        if request.side is OrderSide.SELL and request.quantity > held + 1e-9:
            raise BrokerError("insufficient position to sell")
        self._cash -= cost
        new_position = held + signed_quantity
        if abs(new_position) < 1e-9:
            self._positions.pop(request.symbol, None)
        else:
            self._positions[request.symbol] = new_position
        broker_order_id = new_id("simorder")
        self._executions.append(
            BrokerExecution(
                broker_order_id=broker_order_id,
                client_order_id=request.client_order_id,
                symbol=request.symbol,
                side=request.side,
                filled_quantity=request.quantity,
                average_price=fill_price,
                timestamp_utc=self._clock.now(),
            )
        )
        return broker_order_id
