# Quant Researcher Desk

Quant Researcher Desk is an agentic options research system for retail and independent investors who want disciplined, repeatable analysis instead of ad hoc trade ideas. The project combines options chain ingestion, quantitative pricing, scenario analysis, Telegram delivery, and research journaling into a Python-first workflow designed for daily use.

The current repository includes a working local Moomoo OpenD integration for `US.TSM` options reporting, Telegram notification tooling, and the planning documents for a broader quantitative research stack. The intended direction is a research desk that can fetch options data, calculate pricing and Greeks, frame risk-first theses, and turn each run into a structured memo rather than a trading signal.

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
- local Moomoo OpenD quote integration
- `US.TSM` options report script with ranked calls and puts
- unit tests for report formatting, ranking logic, and Telegram payloads

Planned next:

- broader options ingestion workflows
- pricing engine with Black-Scholes and Greeks
- implied volatility and historical volatility analysis
- scenario matrices and strategy evaluation
- journal persistence and outcome tracking
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

## Repository Layout

- `src/` contains product code
- `tests/` contains unit tests
- `scripts/` contains local operational scripts
- `internal-notes/` contains PRD, QA criteria, and design guidance

Current implementation highlights:

- [scripts/send_tsmc_options_report.py](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/scripts/send_tsmc_options_report.py)
- [src/quant_researcher_desk/moomoo_options_report.py](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/src/quant_researcher_desk/moomoo_options_report.py)
- [scripts/telegram_notify.py](/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst/scripts/telegram_notify.py)

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

## Validation

Run the scaffold preflight:

```sh
uv --cache-dir .uv-cache run python scripts/preflight.py --hook manual
```

Run unit tests:

```sh
uv --cache-dir .uv-cache run pytest
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

## Product Principles

- structure over impulse
- evidence over hype
- risk before verdict
- understanding before automation

The guiding principle comes directly from the PRD: we are not predicting markets, we are building understanding.

## Keywords

Quant Researcher Desk, quantitative research system, options research, options chain analysis, implied volatility, Greeks, Black-Scholes, scenario analysis, Moomoo OpenD, moomoo-api, Telegram bot, Telegram market report, agentic finance workflow, retail investor research tooling, options thesis generator.

