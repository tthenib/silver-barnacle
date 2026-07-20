"""Cross-cutting primitives shared by every domain package.

Nothing in ``core`` may import from any other ``quant_platform`` package;
it is the bottom of the dependency graph.
"""
