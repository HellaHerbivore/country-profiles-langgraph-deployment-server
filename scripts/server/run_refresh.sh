#!/usr/bin/env bash
# Cron wrapper for the monthly PIB refresh. Cron runs with a stripped-down
# environment, so this resolves the repo, uses the venv's Python explicitly, and
# logs with timestamps. run_monthly_refresh.py has its own lockfile, so
# overlapping runs are already prevented.
#
# Schedule via 'crontab -e' (03:00 UTC on the 2nd of each month):
#   0 3 2 * * /absolute/path/to/repo/scripts/server/run_refresh.sh
#
# It's also the command to run by hand (in tmux) for the first full backfill.
set -uo pipefail   # no -e: we want to log the pipeline's exit code

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/refresh-$(date +%Y%m).log"

cd "$REPO_ROOT"
echo "[$(date -Is)] START monthly refresh" | tee -a "$LOG"
"$VENV_PY" scripts/run_monthly_refresh.py >> "$LOG" 2>&1
status=$?
echo "[$(date -Is)] END monthly refresh (exit $status)" | tee -a "$LOG"
exit $status
