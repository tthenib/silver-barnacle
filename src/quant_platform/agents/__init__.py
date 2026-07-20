"""Agent plane: propose-only AI agent contracts and evaluation harness.

Agents produce schema-validated, cited, uncertainty-bearing proposals; they
never own prices, portfolio state, policy, or broker access. The LLM binding
is intentionally absent at this layer — see ADR-0004.
"""
