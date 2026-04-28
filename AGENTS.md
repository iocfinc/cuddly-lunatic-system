# Repository Guidelines

## Project Structure & Module Organization

This repository is currently a planning-first codebase for **Quant Researcher Desk**, a personal quantitative research system for daily options analysis and report generation.

- `internal-notes/` contains product source material: PRD, roadmap, acceptance criteria, and design guidance.
- Add production code under `src/` when implementation begins.
- Add tests under `tests/`, mirroring the source module names where possible.
- Keep generated reports, snapshots, and journals out of source modules; prefer `reports/`, `data/`, or `journal/` with clear retention rules once those workflows exist.

## Build, Test, and Development Commands

This repo now uses a Python-first scaffold with `pyproject.toml` and `uv`.

- `brew install uv` — install the standard local Python runner if it is missing.
- `uv run python scripts/preflight.py --hook pre-commit` — run the scaffold pre-flight checks.
- `uv run python scripts/telegram_notify.py --dry-run "preflight test"` — validate Telegram notification formatting without network delivery.
- `./scripts/install-hooks.sh` — configure Git to use the local hooks in `.githooks/`.

No product test suite is configured yet. When production code is introduced, add the supporting files before documenting commands such as `pytest`, `ruff`, or `mypy`.

## Coding Style & Naming Conventions

Favor small, explicit modules organized by workflow responsibility: ingestion, pricing, volatility analysis, strategy evaluation, scenario simulation, reporting, and journaling.

Use descriptive names tied to the domain, such as `black_scholes`, `implied_volatility`, `scenario_matrix`, and `thesis_report`. Keep report language professional and evidence-based: statement, evidence, interpretation, then risk. Avoid hype, trading-signal language, and automated-trading assumptions.

## Testing Guidelines

Testing should prioritize numerical correctness and repeatable outputs.

- Put unit tests in `tests/`.
- Name tests after the behavior being verified, for example `test_black_scholes_call_price`.
- Include fixture data for options chains and report examples once ingestion starts.
- Compare pricing, Greeks, IV, and scenario outputs against known reference values.

## Commit & Pull Request Guidelines

This repository has no commit history yet, so use short imperative commit messages until a stronger convention emerges, for example `Add pricing engine outline`.

Pull requests should include:

- A brief summary of the change.
- Links to relevant planning notes in `internal-notes/`.
- Test or validation evidence.
- Screenshots or sample report output when changing report formatting.

## Agent-Specific Instructions

Keep reusable agent harnesses, skills, and workflow automation outside this product repository. This repo should stay focused on the Quant Researcher Desk product, its implementation, tests, and product-specific documentation.

When merging or updating agent instructions, preserve product-specific Quant Researcher Desk guidance here and move reusable Codex harness logic to the external CodexSkills harness. Repo-local Codex config may wire this product to local scripts, but it should not define broad plugin/app behavior or reusable workflow automation.

## Local Secrets & Notifications

- Copy `.env.example` to `.env` for local-only secrets.
- Keep `.env` ignored and never commit real tokens.
- Set `TELEGRAM_NOTIFY_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` only when local Telegram notifications should send.
- Git hooks call Telegram only after pre-flight failure.

## Codex & Agentic Stack

Repo-local Codex settings live in `.codex/config.toml`. They enable Codex hooks and route notifications through `scripts/telegram_notify.py`.

Agentic-stack setup is local bootstrap only:

1. `brew tap codejunkie99/agentic-stack https://github.com/codejunkie99/agentic-stack`
2. `brew install agentic-stack`
3. `agentic-stack codex --yes`

Treat `.agent/` and related agentic-stack runtime memory, indexes, dashboard exports, and flywheel outputs as private local state unless a specific product artifact is intentionally promoted into tracked docs.
