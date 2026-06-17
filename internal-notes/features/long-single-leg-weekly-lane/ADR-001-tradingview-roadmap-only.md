# ADR-001: TradingView Is Roadmap-Only For The Weekly Lane

## Status

Accepted

## Context

TradingView was considered because it already exposes strong charting and options workflow UX, but it is not an API-first or agent-friendly implementation target for this repo today.

## Decision

- Do not integrate TradingView into the current weekly implementation path.
- Keep TradingView as a roadmap and parity reference for future UX and workflow ideas.
- Learn the Moomoo/OpenD surface first before widening the tool boundary.

## Consequences

- Positive:
  - the production lane stays on a verified, automatable data source
  - implementation complexity stays bounded
- Negative:
  - some UX and built-in workflow features remain aspirational rather than available now
