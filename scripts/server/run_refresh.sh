#!/usr/bin/env bash
# Cron wrapper for a monthly scraper refresh. Cron runs with a stripped-down
# environment, so this resolves the repo, uses the venv's Python explicitly, and
# logs with timestamps. run_monthly_refresh.py has its own per-source lockfile,
# so overlapping runs of the same source are already prevented.
#
# Takes the scraper source as the first argument (defaults to "pib" for
# backwards compatibility with the original single-source cron line).
#
# Runs under `nice`/`ionice` so it always yields CPU and disk to anything else
# on the box (e.g. an N8N container) — the scrapers are low-priority monthly
# batches paced by deliberate delays, so deferring costs them nothing.
#
# Schedule via 'crontab -e' (one line per source, on their own days, UTC):
#   0 3 2  * * /absolute/path/to/repo/scripts/server/run_refresh.sh pib
#   0 3 26 * * /absolute/path/to/repo/scripts/server/run_refresh.sh icnl
#
# It's also the command to run by hand (in tmux) for a first full backfill.
set -uo pipefail   # no -e: we want to log the pipeline's exit code

SOURCE="${1:-pib}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/refresh-${SOURCE}-$(date +%Y%m).log"

cd "$REPO_ROOT"
echo "[$(date -Is)] START monthly refresh (source=$SOURCE)" | tee -a "$LOG"
nice -n 19 ionice -c 3 "$VENV_PY" scripts/run_monthly_refresh.py --source "$SOURCE" >> "$LOG" 2>&1
status=$?
echo "[$(date -Is)] END monthly refresh (source=$SOURCE, exit $status)" | tee -a "$LOG"
exit $status
