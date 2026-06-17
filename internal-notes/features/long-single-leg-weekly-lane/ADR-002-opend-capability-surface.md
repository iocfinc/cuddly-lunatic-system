# ADR-002: Verified OpenD Capability Surface For The Weekly Lane

## Status

Accepted

## Context

The weekly lane depends on a specific subset of the Moomoo OpenD wrapper. The repo needs a clear rule for which fields are verified now, which are only safe when present in snapshot rows, and which remain unsupported for scoring.

## Decision

- Treat these wrapper capabilities as verified now:
  - plate list
  - plate constituents
  - daily bars
  - option expirations
  - option chain rows
  - market snapshots
  - underlying snapshot
  - watchlist groups and watchlist securities
- Treat these as usable only when present in snapshot rows:
  - implied volatility
  - delta
  - volume
  - open interest
- Treat these as unsupported for scoring until the wrapper exposes and tests them explicitly:
  - bid/ask spread
  - theoretical price from provider fields
  - event calendar
  - extra Greeks beyond the currently verified surface

## Consequences

- Positive:
  - ranking logic stays tied to verified repo-owned data
  - unsupported assumptions become visible roadmap items instead of hidden dependencies
- Negative:
  - spread quality and richer catalyst logic remain proxy-based until the wrapper grows
