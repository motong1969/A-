#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_DIR="$ROOT_DIR/.runlocks"
PID_FILE="$LOCK_DIR/daily-select.pid"

mkdir -p "$LOCK_DIR"
mkdir -p "$ROOT_DIR/logs"

cleanup() {
  rm -f "$PID_FILE"
}

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$EXISTING_PID" ]] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scheduled run skipped: existing process $EXISTING_PID is still running."
    exit 0
  fi
  rm -f "$PID_FILE"
fi

echo "$$" > "$PID_FILE"
trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Checking whether today is an A-share trading day."
if ! python3 scripts/check_trading_day.py; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Not a trading day. Scheduled run skipped."
  exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running daily selector."
python3 scripts/run_daily_select.py --mode baostock --sector-limit 0

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Generating backtest report."
python3 report_backtest.py

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scheduled run completed."
