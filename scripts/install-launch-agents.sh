#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst"
LAUNCHD_DIR="$ROOT/launchd"
USER_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT/reports/cron-logs"

mkdir -p "$USER_AGENTS_DIR" "$LOG_DIR"

install_agent() {
  local src="$1"
  local label="$2"
  local dest="$USER_AGENTS_DIR/$(basename "$src")"

  cp "$src" "$dest"
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$dest"
  launchctl enable "gui/$(id -u)/$label"
  launchctl kickstart -k "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  echo "loaded: $label"
}

install_agent \
  "$LAUNCHD_DIR/com.dioscuri.quant-researcher-desk.sector-update.plist" \
  "com.dioscuri.quant-researcher-desk.sector-update"

install_agent \
  "$LAUNCHD_DIR/com.dioscuri.quant-researcher-desk.options-update.plist" \
  "com.dioscuri.quant-researcher-desk.options-update"

echo "LaunchAgents installed into $USER_AGENTS_DIR"
