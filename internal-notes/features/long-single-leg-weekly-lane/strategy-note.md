# Strategy Note: Deep-Research Decisions Converted To Repo Rules

## Locked Decisions

- Strategy scope is direct options trading for resale, not hedging.
- OpenD stays the production market-data source for now.
- TradingView is roadmap-only; use it as a reference for product direction, not as an integration target.
- Repo-owned notes inside `internal-notes/` are the canonical bridge between deep-research conclusions and local implementation.

## Working Interpretation

- The weekly lane should rank contracts that are practical to resell later.
- Liquidity, delta band, DTE fit, and event visibility matter more than theoretical cheapness alone.
- Event timing should reduce confidence when unknown and reduce score when the catalyst sits inside the holding window.
