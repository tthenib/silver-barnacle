"""Risk plane: deterministic limits, circuit breakers, and the kill switch.

Risk can block but never silently loosen a limit; there is no code path by
which an agent, strategy, or optimizer widens anything here.
"""
