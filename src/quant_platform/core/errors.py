"""Platform exception hierarchy.

Every raised error must make the failure mode explicit. Callers are expected
to fail closed: an unclassified error is treated as a reason to stop, never a
reason to guess.
"""

from __future__ import annotations


class PlatformError(Exception):
    """Base class for all platform errors."""


class ConfigurationError(PlatformError):
    """Configuration is missing, malformed, or fails schema validation."""


class DataValidationError(PlatformError):
    """Data failed a validation check and may not be used for the requested purpose."""


class PolicyViolationError(PlatformError):
    """An action was attempted that the active policy forbids."""


class StateTransitionError(PlatformError):
    """An entity was asked to make a transition its state machine does not allow."""


class ApprovalError(PlatformError):
    """An approval record is missing, expired, or does not match the intent."""


class BrokerError(PlatformError):
    """The broker adapter returned a definitive error."""


class AmbiguousBrokerResponseError(PlatformError):
    """The broker response was lost or unclear; the intent must be reconciled,
    never blindly retried."""


class AuditIntegrityError(PlatformError):
    """The audit ledger hash chain failed verification."""
