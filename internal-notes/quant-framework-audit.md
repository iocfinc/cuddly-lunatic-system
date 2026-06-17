# Quant Framework Audit

## Purpose

This note records the current options-research stack, what remains repo-owned, and why QuantLib is the selected closed-form pricing core during the migration.

## Current Runtime Stack

- Market data: `moomoo-api` via local Moomoo OpenD
- Closed-form pricing, Greeks, and IV: repo-owned Python implementation in `src/quant_researcher_desk/options_research.py`
- Monte Carlo scenario simulation: repo-owned Python implementation
- Weekly shortlist scoring: repo-owned workflow in `src/quant_researcher_desk/weekly_options_screener.py`
- Report rendering: repo-owned HTML plus PDF rendering in `src/quant_researcher_desk/reporting.py`
- Richer browser/PDF output: optional Chrome or Playwright-backed rendering when available

## Libraries Not Currently Used As The Core Runtime

These may appear in planning or future experiments, but they are not the current pricing/reporting source of truth:

- `pyfinance`
- `vollib`
- `numpy`
- `pandas`
- `scipy`
- `matplotlib`
- `plotly`

## Migration Decision

QuantLib is the chosen replacement for the repo-owned closed-form pricing core because:

1. The user wants a community-validated pricing and Greeks implementation rather than a permanently repo-owned math core.
2. QuantLib leaves room for broader quant models later without forcing a separate framework migration first.
3. The repo can keep market-data ingestion, weekly workflow logic, report writing, and Monte Carlo teaching views product-specific while delegating closed-form valuation to a well-known library.

## Boundary Decision

QuantLib replaces only the closed-form pricing, Greeks, and implied-volatility source of truth.

The following remain repo-owned for now:

- market-data ingestion and OpenD contracts
- weekly shortlist filters and ranking rules
- Monte Carlo path generation and scenario storytelling
- report rendering, delivery, and journaling workflows

## Migration Mode

The repo now uses a shadow-then-switch path:

- `legacy` keeps the current repo-owned closed-form engine
- `quantlib` uses the QuantLib-backed closed-form engine when the package is installed
- `--shadow-compare` computes a legacy-vs-QuantLib parity summary without changing the default scoring engine

QuantLib is not the default scoring engine until parity is consistently inside the configured tolerances.
