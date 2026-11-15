# WTF: Options Catalyst Product Map

## Problem

The Options Catalyst workflow can now produce stock-first, research-only review artifacts, but it still has two important product gaps:

- backtest evidence is synthetic and cannot yet answer whether past ideas would have worked under repeatable entry, exit, and management rules
- lifecycle management stops at review queue metadata instead of tracking paper entries, thesis invalidation, time decay, event windows, roll/exit decisions, and post-review lessons

The current system is useful for screening and explanation, but not yet strong enough to measure edge or reinforce returns.

## User Or Operator

The operator is a solo options researcher who wants a daily review workflow that teaches, validates, and improves. The system should help the operator avoid overreacting to catalysts, understand whether a contract can be managed after entry, and learn from the actual path after an idea is accepted into paper review.

## Why Now

The repo already has the ingredients:

- stock-first catalyst screening
- options pricing and scenario reports
- advisor gating
- local lifecycle records
- fixture-backed tests
- journal update paths

The next leap is not another screen. It is accountability after a screened idea appears: historical replay, management rules, persona disagreement, and post-review attribution.

## Evidence

- `src/quant_researcher_desk/catalyst_lifecycle.py` already creates paper-review records, exit-rule flags, synthetic premium paths, and advisor checks.
- `scripts/run_catalyst_options_review.py` writes JSON, HTML, and PDF artifacts with advisor verdicts.
- `src/quant_researcher_desk/weekly_options_screener.py` already separates stock context, event risk, contract quality, pricing, and reviewer status.
- Current OpenD capability notes still mark event calendar as unsupported for scoring.
- Current fixture paths make it feasible to test lifecycle and persona outputs without live OpenD.

## Success Signal

Every catalyst idea can be traced from signal generation through paper entry, management decisions, exit, and post-review attribution. Persona reviews can disagree, but no persona can override missing deterministic evidence such as unmapped event timing, failed pricing, missing chain marks, or violated exit rules.

