#!/usr/bin/env zsh
# Headless daily catalyst options screen for Quant Researcher Desk.

set -u

ROOT="/Users/iraoliverfernando/Desktop/Dioscuri/naval-analyst"
UV="/opt/homebrew/bin/uv"
LOG_DIR="$ROOT/reports/cron-logs"
STATE_DIR="$ROOT/reports/run-state"
RUN_LEDGER="$STATE_DIR/options-update-ledger.jsonl"
LOCK_ROOT="$ROOT/.cron-locks"
LOCK_DIR="$LOCK_ROOT/options-update.lock"
LOCK_STALE_SECONDS="${QRD_LOCK_STALE_SECONDS:-21600}"
ARTIFACT_PATH="$ROOT/reports/catalyst-options/catalyst-options-screen.pdf"
RUN_STARTED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export PYTHONUNBUFFERED=1

send_mode="--post"
if [[ "${QRD_DRY_RUN:-false}" == "true" ]]; then
  send_mode="--dry-run"
fi

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$STATE_DIR"
exec >> "$LOG_DIR/options-update.log" 2>&1

echo "==== $(date '+%Y-%m-%d %H:%M:%S %Z') options-update start ===="
echo "mode=$send_mode"

record_run() {
  local status="$1"
  local exit_code="$2"
  local finished_at
  finished_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  printf '{"started_at":"%s","finished_at":"%s","status":"%s","exit_code":%s,"mode":"%s","artifact_path":"%s","log_path":"%s"}\n' \
    "$RUN_STARTED_AT" "$finished_at" "$status" "$exit_code" "$send_mode" "$ARTIFACT_PATH" "$LOG_DIR/options-update.log" >> "$RUN_LEDGER"
}

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
  record_run "skipped_lock_active" 0
  exit 0
fi

cleanup() {
  exit_code=$?
  rmdir "$LOCK_DIR" 2>/dev/null || true
  if (( exit_code == 0 )); then
    record_run "succeeded" "$exit_code"
  else
    record_run "failed" "$exit_code"
  fi
  echo "==== $(date '+%Y-%m-%d %H:%M:%S %Z') options-update end status=$exit_code ===="
}
trap cleanup EXIT

cd "$ROOT" || exit 1

"$UV" --cache-dir "$ROOT/.uv-cache" run python scripts/send_catalyst_options_screen.py \
  "$send_mode" \
  --output-dir "$ROOT/reports/catalyst-options" \
  --run-ledger "$RUN_LEDGER"
