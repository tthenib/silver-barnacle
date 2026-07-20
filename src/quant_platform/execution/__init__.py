"""Execution plane: signed intents, approvals, gateway, broker adapters.

Only the execution gateway may request broker action, and only for a signed,
approved, unexpired intent against a fresh broker snapshot. Ambiguity becomes
``BLOCKED_PENDING_RECONCILIATION`` — never a blind retry.
"""
