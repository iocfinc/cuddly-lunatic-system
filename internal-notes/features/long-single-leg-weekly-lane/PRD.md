# PRD: Long Single-Leg Weekly Lane

## Goal

Improve the weekly options workflow for one explicit v1 strategy lane: buy a single-leg call or put, then sell the contract later.

## Scope

- In scope:
  - stock-first weekly screening for aligned CALL or PUT candidates
  - resale-oriented ranking with explicit score components
  - event-risk seam with `low`, `medium`, `high`, and `unknown` handling
  - packet and tear-sheet wording for contract resale rather than exercise
  - verified OpenD capability contract for the current repo wrapper
- Out of scope:
  - hedging workflows
  - stock exercise or assignment planning
  - short premium and multi-leg strategies
  - TradingView integration

## Product Rules

- Strategy scope is `long_single_leg_resale`.
- The lane is options-only and assumes the contract will be sold later, not exercised into stock.
- Stock-first context is a hard gate: bullish names can only surface CALLs, bearish names can only surface PUTs.
- Event policy is `flag and penalize, not exclude`.
- Missing event data is `unknown risk`, not `safe`.

## Inputs

- OpenD plates and plate constituents
- daily bars for trend regime
- option expirations, chain rows, and snapshots
- optional event provider context

## Outputs

- weekly shortlist rows with score components and event fields
- contract-level research reports with resale, exit-quality, and event-risk summaries
- packet overview buckets for clean swing candidates versus flagged event-risk names

## Success Criteria

- Functional:
  - shortlist contracts expose `directional_fit_score`, `exit_quality_score`, `valuation_context_score`, and `event_risk_score`
  - packet and tear sheets explain the resale thesis without drifting into execution language
  - missing event data stays visible as uncertainty
- Quality:
  - current JSON/CSV/HTML/PDF flows remain backward-compatible at the top level
  - `composite_score` remains the published top-level score
- Operational:
  - fixture-backed weekly script still runs end to end
  - OpenD assumptions are documented as verified, conditional, or unsupported
