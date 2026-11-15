# PRD: Options Catalyst Product Map

## Goal

Turn Options Catalyst from a daily screen into a research loop that can test, manage, and learn from options ideas after they enter review.

The product should remain research-only. It should improve decision quality by combining deterministic evidence with persona-based review, not by producing broker-style instructions.

## Boundaries

## In Scope

- real historical replay design for long single-leg option ideas
- paper-review lifecycle states from idea generation through exit and post-review
- deterministic management rules for time decay, thesis invalidation, event timing, and option mark changes
- persona-based review council for richer reasoning and disagreement capture
- source and data contracts for historical options chains, underlying bars, event timing, and news/catalyst evidence
- feature map and first implementation slice for the existing repo

## Out Of Scope

- automated broker execution
- live order routing
- short-premium or complex multi-leg strategy expansion
- treating LLM output as a standalone trading signal
- reusable Codex harness logic inside this product repo

## Current Diagnosis

The current system has a strong deterministic spine but weak historical accountability.

- Stock-first gating is a good first filter, but it does not prove edge.
- The catalyst is currently a reinforcing context layer, not a verified data source.
- The lifecycle layer is useful but synthetic; it should graduate into replay over historical option marks.
- Advisor checks catch missing evidence, but the product needs richer disagreement before ideas are promoted.
- OpenD is useful for current chains but not enough by itself for historical options backtesting.

## Product Principles

- Stock first, contract second, catalyst third.
- Backtest before conviction.
- Missing data blocks promotion rather than being smoothed over.
- Persona reasoning can enrich a review but cannot override deterministic gates.
- Every accepted idea needs an exit policy before it can enter paper tracking.
- All outputs remain watch/review/pass language, never execution instructions.

## Feature Map

## Immediate Fixes

- Add an explicit `backtest_status` to catalyst artifacts:
  - `not_run`
  - `synthetic_only`
  - `historical_partial`
  - `historical_complete`
  - `blocked_missing_data`
- Add source notes for each idea:
  - underlying bars source
  - option chain source
  - option mark source
  - event timing source
  - catalyst/news source
- Add a persona review block to artifacts with deterministic fallback fixtures.
- Keep advisor verdicts strict when backtest or source coverage is missing.

## Backtesting Foundation

- Define a historical option mark schema:
  - `symbol`
  - `option_code`
  - `date`
  - `bid`
  - `ask`
  - `mid`
  - `last`
  - `volume`
  - `open_interest`
  - `delta`
  - `implied_volatility`
  - `underlying_price`
  - `days_to_expiry`
- Build a replay runner for one long call/put idea at a time.
- Model exit rules before modeling returns:
  - max holding days
  - DTE floor
  - thesis invalidation
  - premium drawdown
  - premium target
  - event-window review
  - liquidity deterioration
- Store replay outputs separately from live screen outputs.
- Treat sparse or stale historical options data as a blocker.

## Trade Lifecycle Management

- Add lifecycle states:
  - `screened`
  - `paper_accepted`
  - `paper_active`
  - `review_required`
  - `closed`
  - `expired`
  - `invalidated`
  - `blocked_missing_data`
- Add daily management checks:
  - current option mark versus entry mark
  - DTE remaining
  - underlying versus invalidation level
  - event timing proximity
  - volume/open-interest deterioration
  - IV change and theta pressure
- Add post-review attribution:
  - stock regime was right or wrong
  - contract selection helped or hurt
  - catalyst timing helped or hurt
  - exit rule helped or hurt
  - persona disagreement was useful or noisy

## Signal Quality Upgrades

- Add volatility regime:
  - realized volatility percentile
  - IV versus historical volatility
  - IV rank or proxy when available
- Add market context:
  - index trend
  - sector trend
  - risk-on/risk-off proxy
- Add catalyst evidence:
  - mapped event date
  - source timestamp
  - event type
  - confidence
  - stale-source blocker
- Add portfolio context:
  - duplicate exposure by ticker, sector, and event window
  - total premium at risk in paper review
  - correlated names inside the same catalyst cluster

## Persona Review Council

Persona review should be a structured artifact, not free-form chat.

- `Regime Analyst`:
  - checks trend, sector context, and invalidation
  - can downgrade mixed or extended setups
- `Volatility Analyst`:
  - checks IV, event risk, premium richness, and post-event crush risk
  - can require backtest evidence before promotion
- `Contract Specialist`:
  - checks liquidity, delta, spread proxy, DTE, and resale quality
  - can block thin contracts
- `Lifecycle Manager`:
  - checks exit rules, daily management burden, and stop/review conditions
  - can block ideas without a management plan
- `Skeptical PM`:
  - checks concentration, overlap, source gaps, and whether the idea is overfit to catalyst language
  - can keep an idea in watch even if other personas like it

The council output should include:

- persona name
- disposition: `priority_review`, `conditional_watch`, `pass`, or `blocked`
- confidence: `low`, `medium`, or `high`
- evidence used
- blockers
- one-sentence thesis
- one-sentence invalidation

## GPT-5.5 Use

Use GPT-5.5 where qualitative synthesis matters, while keeping numerical decisions deterministic.

- Good uses:
  - persona review summaries
  - catalyst/news interpretation
  - post-review attribution
  - contradiction detection across personas
  - management-note drafting
  - explaining backtest results
- Bad uses:
  - replacing option mark calculations
  - inventing missing event dates
  - overriding failed advisor gates
  - producing execution instructions
  - treating one persona's confidence as edge

## Open-Source Tools To Evaluate

- QuantLib:
  - already in the repo
  - best for pricing, Greeks, and model validation
  - official project describes it as a free/open-source quantitative finance library for modeling, trading, and risk management
  - source: https://www.quantlib.org/
- VectorBT:
  - useful for vectorized signal research and parameter sweeps over underlying or option-mark series
  - official docs describe a pandas/NumPy approach accelerated for large strategy grids
  - source: https://vectorbt.dev/
- Backtrader:
  - useful for event-driven backtests and lifecycle logic
  - official site describes reusable strategies, indicators, and analyzers
  - source: https://www.backtrader.com/
- bt:
  - useful for composable portfolio-level logic and allocation experiments
  - official docs describe reusable Algo blocks for strategy testing
  - source: https://pmorissette.github.io/bt/
- OpenBB:
  - useful to evaluate as a market-data integration layer, especially for options chain endpoints
  - current docs expose derivatives/options commands such as chains, snapshots, surface, and unusual
  - source: https://docs.openbb.co/odp/python/reference/derivatives/options
- yfinance:
  - useful for research-only fallback and quick prototyping, but not a durable production source
  - docs state it is not affiliated with Yahoo and is intended for research and educational purposes
  - source: https://ranaroussi.github.io/yfinance/
- Optopsy:
  - worth a spike for options-specific research ideas, but treat as evaluation-only until maintenance, data assumptions, and Python compatibility are verified locally
  - source: https://github.com/goldspanlabs/optopsy

## Architecture Map

- `src/quant_researcher_desk/catalyst_options_screen.py`
  - current idea generation and stock-first filtering
- `src/quant_researcher_desk/catalyst_lifecycle.py`
  - current lifecycle records, synthetic evidence, and advisor gates
  - target home for lifecycle state transitions and management summaries
- `src/quant_researcher_desk/options_research.py`
  - pricing, Greeks, scenario, and valuation evidence
- `src/quant_researcher_desk/options_strategy_router.py`
  - strategy suitability and structure selection
- proposed `src/quant_researcher_desk/options_backtest.py`
  - historical option mark schema, replay runner, and return metrics
- proposed `src/quant_researcher_desk/options_personas.py`
  - deterministic persona schema and optional LLM-backed synthesis
- proposed `src/quant_researcher_desk/options_position_management.py`
  - paper lifecycle updates, exit checks, and post-review attribution
- proposed `scripts/run_options_backtest.py`
  - fixture and historical replay entrypoint
- proposed `scripts/run_options_persona_review.py`
  - fixture and live artifact persona review entrypoint
- proposed `tests/test_options_backtest.py`
  - replay and exit-rule tests
- proposed `tests/test_options_personas.py`
  - persona schema, blocker, and disagreement tests
- proposed `tests/test_options_position_management.py`
  - paper state transition and attribution tests

## First Implementation Slice

Build a fixture-backed historical replay for one catalyst idea.

Done means:

- a fixture option-mark path can replay a long call or put from `paper_accepted` to `closed`
- the replay emits final return, max return, max drawdown, exit reason, and rule flags
- sparse historical marks produce `blocked_missing_data`
- persona council can review the replay with deterministic fixture personas
- advisor gate fails if an idea has only synthetic evidence but is marked as promoted
- tests run without OpenD or network access

Suggested files:

- add `src/quant_researcher_desk/options_backtest.py`
- add `src/quant_researcher_desk/options_personas.py`
- add `tests/test_options_backtest.py`
- add `tests/test_options_personas.py`
- update `src/quant_researcher_desk/catalyst_lifecycle.py` to distinguish synthetic versus historical evidence

## Validation Commands

```bash
uv run pytest tests/test_catalyst_lifecycle.py tests/test_options_backtest.py tests/test_options_personas.py -q
uv run python scripts/run_catalyst_options_review.py --fixture --dry-run --output-dir /tmp/catalyst-options-review-fixture
```

## Open Questions

- Which historical options source is acceptable for the first real replay: paid vendor export, OpenBB provider, local CSV, or Moomoo historical capture going forward?
- Should persona reviews run daily on all ideas or only after deterministic gates pass?
- Should paper-review entries live in JSON first, SQLite, or the existing journal artifacts?
- What promotion threshold should separate `conditional_watch` from `paper_accepted`?
- How much historical coverage is required before backtest statistics can be called useful?

