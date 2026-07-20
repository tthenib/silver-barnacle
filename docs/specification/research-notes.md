# Research Notes — Quantitative Trading Platform Specification

## Scope and integration status

- The current task configuration contains **no configured Robinhood connector**. The final document will therefore specify an adapter and explicit onboarding/authorization boundary rather than claim a live session connection.
- Robinhood’s official Agentic Trading material states that the Robinhood Trading MCP can provide read access to Robinhood account data, positions, balances, transactions, order history, watchlists, and scans. Trades are limited to a dedicated Robinhood Agentic account. The product is described as beta support for **equities only** at launch; other assets should be modeled as future capabilities, not assumptions.
- Robinhood’s official material emphasizes that an agent may place orders without direct confirmation if configured to do so, that the account holder remains responsible, and that dedicated funding, real-time activity visibility, notifications, and the ability to disconnect are core controls. The specification will impose additional platform-side human approval and risk gates by default.

## Data-source findings

- SEC developer resources state that company submissions and extracted XBRL data are available through RESTful APIs on data.sec.gov in JSON format. The SEC requests efficient, moderated access and gives a current fair-access guideline of no more than 10 requests per second per user. The design will require a throttled, cache-first EDGAR client with provenance and retry behavior.
- The Federal Reserve Bank of St. Louis states that the FRED API provides access to both FRED and ALFRED data and supports programmatic retrieval using JSON/XML over HTTPS. The design will use vintage-aware macro data where historical evaluation requires it, rather than backfilling with revisions.
- OpenBB documentation describes its Open Data Platform as a Python-based, provider-abstracted toolset for integrating public, proprietary, and licensed data sources. It will be presented as an optional normalization layer rather than a guaranteed source of real-time institutional data.

## Sources

1. Robinhood, “Agentic Trading overview,” https://robinhood.com/us/en/support/articles/agentic-trading-overview/
2. Robinhood, “Robinhood is Now Open to Agents,” May 27, 2026, https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/
3. Robinhood, “Agentic Trading,” https://robinhood.com/us/en/agentic-trading
4. U.S. Securities and Exchange Commission, “Developer Resources,” https://www.sec.gov/about/developer-resources
5. Federal Reserve Bank of St. Louis, “FRED API Overview,” https://fred.stlouisfed.org/docs/api/fred/overview.html
6. OpenBB, “Open Data Platform Documentation,” https://docs.openbb.co/odp
