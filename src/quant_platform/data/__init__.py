"""Data plane: provider adapters, validation, and the point-in-time store.

Data enters untrusted, is validated by :mod:`quant_platform.data.validation`,
and only then becomes eligible for research or backtesting. The store serves
history strictly as-of a date so downstream consumers cannot look ahead.
"""
