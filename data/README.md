# data

Raw market data is **immutable** and gitignored; only the manifest is tracked.

Each dataset carries a manifest recording source, symbol, timeframe, date range, row count,
checksum, and download timestamp. A result whose manifest cannot be reproduced is not
reportable ([BACKTESTING_PROTOCOL.md](../BACKTESTING_PROTOCOL.md) §8).

Sources:
- **Research:** exchange OHLCV (Binance/Coinbase) — long history, reproducible
- **Production validation:** MT5 broker bars and ticks — what the EA actually trades

The two must be reconciled (EXP-0001) before exchange-data results are trusted.
