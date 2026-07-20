"""Strategy registry and lifecycle.

Every strategy instance is registered with an explicit lifecycle state
(specification section 9). The registry is the single authority on which
strategies may participate in a given context: a backtest may run anything at
or past RESEARCH; simulation portfolios draw only from validated states.
Promotion and demotion are recorded — silent state changes are not possible.
"""

from __future__ import annotations

from enum import StrEnum

from quant_platform.core.audit import AuditLedger
from quant_platform.core.errors import StateTransitionError
from quant_platform.strategies.base import Strategy


class StrategyLifecycle(StrEnum):
    IDEA = "IDEA"
    RESEARCH = "RESEARCH"
    BACKTESTED = "BACKTESTED"
    WALK_FORWARD_VALIDATED = "WALK_FORWARD_VALIDATED"
    STRESS_TESTED = "STRESS_TESTED"
    PAPER = "PAPER"
    LIMITED_LIVE = "LIMITED_LIVE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


#: Forward promotion order; a strategy may only be promoted one step at a
#: time and only along this path. PAUSED/RETIRED/REJECTED are reachable from
#: any state (demotion is always allowed — risk reduction needs no ceremony).
_PROMOTION_PATH = [
    StrategyLifecycle.IDEA,
    StrategyLifecycle.RESEARCH,
    StrategyLifecycle.BACKTESTED,
    StrategyLifecycle.WALK_FORWARD_VALIDATED,
    StrategyLifecycle.STRESS_TESTED,
    StrategyLifecycle.PAPER,
    StrategyLifecycle.LIMITED_LIVE,
    StrategyLifecycle.ACTIVE,
]

_TERMINAL_OR_HOLD = {
    StrategyLifecycle.PAUSED,
    StrategyLifecycle.RETIRED,
    StrategyLifecycle.REJECTED,
}

#: Minimum lifecycle state required to participate in a context.
SIMULATION_ELIGIBLE = {
    StrategyLifecycle.BACKTESTED,
    StrategyLifecycle.WALK_FORWARD_VALIDATED,
    StrategyLifecycle.STRESS_TESTED,
    StrategyLifecycle.PAPER,
    StrategyLifecycle.LIMITED_LIVE,
    StrategyLifecycle.ACTIVE,
}


class StrategyRegistry:
    """Owns strategy instances and their lifecycle states."""

    def __init__(self, audit: AuditLedger) -> None:
        self._audit = audit
        self._strategies: dict[str, Strategy] = {}
        self._states: dict[str, StrategyLifecycle] = {}

    def register(
        self, strategy: Strategy, state: StrategyLifecycle = StrategyLifecycle.IDEA
    ) -> None:
        key = self._key(strategy)
        if key in self._strategies:
            raise ValueError(f"strategy already registered: {key}")
        self._strategies[key] = strategy
        self._states[key] = state
        self._audit.append(
            "strategy.registered",
            correlation_id=key,
            actor="strategy_registry",
            payload={"state": state, "spec_hash": strategy.spec.spec_hash()},
        )

    def state_of(self, strategy: Strategy) -> StrategyLifecycle:
        return self._states[self._key(strategy)]

    def promote(self, strategy: Strategy, to_state: StrategyLifecycle, evidence: str) -> None:
        """Advance one lifecycle step with a recorded evidence reference.

        ``evidence`` names the artifact justifying promotion (backtest report
        ID, walk-forward report ID, …). Promotion without evidence is invalid.
        """
        if not evidence.strip():
            raise StateTransitionError("promotion requires an evidence reference")
        key = self._key(strategy)
        current = self._states[key]
        if to_state in _TERMINAL_OR_HOLD:
            raise StateTransitionError(f"use demote() to move to {to_state}")
        if current in _TERMINAL_OR_HOLD:
            raise StateTransitionError(f"cannot promote from {current}")
        current_idx = _PROMOTION_PATH.index(current)
        target_idx = _PROMOTION_PATH.index(to_state)
        if target_idx != current_idx + 1:
            raise StateTransitionError(
                f"promotion must be stepwise: {current} -> {to_state} is not adjacent"
            )
        self._states[key] = to_state
        self._audit.append(
            "strategy.promoted",
            correlation_id=key,
            actor="strategy_registry",
            payload={"from": current, "to": to_state, "evidence": evidence},
        )

    def demote(self, strategy: Strategy, to_state: StrategyLifecycle, reason: str) -> None:
        """Move to any earlier or hold state; always allowed, always recorded."""
        key = self._key(strategy)
        current = self._states[key]
        if to_state not in _TERMINAL_OR_HOLD and _PROMOTION_PATH.index(
            to_state
        ) >= _PROMOTION_PATH.index(current):
            raise StateTransitionError(f"demotion target {to_state} is not below {current}")
        self._states[key] = to_state
        self._audit.append(
            "strategy.demoted",
            correlation_id=key,
            actor="strategy_registry",
            payload={"from": current, "to": to_state, "reason": reason},
        )

    def eligible_for_simulation(self) -> list[Strategy]:
        return [s for k, s in self._strategies.items() if self._states[k] in SIMULATION_ELIGIBLE]

    @staticmethod
    def _key(strategy: Strategy) -> str:
        return f"{strategy.spec.strategy_id}@{strategy.spec.version}"
