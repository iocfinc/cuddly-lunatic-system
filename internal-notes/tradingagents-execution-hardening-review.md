# TradingAgents Execution Hardening Review

## Failure-Boundary Map

- `src/quant_researcher_desk/weekly_options_screener.py`
  - Discovery is already partially resilient at the plate level when OpenD rate-limits plate expansion.
  - The per-symbol screening lane was previously brittle because expiry lookup, expiry selection, underlying snapshot, chain fetch, contract snapshots, and contract filtering all shared one untyped failure path.
  - The hardened lane now treats symbol-level optionability and provider failures as structured skips and only fails the whole run when zero viable ranked contracts remain.

- `src/quant_researcher_desk/options_research.py`
  - The report builder is the shared evidence boundary for single-symbol packets and watchlist digests.
  - It now emits stage-specific `OptionsReportError` messages for empty expirations, empty chains, and missing contract snapshots so upper layers can normalize them consistently.

- `src/quant_researcher_desk/tradingagents_packet.py`
  - `build_desk_evidence_pack()` is the packet-side normalization boundary for symbol-level options evidence failures.
  - `run_tradingagents_debate_for_symbol()` is the packet-side normalization boundary for debate/backend failures.

- `scripts/send_tradingagents_watchlist_digest.py`
  - Watchlist digest policy belongs at the script/product layer, not in reusable harness code.
  - Evidence-pack failures and debate failures are both downgraded to symbol-level skips.
  - Digest publication remains allowed when at least one packet survives and a structured summary artifact is written beside the attachment.

## Provider-Contract Mismatches

- Fixture weekly providers return `[]` for non-optionable symbols, while live OpenD can raise `OptionsReportError("No option expirations returned for SYMBOL.")`.
  - Recovery policy: normalize both to the same `no_expirations` skip reason.

- The raw options research path previously collapsed several chain/snapshot failures into `No contract matched the requested option filters.`
  - Recovery policy: distinguish `empty_chain`, `missing_contract_snapshot`, and `no_contract_match`.

- Debate execution failures were previously whole-run aborts in the watchlist digest.
  - Recovery policy: normalize them to `debate_backend_failed` and skip the affected symbol while preserving successful packets.

## Shared Recovery Policy

- Multi-symbol flows
  - Skip and continue on `not_optionable`, `no_expirations`, `empty_chain`, `missing_underlying_snapshot`, `missing_contract_snapshot`, `no_contract_match`, `provider_rate_limited`, `provider_unreachable`, and `debate_backend_failed`.
  - Publish partial output when at least one symbol survives.
  - Fail only when zero symbols survive, with aggregated skip counts.

- Single-symbol packet
  - Stay fail-fast because there is no alternate symbol to continue with.
  - Use typed, stage-specific stderr so the operator can tell whether the failure was optionability, provider reachability, or the debate backend.

- Durability
  - Weekly screen JSON carries structured skip rows plus run-summary metadata.
  - Watchlist digest writes a companion summary JSON with attempted/succeeded/skip counts and per-symbol statuses.
