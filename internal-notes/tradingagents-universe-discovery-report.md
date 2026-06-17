# TradingAgents Universe Discovery Report

## Purpose

This note answers a product question that sits underneath the current TradingAgents adoption work in `naval-analyst`:

- Does the trading agent know how to find what to analyze?
- Can it screen for stocks or industries outside the names the user already knows?

Short answer: **not today**. The current implementation is an **analysis and ranking layer over a candidate set**, not a true **market discovery or screening engine**.

## Executive Summary

Today, the TradingAgents flow in this repo starts only after a symbol list already exists.

That symbol list can come from:

1. an explicit user-provided ticker or symbol list, or
2. an existing Moomoo OpenD watchlist group.

The system can then:

- build a repo-owned evidence pack,
- run the bounded TradingAgents debate,
- normalize the outcome into research-only labels,
- render a packet or watchlist digest.

What it **cannot** currently do is:

- scan the broader market by itself,
- discover sectors or industries that deserve attention,
- rank the full opportunity set across unknown names,
- tell the user "you should be looking at this area" without a prior seed universe.

That means the current product solves **"analyze what I already suspect"**, not yet **"tell me what I should care about."**

## What The Current System Actually Does

### Single-symbol packet flow

The packet flow is centered on a single `symbol` request and a repo-owned `DeskEvidencePack`.

Relevant implementation:

- `src/quant_researcher_desk/tradingagents_packet.py`
- `scripts/send_tradingagents_packet.py`

This is a bounded debate engine. It consumes an already selected symbol and returns a research packet.

### Watchlist digest flow

There is also a watchlist digest path:

- `scripts/send_tradingagents_watchlist_digest.py`
- `src/quant_researcher_desk/tradingagents_watchlist.py`

This sounds like discovery, but the current source universe is still narrow:

1. If `--symbols` is passed, it uses those symbols directly.
2. If `--symbols` is not passed, it reads names from the user's existing OpenD watchlist groups.

That means the system is **ranking a preselected list**, not screening the open market.

## Evidence From The Current Implementation

### The watchlist digest does not generate a universe

In `scripts/send_tradingagents_watchlist_digest.py`, the flow is:

- parse `--symbols`, or
- call `collect_watchlist_symbols(...)`, which reads OpenD user watchlist groups,
- then analyze those symbols up to `max_candidates`.

So the discovery boundary is external:

- user input, or
- names the user already saved in OpenD.

The TradingAgents layer starts only after those names already exist.

### The current watchlist path is a filter and ranker

`src/quant_researcher_desk/tradingagents_watchlist.py`:

- normalizes watchlist symbols,
- builds `WatchlistSecurity` entries,
- ranks `DecisionPacket`s by label and packet metrics,
- renders a digest.

That is useful, but it is **post-universe processing**, not **universe generation**.

### The packet layer is symbol-first by design

`TradingAgentsPacketRequest` currently requires a `symbol`.

That is the right shape for a packet generator, but it also makes the current boundary obvious:

- the repo has a strong per-symbol research path,
- it does not yet have a first-class "find candidates" path upstream of that.

## Product Gap

The missing layer is **candidate discovery**.

Without that layer, the user is constrained by prior awareness:

- "Analyze NVDA"
- "Analyze TSM"
- "Analyze this watchlist"

That is valuable, but it does not solve:

- "What sector is setting up?"
- "Which names have unusual opportunity today?"
- "What am I missing outside my current watchlist?"

This is the difference between:

- a **research memo engine**, and
- a **research desk with market discovery**.

## Why This Matters

From a product perspective, discovery is where a large share of the value sits.

If the system only analyzes names the user already knows, it improves discipline but not idea generation.

A stronger desk should do both:

1. **discover** the candidate set
2. **analyze** the best candidates deeply

Right now, `naval-analyst` is materially stronger on step 2 than step 1.

## What A Real Screener Would Need

To move from analysis-only into discovery, the product needs an explicit upstream workflow before TradingAgents debate.

### Stage 1: Universe construction

Build and maintain a candidate universe from one or more of:

- user watchlists
- sector/industry universes
- earnings calendars
- unusual options activity
- liquidity filters
- volatility dislocations
- price/momentum or mean-reversion scans
- market-cap and geography buckets

This repo already has adjacent ingredients:

- options research
- sector mapping artifacts in `docs/sector-industry-universe.md`
- OpenD integration

But they are not yet composed into a general-purpose discovery engine.

### Stage 2: Cheap screening

Run low-cost heuristics over the universe to narrow it down:

- option liquidity
- spread quality
- IV vs HV gap
- upcoming catalyst timing
- earnings proximity
- sector relevance
- minimum tradability thresholds

This stage should be deterministic and cheap. It should not require the full TradingAgents debate for every name.

### Stage 3: Prioritization

Rank the screened names into a shortlist such as:

- top research candidates
- watchlist names
- rejects
- needs manual review

Only after that should the desk spend expensive LLM or debate budget.

### Stage 4: Deep analysis

Feed only the shortlisted names into the existing `DecisionPacket` / TradingAgents path.

That preserves the current architecture cleanly:

- deterministic screening first,
- bounded debate second.

## Recommended Product Direction

The right move is **not** to turn TradingAgents itself into the screener.

TradingAgents should remain the bounded debate and synthesis layer.

The screener should live one level upstream inside `naval-analyst`, using repo-owned market-data and ranking logic.

Recommended architecture:

1. `UniverseProvider`
   - returns candidate symbols from watchlists, sectors, earnings, or configured universes
2. `ScreeningProvider`
   - applies deterministic filters and scoring
3. `ShortlistBuilder`
   - selects the top names for deeper work
4. existing `TradingAgentsPacketRequest` / `DecisionPacket`
   - performs the deep research debate only on shortlisted symbols
5. `WatchlistDigest`
   - publishes the ranked output

This keeps the product-specific logic in `naval-analyst` and avoids overloading upstream TradingAgents with discovery duties it was not built for.

## Concrete Answer To The Original Question

### Is the trading agent capable of finding or screening stocks instead?

**Partially, but only in a very limited sense today.**

It can:

- analyze a ticker you provide,
- analyze a list of symbols you provide,
- analyze symbols pulled from an existing OpenD watchlist group,
- rank those names into a digest.

It cannot yet:

- scan the broader market independently,
- generate its own investable universe from scratch,
- discover sectors or names outside your existing seeded list in a systematic way.

So the current answer is:

**it is a candidate analyzer and ranker, not yet a full market discovery engine.**

## Product Implication

If the desired user experience is:

> "Tell me what I should look at today, even if I have never thought of the ticker."

then the next product milestone is not more debate depth. It is a **first-class discovery and screening workflow** upstream of the current TradingAgents packet flow.

## Suggested Next Build Slice

The thinnest high-value next slice is:

1. add a repo-owned universe source with 2-3 bounded entry points:
   - OpenD watchlists
   - a tracked sector universe
   - near-term catalyst or earnings names
2. score those candidates deterministically with options and liquidity filters
3. send only the top `N` names through the current TradingAgents packet flow
4. publish one ranked digest

That would upgrade the desk from:

- "analyze what I already know"

to:

- "surface what I should know, then analyze it."
