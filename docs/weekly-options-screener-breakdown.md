# Weekly Options Screener Breakdown

This document explains what the weekly options screener does and how the
position shortlist is trimmed before publication.

The implementation lives in
`src/quant_researcher_desk/weekly_options_screener.py`.

## Purpose

The screener is a stock-first weekly options workflow for US names.

It is designed to:

- start from a broad live OpenD universe
- reduce that universe to names with a clear directional regime
- keep only weekly contracts with usable liquidity
- score the surviving contracts on direction, exit quality, valuation, and event risk
- publish a diversified shortlist instead of a ticker-concentrated contract dump

## Request Defaults

The default request shape is defined by `WeeklyScreenRequest`.

Current defaults:

- `market = US`
- `top_n = 10`
- `minimum_days_out = 5`
- `target_days_out = 7`
- `min_volume = 100`
- `min_open_interest = 100`
- `min_abs_delta = 0.20`
- `max_abs_delta = 0.60`
- `historical_volatility = 0.25`
- `max_underlyings = 60`
- `pricing_engine = legacy`
- `analysis_mode = stock-first`
- `stock_review = true`

## High-Level Flow

The screener trims candidates in five layers:

1. universe discovery
2. stock-context gate
3. weekly-expiry gate
4. contract-quality gate
5. ranking plus diversification

## 1. Universe Discovery

The screener begins by calling OpenD plate APIs:

- `get_plate_list(market, "ALL")`
- `get_plate_constituents(plate_code)`

It then:

- deduplicates overlapping symbols across plates
- records the source plates for each symbol
- stops once it reaches `max_underlyings`

This means the screener does not start from a user-curated watchlist by default.
It starts from a broad live market universe and caps the number of symbols it
will attempt.

## 2. Stock-Context Gate

In the default `stock-first` mode, each symbol must first pass the stock gate
before any option contract is considered.

For each candidate symbol, the screener:

- loads daily bars
- builds stock context
- classifies the trend regime
- runs or derives a stock review

Names are removed here if:

- the trend regime is `mixed`
- the stock review returns `no_trade`
- daily bars or stock context inputs are missing

If the stock review passes, it also forces side alignment:

- bullish stock context -> only `CALL` contracts are eligible
- bearish stock context -> only `PUT` contracts are eligible

This is the first major trim in the pipeline.

## 3. Weekly-Expiry Gate

For each surviving symbol, the screener asks OpenD for expirations and chooses
the expiry closest to the weekly target window.

The selection logic:

- rejects expiries closer than `minimum_days_out`
- prefers expiries closest to `target_days_out`
- breaks ties by preferring expiries on or after the target date

If a symbol does not have a usable weekly expiry, it is removed at this stage.

## 4. Contract-Quality Gate

After the weekly expiry is chosen, the screener fetches:

- the option chain for that expiry
- market snapshots for the returned option codes

It then keeps only contracts that satisfy the hard contract filter:

- premium must be greater than zero
- volume must be at least `min_volume`
- open interest must be at least `min_open_interest`
- absolute delta must be between `min_abs_delta` and `max_abs_delta`

In `stock-first` mode, the aligned side filter is then applied on top of that:

- bullish names keep only `CALL`s
- bearish names keep only `PUT`s

If no contracts survive these checks, the symbol is dropped from the shortlist
pipeline.

This is the second major trim.

## 5. Scoring Surviving Contracts

Each surviving contract is scored individually.

The screener computes:

- theoretical value using the configured pricing engine
- Monte Carlo value
- blended model edge versus market premium
- liquidity score
- expiry-fit score
- IV versus historical-volatility adjustment
- directional-fit score
- delta-fit score
- exit-quality score
- valuation-context score
- event-risk score

These are combined into a composite score:

- directional fit: `25%`
- exit quality: `35%`
- valuation context: `25%`
- event risk: `15%`

The practical effect is:

- direction matters
- but the shortlist is not just trend-following
- liquidity and exit quality carry the heaviest weight
- valuation and timing still matter

## 6. Global Ranking

All surviving contracts are then sorted globally.

The sort order is:

1. highest `composite_score`
2. highest `liquidity_score`
3. highest `model_edge_pct`
4. symbol
5. option code

If the screener stopped here, the shortlist would likely over-concentrate in a
small number of tickers with many similar contracts.

## 7. Diversification Trim

The final shortlist is not a simple top-`N` slice from the sorted list.

Instead, the screener groups contracts by symbol and does a round-robin
selection:

- first pass: take the top contract from each symbol
- second pass: take the second contract from each symbol
- continue until `top_n` is filled

This means the published shortlist is intentionally diversified across names.

Practical consequence:

- a symbol with five highly ranked contracts does not automatically take over
  the whole shortlist
- a lower-ranked contract from another symbol can still make the published list
  because diversification is a deliberate product rule

## 8. Optional Post-Shortlist Review

After the shortlist is built, there are optional reviewer layers:

- deterministic shortlist review
- LLM summary review
- separate headless GPT-5.5 per-option review lane

These layers do not define the shortlist itself.
They annotate or explain the contracts that already survived the main screen.

## Gate Summary Semantics

The screener also records a gate trail for each symbol.

The main gate stages are:

- `universe_discovery`
- `stock_context`
- `weekly_expiry`
- `contract_quality`
- `shortlist_outcome`

Each symbol ends with either:

- a pass into the published shortlist
- a concrete failure reason
- a ranked-out outcome after diversification

This is why the run output can report where symbols were lost rather than only
showing a final shortlist.

## How The Shortlist Is Trimmed

The simplest way to think about the trimming logic is:

1. start with up to `max_underlyings` live symbols
2. drop names without a clean stock regime
3. drop names without a usable weekly expiry
4. drop contracts with weak liquidity, zero premium, or the wrong delta
5. drop contracts on the wrong side of the stock thesis
6. score what remains
7. keep a diversified top `N`

So the shortlist is not just a list of expensive options that happen to exist.
It is already constrained by:

- stock regime
- expiry timing
- contract liquidity
- delta usability
- side alignment
- ranking quality
- diversification

## Why This Matters

When reviewing a weekly output, it helps to separate two questions:

1. why did a symbol survive at all?
2. why did a specific contract make the published shortlist instead of another contract from the same ticker?

The answer to the first question is mostly the stock-context and weekly-expiry
gate.

The answer to the second question is mostly:

- hard contract filters
- composite score
- diversification round-robin

## Current Product Interpretation

The screener should be read as a research queue, not an execution engine.

It is best understood as:

- a stock-first weekly options narrowing system
- biased toward liquid, readable contracts
- hostile to mixed-regime names
- willing to drop contracts that are directionally interesting but operationally weak
- intentionally diversified in the final published shortlist
