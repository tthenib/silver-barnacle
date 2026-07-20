"""Observability plane: metrics registry.

A minimal, dependency-free registry; the export format is the contract, so a
Prometheus or OTLP backend can replace the in-memory implementation without
touching instrumented call sites.
"""
