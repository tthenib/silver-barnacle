"""Strategy framework: pure, versioned signal logic.

A strategy converts point-in-time history into :class:`SignalProposal`s.
It never sizes positions, never checks risk, and never talks to a broker —
those responsibilities belong to portfolio, risk, and execution respectively.
"""
