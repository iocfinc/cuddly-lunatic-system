#!/usr/bin/env zsh
# Headless daily catalyst options screen for Quant Researcher Desk.

set -u

ROOT="/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst"
UV="/opt/homebrew/bin/uv"
LOG_DIR="$ROOT/reports/cron-logs"
LOCK_ROOT="$ROOT/.cron-locks"
LOCK_DIR="$LOCK_ROOT/options-update.lock"
LOCK_STALE_SECONDS="${QRD_LOCK_STALE_SECONDS:-21600}"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export PYTHONUNBUFFERED=1

send_mode="--post"
if [[ "${QRD_DRY_RUN:-false}" == "true" ]]; then
  send_mode="--dry-run"
fi

mkdir -p "$LOG_DIR" "$LOCK_ROOT"
exec >> "$LOG_DIR/options-update.log" 2>&1

echo "==== $(date '+%Y-%m-%d %H:%M:%S %Z') options-update start ===="
echo "mode=$send_mode"

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    return 0
  fi
  if [[ -d "$LOCK_DIR" ]]; then
    lock_epoch=$(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0)
    now_epoch=$(date +%s)
    age=$((now_epoch - lock_epoch))
    if (( age > LOCK_STALE_SECONDS )); then
      echo "options-update stale lock detected: age=${age}s; clearing $LOCK_DIR"
      rmdir "$LOCK_DIR" 2>/dev/null || true
      mkdir "$LOCK_DIR" 2>/dev/null && return 0
    fi
  fi
  return 1
}

if ! acquire_lock; then
  echo "options-update skipped: previous run still active"
  exit 0
fi

cleanup() {
  exit_code=$?
  rmdir "$LOCK_DIR" 2>/dev/null || true
  echo "==== $(date '+%Y-%m-%d %H:%M:%S %Z') options-update end status=$exit_code ===="
}
trap cleanup EXIT

cd "$ROOT" || exit 1

"$UV" --cache-dir "$ROOT/.uv-cache" run python scripts/send_catalyst_options_screen.py \
  "$send_mode" \
  --output-dir "$ROOT/reports/catalyst-options"
