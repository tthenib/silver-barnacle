# tests

Three categories, all required before any component ships:

1. **Unit** — indicators, sizing arithmetic, broker-constraint handling.
2. **Property-based** — the load-bearing invariants, fuzzed:
   - `approved_lots <= requested_lots` for every input (risk engine can only subtract)
   - signals are bit-identical when future bars are mutated (no look-ahead)
   - sizing never returns a lot size the broker would reject
3. **Parity** — Python vs MQL5 signal agreement, 100% on direction.
