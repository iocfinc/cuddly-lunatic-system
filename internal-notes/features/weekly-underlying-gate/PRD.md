# PRD: Weekly Underlying Gate Trace

## Goal

Make the weekly options screen traceable from universe discovery through shortlist publication while preserving the current stock-first methodology and current artifacts.

## Scope

- In scope:
  - gate-stage trace capture inside the weekly screener
  - additive JSON fields for gate results and gate summary
  - one gate-trace section in weekly HTML
  - run-level Notion summary of gate counts and representative pass/fail reasons
- Out of scope:
  - new vendors
  - TradingView automation
  - new trading strategies
  - earnings or IV percentile policy redesign

## Inputs

- weekly universe from Moomoo plates
- daily bars for stock context
- option expirations, chains, and snapshots
- existing weekly screen config and pricing engine selection

## Outputs

- `WeeklyScreenResult.gate_results`
- `WeeklyScreenResult.gate_summary`
- JSON artifact fields for the same structures
- weekly HTML gate-trace section
- run-level Notion gate summary

## Success Criteria

- Functional:
  - every attempted symbol has a final `shortlist_outcome` gate decision
  - symbols that fail stock context, expiry, or contract quality have stage-specific failures
- Quality:
  - existing payload keys remain intact
  - current ranking logic does not change
- Operational:
  - fixture-backed weekly script still writes CSV, JSON, HTML, and PDF
  - Notion sync remains additive

## Risks

- Data risk:
  - stage naming or reason-code drift between outputs
- Interpretation risk:
  - gate trace could be mistaken for a new scoring model if wording is vague
- Delivery risk:
  - run-level payloads could become noisier if representative reasons are not kept concise
