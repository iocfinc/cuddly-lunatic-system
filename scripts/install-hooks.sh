#!/usr/bin/env sh
set -eu

git config core.hooksPath .githooks
chmod +x scripts/preflight.py scripts/telegram_notify.py scripts/install-hooks.sh
chmod +x .githooks/pre-commit .githooks/pre-push
echo "Git hooks installed from .githooks"
