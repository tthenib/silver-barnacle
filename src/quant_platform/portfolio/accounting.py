"""Deterministic portfolio accounting.

Tracks cash and positions, values them against supplied prices, and exposes
the exposure arithmetic the risk engine and allocator rely on. Accounting is
authoritative state — no agent or strategy may mutate it directly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Position(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    quantity: float
    average_cost: float = Field(ge=0)


class PortfolioState(BaseModel):
    """Immutable snapshot of holdings; mutations produce a new snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cash: float
    positions: dict[str, Position] = Field(default_factory=dict)

    def equity(self, prices: dict[str, float]) -> float:
        """Total account value: cash plus marked positions."""
        return self.cash + sum(
            pos.quantity * prices[symbol] for symbol, pos in self.positions.items()
        )

    def weight_of(self, symbol: str, prices: dict[str, float]) -> float:
        equity = self.equity(prices)
        if equity <= 0:
            return 0.0
        position = self.positions.get(symbol)
        if position is None:
            return 0.0
        return position.quantity * prices[symbol] / equity

    def gross_exposure(self, prices: dict[str, float]) -> float:
        equity = self.equity(prices)
        if equity <= 0:
            return 0.0
        return (
            sum(abs(pos.quantity) * prices[symbol] for symbol, pos in self.positions.items())
            / equity
        )

    def apply_fill(
        self, symbol: str, quantity_delta: float, price: float, total_cost: float
    ) -> PortfolioState:
        """Return a new state reflecting a fill.

        ``total_cost`` is the all-in friction (commission + fees + slippage
        already embedded in ``price`` stays in price; explicit costs are
        deducted from cash separately so cost drag is visible in accounting).
        """
        positions = dict(self.positions)
        existing = positions.get(symbol)
        new_quantity = (existing.quantity if existing else 0.0) + quantity_delta
        if abs(new_quantity) < 1e-9:
            positions.pop(symbol, None)
        else:
            if existing is None or existing.quantity * new_quantity <= 0 < abs(new_quantity):
                # Opening or flipping: basis resets to this fill's price.
                average_cost = price
            elif abs(new_quantity) > abs(existing.quantity):
                # Increasing an existing position: blend the basis.
                average_cost = (
                    existing.average_cost * abs(existing.quantity) + price * abs(quantity_delta)
                ) / abs(new_quantity)
            else:
                # Reducing: basis unchanged.
                average_cost = existing.average_cost
            positions[symbol] = Position(
                symbol=symbol, quantity=new_quantity, average_cost=average_cost
            )
        new_cash = self.cash - quantity_delta * price - total_cost
        return PortfolioState(cash=new_cash, positions=positions)
