# Quant Researcher Desk

Quant Researcher Desk is an agentic options research system for retail and independent investors who want disciplined, repeatable analysis instead of ad hoc trade ideas. The project combines options chain ingestion, quantitative pricing, scenario analysis, Telegram delivery, and research journaling into a Python-first workflow designed for daily use.

The current repository includes a working local Moomoo OpenD integration for `US.TSM` options reporting, Telegram notification tooling, and the planning documents for a broader quantitative research stack. The intended direction is a research desk that can fetch options data, calculate pricing and Greeks, frame risk-first theses, and turn each run into a structured memo rather than a trading signal.

The closed-form pricing core now supports a shadow migration path: `legacy` keeps the repo-owned Black-Scholes and IV implementation, while `quantlib` becomes available when the `QuantLib` Python package is installed. Market data, weekly workflow orchestration, Monte Carlo intuition, and report rendering stay repo-owned.

## Get Started

The best first run in this repo is the fixture-backed weekly options screen. It shows the full workflow without needing OpenD or Telegram first.

Quickstart commands:

```sh
brew install uv
cp .env.example .env
mkdir -p ~/.codex/skills
cp -R /Users/iraoliverfernando/Desktop/Dioscuri/CodexSkills/.agents/skills/clear-technical-writing ~/.codex/skills/clear-technical-writing
./scripts/install-hooks.sh
uv --cache-dir .uv-cache run python scripts/preflight.py --hook manual
uv --cache-dir .uv-cache run python scripts/run_weekly_options_screen.py --fixture --report-format html
LATEST_HTML=$(ls -t reports/weekly-options/*-weekly-shortlist.html | head -n 1)
open "$LATEST_HTML"
```

Step-by-step:

1. Install `uv`.

```sh
brew install uv
```

2. Create your local-only environment file.

```sh
cp .env.example .env
```

3. Install the local writing skill this repo uses for explanation-first copy.

```sh
mkdir -p ~/.codex/skills
cp -R /Users/iraoliverfernando/Desktop/Dioscuri/CodexSkills/.agents/skills/clear-technical-writing ~/.codex/skills/clear-technical-writing
```

The canonical skill name for this repo is `clear-technical-writing`. The public `codex-ai-lab-skills` checkout on this machine currently exposes a different inventory under `SKILLS/`, including `anti-slop-editorial`, so the local `CodexSkills` mirror is the source-of-truth install path for now.

4. Restart Codex so the new skill is available in the session.

5. Install the local Git hooks.

```sh
./scripts/install-hooks.sh
```

6. Run the preflight check once.

```sh
uv --cache-dir .uv-cache run python scripts/preflight.py --hook manual
```

7. Run the weekly options screen in fixture mode first.

```sh
uv --cache-dir .uv-cache run python scripts/run_weekly_options_screen.py --fixture --report-format html
```

8. Open the newest generated HTML report.

```sh
LATEST_HTML=$(ls -t reports/weekly-options/*-weekly-shortlist.html | head -n 1)
open "$LATEST_HTML"
```

9. If you want to inspect the machine-readable payload in the terminal, open the newest JSON artifact.

```sh
LATEST_JSON=$(ls -t reports/weekly-options/*-weekly-shortlist.json | head -n 1)
python -m json.tool "$LATEST_JSON" | less
```

10. When you want live data, start and log into Moomoo OpenD, then rerun without `--fixture`.

```sh
uv --cache-dir .uv-cache run python scripts/run_weekly_options_screen.py --report-format pdf
```

The live run keeps the machine-readable CSV and JSON outputs, writes the teaching-first HTML explainer, and derives a PDF companion for upload or attachment.

## What The Weekly Options Screen Is Doing

The weekly screen is now stock-first by default. It starts from a broad US universe pulled from Moomoo plates, fetches daily bars, classifies each stock into a deterministic trend regime, runs a light stock review on bullish and bearish names, then filters the option chain to aligned direction only: CALLs for bullish names, PUTs for bearish names. Mixed or no-trade stock context produces no weekly directional candidate. The outputs are split by audience: CSV and JSON for machine workflows, HTML and PDF for human review. The shortlist is a research queue, not a trade instruction.

The current strategy lane is intentionally narrow: long single-leg options for resale, not hedging and not exercise into stock. The ranking now explicitly prefers contracts that are easier to exit later: directionally aligned, inside the working delta band, liquid enough to review seriously, and visibly penalized when event timing is risky or unknown.

Optional reviewer lane:

- `--review-shortlist` runs deterministic shortlist checks after ranking
- reviewer statuses are `Candidate`, `Watch`, `Reject`, or `Needs Human Review`
- `--reviewer-model` adds a non-blocking portfolio-manager summary on top of the deterministic review
- `--analysis-mode options-first` keeps the temporary comparison path for validation and rollback
- `--no-stock-review` disables the stock-review gate when you need a deterministic regime-only comparison

## What This Repository Is For

This repository is building a personal quant research desk for:

- options chain analysis
- implied volatility and Greeks workflows
- scenario-based options research
- LLM-assisted thesis generation
- Telegram-delivered market reports
- agentic research automation with human review

The focus is understanding, not execution. It is not an automated trading bot, not a signal-selling product, and not a real-time execution engine.

## Current Status

The project is in an early implementation phase with a planning-first structure and one live integration path already working locally.

Implemented now:

- Python scaffold with `uv`
- local preflight checks and Git hooks
- Telegram notification script with formatted HTML support
- Telegram document attachment support for report delivery
- local Moomoo OpenD quote integration
- `US.TSM` options report script with ranked calls and puts
- fixture-backed options pricing, Greeks, IV, scenario, and verdict pipeline
- QuantLib shadow-compare seam for closed-form pricing migration
- fixture-backed US/HK sector value-chain tree reports
- institutional HTML report rendering with optional PDF export through Playwright
- tokenized report theme primitives through `REPORT_THEME`
- local options journal persistence and outcome updates
- unit tests for report formatting, ranking logic, and Telegram payloads

Planned next:

- real earnings, fundamentals, and sector relationship providers
- richer thesis and report generation

## Why It Exists

Most retail options workflows optimize for placing trades quickly. Quant Researcher Desk is being built to optimize for learning, structure, and evidence.

The operating idea is simple:

1. pull the market data
2. price and interpret the optionality
3. simulate scenarios
4. write a clear thesis with explicit risk
5. deliver the output in a format that is easy to review daily

That makes the system useful for agentic search as well as human search because the repository is explicitly about quantitative options research, Moomoo OpenD automation, Telegram market reporting, and retail research discipline.

## Architecture Direction

The product is organized around a small set of workflows:

- ingestion: fetch underlying prices and options chains
- pricing: compute theoretical values, implied volatility, and Greeks
- analysis: compare model outputs with market structure and liquidity
- strategy evaluation: frame candidate structures and tradeoffs
- scenario simulation: test price, IV, and time-decay paths
- reporting: generate disciplined research memos
- journaling: record thesis, outcomes, and learning loops

Tracked planning docs live in [internal-notes/PRD.md](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/internal-notes/PRD.md), [internal-notes/acceptance-criteria-QA.md](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/internal-notes/acceptance-criteria-QA.md), and [internal-notes/design-branding.md](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/internal-notes/design-branding.md).

Framework audit and migration rationale live in [internal-notes/quant-framework-audit.md](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/internal-notes/quant-framework-audit.md).

The product-specific spec workflow now lives under [internal-notes/glossary/development-model.md](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/internal-notes/glossary/development-model.md), with weekly-lane feature packs at [internal-notes/features/weekly-underlying-gate/PRD.md](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/internal-notes/features/weekly-underlying-gate/PRD.md) and [internal-notes/features/long-single-leg-weekly-lane/PRD.md](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/internal-notes/features/long-single-leg-weekly-lane/PRD.md).

The verified OpenD wrapper surface for this repo is documented in [internal-notes/features/long-single-leg-weekly-lane/ADR-002-opend-capability-surface.md](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/internal-notes/features/long-single-leg-weekly-lane/ADR-002-opend-capability-surface.md) and mirrored in code through `opend_capability_contract()` in [src/quant_researcher_desk/moomoo_options_report.py](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/src/quant_researcher_desk/moomoo_options_report.py).

## Repository Layout

- `src/` contains product code
- `tests/` contains unit tests
- `scripts/` contains local operational scripts
- `docs/` contains rendered visual and user-facing artifacts
- `internal-notes/` contains product specs, ADRs, templates, and design guidance

Use `internal-notes/` as the source of truth for product rules, strategy scope, and implementation ADRs. Keep `docs/` focused on rendered explainers, visuals, and user-facing artifacts.

Current implementation highlights:

- [scripts/send_tsmc_options_report.py](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/scripts/send_tsmc_options_report.py)
- [src/quant_researcher_desk/moomoo_options_report.py](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/src/quant_researcher_desk/moomoo_options_report.py)
- [scripts/telegram_notify.py](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/scripts/telegram_notify.py)

## Motion Overview

The current product-motion overview artifact is a Remotion explainer for the sector and industry research workflow:

<p align="center">
  <img src="docs/assets/sector-universe-explainer.gif" alt="sector-universe-explainer" width="880"/>
</p>

This GIF is derived from [demos/remotion/sector-universe-explainer](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/demos/remotion/sector-universe-explainer) and shows how Quant Researcher Desk maps market sectors into upstream, operating, demand, and evidence layers before turning the research into Telegram and PDF-ready outputs. A companion MP4 is tracked at [docs/assets/sector-universe-explainer.mp4](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/docs/assets/sector-universe-explainer.mp4).

The earlier Options Analyst workflow overview remains available at [docs/assets/options-analyst-overview.gif](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/docs/assets/options-analyst-overview.gif).

## Local Setup

Install the local Python runner:

```sh
brew install uv
```

Create local-only environment settings:

```sh
cp .env.example .env
```

Install local hooks:

```sh
./scripts/install-hooks.sh
```

If you are using the weekly options screen as the first workflow, install `clear-technical-writing` into `~/.codex/skills` and restart Codex before the first run. The repo uses that skill name as the local writing source of truth even though the public skill checkout currently uses different names.

## Validation

Run the scaffold preflight:

```sh
uv --cache-dir .uv-cache run python scripts/preflight.py --hook manual
```

Run unit tests:

```sh
uv --cache-dir .uv-cache run pytest
```

Run the fixture-backed weekly screen:

```sh
uv --cache-dir .uv-cache run python scripts/run_weekly_options_screen.py --fixture --report-format html
```

## Telegram Notifications

Telegram notifications are local-only and disabled by default.

Set in `.env`:

```sh
TELEGRAM_NOTIFY_ENABLED=true
TELEGRAM_BOT_TOKEN=replace-with-real-token
TELEGRAM_CHAT_ID=replace-with-real-chat-id
```

For a public channel, use `@channel_username`. For a private channel, add the bot as a channel admin and use the numeric chat id starting with `-100`.

Dry-run message formatting:

```sh
uv --cache-dir .uv-cache run python scripts/telegram_notify.py --dry-run "Telegram notification test"
```

Live formatting smoke test:

```sh
uv --cache-dir .uv-cache run python scripts/telegram_notify.py --post --parse-mode HTML $'<b>Quant Researcher Desk</b>\nTelegram formatting test'
```

Telegram payloads are validated before network calls. Unsupported parse modes, captions above Telegram's document-caption limit, empty or missing documents, and unsupported photo file types fail locally instead of sending a partial notification.

## Moomoo OpenD Options Report

The repository currently includes a working local options report flow powered by `moomoo-api` and Moomoo OpenD.

Set in `.env`:

```sh
MOOMOO_OPEND_HOST=127.0.0.1
MOOMOO_OPEND_PORT=11111
MOOMOO_DEFAULT_SYMBOL=US.TSM
```

Build the report without posting:

```sh
uv --cache-dir .uv-cache run python scripts/send_tsmc_options_report.py --dry-run --symbol US.TSM --rows 5
```

Send the report to Telegram:

```sh
uv --cache-dir .uv-cache run python scripts/send_tsmc_options_report.py --post --symbol US.TSM --rows 5
```

The report includes:

- timestamp
- underlying latest price
- selected expiry
- scanned contract count
- ranked top calls
- ranked top puts
- risk note stating the output is research only

## Options Research PDF/HTML Report

The fuller options research flow prices a selected contract, computes Greeks, compares IV against HV, simulates price/IV/time-decay scenarios, and produces a risk-first verdict. Use fixture mode for deterministic dry-runs:

```sh
uv --cache-dir .uv-cache run python scripts/send_options_research_report.py --dry-run --fixture --symbol US.TEST --report-format html
```

Enable the visual explainer and migration diagnostics when you want the teaching and parity views:

```sh
uv --cache-dir .uv-cache run python scripts/send_options_research_report.py --dry-run --fixture --symbol US.TEST --report-format html --visual-explainer --shadow-compare --pricing-engine legacy
```

Add post-gate strategy comparison only after the stock, tape, and product gate has passed:

```sh
uv --cache-dir .uv-cache run python scripts/send_options_research_report.py --dry-run --fixture --symbol US.TEST --report-format html --strategy-gate-passed --strategy-gate-reason "fixture stock-first gate passed"
```

The comparison section is suppressed by default so weak or unmapped stock context cannot become a ranked strategy idea. When enabled, the report compares research-only structures such as long single-leg, debit spread, covered call, and cash-secured put candidates.

Persist a local options journal entry without posting Telegram:

```sh
uv --cache-dir .uv-cache run python scripts/send_options_research_report.py --dry-run --fixture --symbol US.TEST --report-format html --persist-journal --journal-dir reports/journal
```

The command prints a local reference in the form `journal: reports/journal/options-journal.json#<entry-id>`.

Update an existing journal entry after the planned review window:

```sh
uv --cache-dir .uv-cache run python scripts/update_options_journal.py --entry-id <entry-id> --status inconclusive --lesson "Outcome stayed mixed after the planned review window." --underlying-price 101.5 --option-price 3.9
```

Outcome status values are `confirmed`, `invalidated`, and `inconclusive`.

Use live Moomoo OpenD data by omitting `--fixture` after OpenD is running:

```sh
uv --cache-dir .uv-cache run python scripts/send_options_research_report.py --post --symbol US.TSM --option-type CALL --strike 100
```

The script attempts PDF output by default. If Playwright/Chromium is unavailable, it writes the printable HTML companion and uses that as the attachment path.

## Weekly Shortlist Reviewer

Run the fixture-backed weekly screen with reviewer annotations and shadow comparison:

```sh
uv --cache-dir .uv-cache run python scripts/run_weekly_options_screen.py --fixture --report-format html --shadow-compare --review-shortlist --pricing-engine legacy
```

Add an LLM summary layer on top of the deterministic reviewer:

```sh
uv --cache-dir .uv-cache run python scripts/run_weekly_options_screen.py --fixture --review-shortlist --reviewer-model gpt-5.4-mini
```

The reviewer is non-blocking by design. CSV, JSON, HTML, and PDF artifacts are still written even when the reviewer only adds caution flags or the LLM summary falls back to a deterministic summary.

## Weekly Options Screen

Use this workflow when you want a broad US weekly shortlist instead of a single-name report.

Fixture-backed first run:

```sh
uv --cache-dir .uv-cache run python scripts/run_weekly_options_screen.py --fixture --report-format html
```

Live OpenD rerun:

```sh
uv --cache-dir .uv-cache run python scripts/run_weekly_options_screen.py --report-format pdf
```

The workflow writes artifacts under `reports/weekly-options/`:

- `*-weekly-shortlist.csv` for tabular downstream use
- `*-weekly-shortlist.json` for automation and inspection
- `*-weekly-shortlist.html` as the primary explainer artifact
- `*-weekly-shortlist.pdf` as the printable and upload-friendly companion

The generated HTML explains:

- what this run is
- how universe discovery works
- why some names were skipped
- how contracts are filtered
- how scoring works
- how to read the ranked shortlist safely

## TradingAgents Research Decision Packet

The repository now includes an optional TradingAgents adoption seam that treats TradingAgents as a bounded research-debate engine. It is disabled by default, reuses the existing report renderer and Telegram document sender, and keeps all state under repo-local ignored paths instead of `~/.tradingagents`.

Use the fixture path for deterministic local validation with no OpenD, no Telegram post, and no live LLM requirement:

```sh
uv --cache-dir .uv-cache run python scripts/send_tradingagents_packet.py --dry-run --fixture --symbol US.TEST --report-format pdf
```

The script writes:

- a rendered packet attachment under `reports/tradingagents/` by default
- a repo-local JSON artifact under `data/tradingagents/results/`

Optional env vars:

```sh
TRADINGAGENTS_ENABLED=false
TRADINGAGENTS_REF=refs/tags/v0.2.4
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_LLM_BACKEND=api
TRADINGAGENTS_CODEX_MODEL=gpt-5.4
TRADINGAGENTS_CODEX_PROFILE=
TRADINGAGENTS_RESULTS_DIR=data/tradingagents/results
TRADINGAGENTS_CACHE_DIR=data/tradingagents/cache
TRADINGAGENTS_MEMORY_DIR=data/tradingagents/memory
TRADINGAGENTS_SOURCE_DIR=../TradingAgents
TRADINGAGENTS_ALLOW_EXECUTION=false
ABACUS_API_KEY=
ABACUS_BASE_URL=https://routellm.abacus.ai/v1
ABACUS_DEEP_MODEL=gpt-5.4
ABACUS_QUICK_MODEL=gpt-5.4-mini
ABACUS_AGENT_MODEL_MAP='{"market":"gpt-5.4-mini","social":"gpt-5.4-mini","news":"gpt-5.4-mini","fundamentals":"gpt-5.4-mini","risk_reflection":"gpt-5.4-mini","bull_researcher":"gpt-5.4","bear_researcher":"gpt-5.4","research_manager":"gpt-5.4","trader":"gpt-5.4","portfolio_manager":"gpt-5.4"}'
```

Backend options:

- `TRADINGAGENTS_LLM_BACKEND=api` uses the upstream TradingAgents graph and its provider SDK path
- `TRADINGAGENTS_LLM_BACKEND=codex` uses a headless `codex exec` JSON contract, defaulting to `gpt-5.4`

When `TRADINGAGENTS_ENABLED=true` and the upstream dependency is installed locally, the script can attempt a live adapter run. The output is still normalized into research-only labels: `Research Candidate`, `Watchlist`, `Reject`, or `Needs Human Review`.

## TradingAgents Watchlist Digest

The watchlist digest flow reads the Moomoo OpenD watchlist, evaluates the selected names through the repo-owned TradingAgents adapter seam, and publishes one ranked attachment plus one concise Telegram caption.

Fixture-backed dry-run:

```sh
uv --cache-dir .uv-cache run python scripts/send_tradingagents_watchlist_digest.py --dry-run --fixture --symbols US.NVDA,US.TSM,US.META --report-format html
```

Live OpenD scan:

```sh
uv --cache-dir .uv-cache run python scripts/send_tradingagents_watchlist_digest.py --post --max-candidates 5 --top-n 3
```

## Sector Universe and Newsletter Report

The sector tree flow builds an educational upstream/midstream/downstream map for a sector and produces Telegram TLDR copy plus a detailed PDF attachment. The scheduled job now prefers the exported Moomoo HK/US industry universe for rotation, with the older curated fixture-backed sectors used as a fallback. It also persists the last successful 3-hour dispatch so duplicate cron or LaunchAgent runs do not resend the same sector inside the cooldown window.

Refresh the local sector universe from Moomoo OpenD:

```sh
uv --cache-dir .uv-cache run python scripts/export_moomoo_sector_universe.py
```

The export writes:

- `docs/sector-industry-universe.md` for the working research document
- `docs/sector-universe-app.html` for an interactive visual browser
- `data/sector-universe/moomoo_hk_us_plates.json` and `.csv` for the raw Moomoo plate database
- `data/sector-universe/value_chain_nodes.csv` for graph nodes
- `data/sector-universe/value_chain_edges.csv` and `value_chain_graph.mmd` for starter supply-chain relationships

```sh
uv --cache-dir .uv-cache run python scripts/send_sector_tree_report.py --dry-run --rotate --report-format pdf
```

```sh
uv --cache-dir .uv-cache run python scripts/send_sector_tree_report.py --dry-run --market HK --sector "internet platforms" --report-format pdf
```

The headless cron wrappers support `QRD_DRY_RUN=true` for local validation without sending Telegram messages:

```sh
QRD_DRY_RUN=true scripts/cron_sector_update.sh
QRD_DRY_RUN=true scripts/cron_options_update.sh
```

## macOS Scheduling

For macOS, prefer `launchd` over `cron`. This repository lives under `~/Desktop/...`, and background cron execution is less reliable there because of macOS privacy and session behavior.

Install the user LaunchAgents:

```sh
./scripts/install-launch-agents.sh
```

The repo includes:

- `launchd/com.dioscuri.quant-researcher-desk.sector-update.plist` for sector updates every 3 hours
- `launchd/com.dioscuri.quant-researcher-desk.options-update.plist` for the daily 10:00 options update

The scheduled options screen is proactive by design: it targets expiries around one week out and skips same-day expiry setups, because those are usually reaction trades rather than researchable thesis windows.

Reports are written under `reports/` by default. Treat generated report files as local output unless a specific artifact is intentionally promoted into tracked documentation.

## Product Principles

- structure over impulse
- evidence over hype
- risk before verdict
- understanding before automation

The guiding principle comes directly from the PRD: we are not predicting markets, we are building understanding.

## Keywords

Quant Researcher Desk, quantitative research system, options research, options chain analysis, implied volatility, Greeks, Black-Scholes, scenario analysis, Moomoo OpenD, moomoo-api, Telegram bot, Telegram market report, agentic finance workflow, retail investor research tooling, options thesis generator.
