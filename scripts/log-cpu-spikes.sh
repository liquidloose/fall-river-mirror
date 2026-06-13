#!/usr/bin/env bash
# Log top CPU processes every 30s to /var/log/cpu-spikes.log (requires root to write).
# Usage: sudo ./scripts/log-cpu-spikes.sh start|stop|status

set -euo pipefail

LOG_FILE="/var/log/cpu-spikes.log"
PID_FILE="/var/run/cpu-spike-logger.pid"
INTERVAL=30
TOP_N=25

log_snapshot() {
  {
    echo "=== $(date "+%F %T") ==="
    ps -eo pid,ppid,user,pcpu,pmem,comm,args --sort=-pcpu | head -n "$TOP_N"
  } >>"$LOG_FILE"
}

run_loop() {
  while true; do
    log_snapshot
    sleep "$INTERVAL"
  done
}

start() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Already running (pid $(cat "$PID_FILE"))"
    exit 0
  fi
  touch "$LOG_FILE"
  run_loop &
  echo $! >"$PID_FILE"
  echo "Logging to $LOG_FILE (pid $(cat "$PID_FILE"), every ${INTERVAL}s)"
}

stop() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "Not running (no pid file)"
    exit 0
  fi
  pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "Stopped pid $pid"
  else
    echo "Stale pid file (pid $pid not running)"
  fi
  rm -f "$PID_FILE"
}

status() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Running (pid $(cat "$PID_FILE")) -> $LOG_FILE"
  else
    echo "Not running"
    [[ -f "$PID_FILE" ]] && rm -f "$PID_FILE"
  fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *)
    echo "Usage: sudo $0 {start|stop|status}"
    exit 1
    ;;
esac
