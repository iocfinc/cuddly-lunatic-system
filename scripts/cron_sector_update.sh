#!/usr/bin/env zsh
# Headless daily HK tech sector value-chain brief for Quant Researcher Desk.

set -u

ROOT="/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst"
UV="/opt/homebrew/bin/uv"
LOG_DIR="$ROOT/reports/cron-logs"
LOCK_ROOT="$ROOT/.cron-locks"
LOCK_DIR="$LOCK_ROOT/sector-update.lock"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export PYTHONUNBUFFERED=1

send_mode="--post"
if [[ "${QRD_DRY_RUN:-false}" == "true" ]]; then
  send_mode="--dry-run"
fi

mkdir -p "$LOG_DIR" "$LOCK_ROOT"
exec >> "$LOG_DIR/sector-update.log" 2>&1

echo "==== $(date '+%Y-%m-%d %H:%M:%S %Z') sector-update start ===="
echo "mode=$send_mode"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "sector-update skipped: previous run still active"
  exit 0
fi

cleanup() {
  exit_code=$?
  rmdir "$LOCK_DIR" 2>/dev/null || true
  echo "==== $(date '+%Y-%m-%d %H:%M:%S %Z') sector-update end status=$exit_code ===="
}
trap cleanup EXIT

cd "$ROOT" || exit 1

"$UV" --cache-dir "$ROOT/.uv-cache" run python scripts/send_sector_tree_report.py \
  "$send_mode" \
  --rotate \
  --report-format pdf \
  --output-dir "$ROOT/reports/sector-tree"
