# Quant Researcher Desk

Planning-first repository for a personal quantitative research desk focused on daily options analysis, report generation, Telegram delivery, and research journaling.

## Bootstrap

1. Install the local Python runner:

   ```sh
   brew install uv
   ```

2. Create local-only environment settings:

   ```sh
   cp .env.example .env
   ```

3. Leave `TELEGRAM_NOTIFY_ENABLED=false` until `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured in `.env`.

4. Install local Git hooks:

   ```sh
   ./scripts/install-hooks.sh
   ```

## Validation

Run the scaffold preflight before handing off changes:

```sh
uv run python scripts/preflight.py --hook manual
```

For documentation-only changes, also read the affected Markdown files and check headings, examples, and links manually. No product build or test suite exists yet beyond the scaffold preflight.

## Telegram Notifications

Telegram notifications are local-only and disabled by default.

1. Copy the sample environment file:

   ```sh
   cp .env.example .env
   ```

2. In `.env`, set:

   ```sh
   TELEGRAM_NOTIFY_ENABLED=true
   TELEGRAM_BOT_TOKEN=replace-with-real-token
   TELEGRAM_CHAT_ID=replace-with-real-chat-id
   ```

3. Validate formatting without network delivery:

   ```sh
   uv --cache-dir .uv-cache run python scripts/telegram_notify.py --dry-run "Telegram notification test"
   ```

4. After credentials are present, run one explicit live test:

   ```sh
   uv --cache-dir .uv-cache run python scripts/telegram_notify.py --post "Quant Researcher Desk Telegram test"
   ```

Real Telegram credentials belong only in `.env`, which is ignored by Git. Git hooks call Telegram only after preflight failure and only when notifications are enabled.

## Agentic Stack

Repo-local Codex settings live in `.codex/config.toml`. That file enables Codex hooks for this repository and wires Codex notifications to the product Telegram script at `scripts/telegram_notify.py`.

The notification script reads local settings from `.env.example` and `.env`. Real Telegram credentials belong only in `.env`, which is ignored by Git.

Install and bootstrap agentic-stack locally with:

```sh
brew tap codejunkie99/agentic-stack https://github.com/codejunkie99/agentic-stack
brew install agentic-stack
agentic-stack codex --yes
```

Keep reusable Codex skills, agents, hooks, and automation harnesses outside this repo. Use the external CodexSkills harness for shared agentic-stack logic; this repository should only contain Quant Researcher Desk product code, tests, docs, and product-local scripts.
