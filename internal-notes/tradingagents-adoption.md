# TradingAgents Adoption Note

## Status

TradingAgents is adopted in `naval-analyst` as an optional research-debate adapter, not as a second application and not as an execution system.

The implementation in this repository is bounded around two repo-owned types:

- `DeskEvidencePack` defines the input boundary that remains authoritative inside `naval-analyst`.
- `DecisionPacket` defines the output boundary that is safe to render to PDF and send through Telegram.

## Provenance

As of 2026-05-03, the official upstream source is `TauricResearch/TradingAgents`.

- Source repository: `https://github.com/TauricResearch/TradingAgents`
- Suggested repo ref for local installation: `refs/tags/v0.2.4`
- Upstream package path is source-install oriented (`pip install .` from the cloned repo), so this repository does not hard-wire TradingAgents into the default dependency set.

This repo stays fixture-first until the user explicitly installs and validates the optional upstream dependency in a local environment.

## Architecture Boundary

`naval-analyst` stays the source of truth for:

- underlying snapshot
- options-chain selection
- IV/HV context
- scenario outputs
- catalyst and earnings context
- sector context

TradingAgents may consume that packet and return a debate result, but it does not own market-data truth inside this repo.

The user-facing output is normalized to research-only labels:

- `Research Candidate`
- `Watchlist`
- `Reject`
- `Needs Human Review`

User-facing captions and rendered packets must not leak `BUY`, `SELL`, `EXECUTE`, or broker-style submission language.

## Config

Optional env/config seams:

- `TRADINGAGENTS_ENABLED`
- `TRADINGAGENTS_REF`
- `TRADINGAGENTS_LLM_PROVIDER`
- `TRADINGAGENTS_LLM_BACKEND`
- `TRADINGAGENTS_CODEX_MODEL`
- `TRADINGAGENTS_CODEX_PROFILE`
- `TRADINGAGENTS_RESULTS_DIR`
- `TRADINGAGENTS_CACHE_DIR`
- `TRADINGAGENTS_MEMORY_DIR`
- `TRADINGAGENTS_ALLOW_EXECUTION`

Defaults are repo-local and ignored:

- `data/tradingagents/results`
- `data/tradingagents/cache`
- `data/tradingagents/memory`
- `reports/tradingagents`

No TradingAgents state should write to `~/.tradingagents` from this repo-owned flow.

## Current Flow

Fixture and dry-run path:

```sh
uv --cache-dir .uv-cache run python scripts/send_tradingagents_packet.py --dry-run --fixture --symbol US.TEST --report-format pdf
```

If the optional live adapter is enabled and installed locally, the same script can run without `--fixture`. When the dependency or provider credentials are missing, it should fail with exact actionable messaging and leave the existing options or sector flows untouched.

The debate step now supports two backend modes behind a repo-local decorator seam:

- `api`: use the upstream TradingAgents graph and its configured LLM provider
- `codex`: use headless `codex exec` with a JSON schema contract, defaulting to `gpt-5.4`

## Verified Closure

As of 2026-06-17, the TradingAgents packet and watchlist backlog items are closed in Linear. The adapter remains fixture-first by default, with live runs gated behind explicit local enablement.

Validation uses repo-local state and cache paths. The live-failure smoke path forces a closed OpenD port so a developer's local `.env` cannot accidentally depend on an active OpenD session during CI-style checks.

## Non-Goal

This repository will not add broker connectivity, order submission, or automated execution as part of the TradingAgents adoption path.
