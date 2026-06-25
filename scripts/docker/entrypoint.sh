#!/bin/sh
# Entrypoint for the scheduled monthly PIB refresh container.
#
# Responsibilities (kept here, not in the pipeline code, so nothing in the
# scraper/uploader had to change to run on a server):
#   1. Seed /app/.env from $GOOGLE_API_KEY so config.load_dotenv() finds the key
#      even under cron's stripped-down environment.
#   2. Point the pipeline's data dirs + upload manifest at the persistent /data
#      volume via symlinks (settled-month skipping + append-only uploads need
#      this state to survive restarts/redeploys).
#   3. Write the crontab from $CRON_SCHEDULE (no rebuild needed to reschedule).
#   4. Optionally run once immediately ($RUN_ON_START=true) for the first backfill.
#   5. Start cron and stream the run log to stdout so it shows in Easypanel logs.
set -eu

APP=/app
SCRAPER=/app/scripts/scraper_scripts
FILESTORE=/app/scripts/filestore_scripts
LOG=/var/log/refresh.log

# 1. API key -> repo-root .env (config.py loads /app/.env).
if [ -n "${GOOGLE_API_KEY:-}" ]; then
    echo "GOOGLE_API_KEY=${GOOGLE_API_KEY}" > "$APP/.env"
else
    echo "WARNING: GOOGLE_API_KEY is not set — the upload stage will fail." >&2
fi

# 2. Persist scraped data + manifest on /data (no code changes; just symlinks
#    over the relative paths the scripts already use).
mkdir -p /data/data_temp /data/data_markdown /data/data_full_text
ln -sfn /data/data_temp            "$SCRAPER/data_temp"
ln -sfn /data/data_markdown        "$SCRAPER/data_markdown"
ln -sfn /data/data_full_text       "$SCRAPER/data_full_text"
ln -sfn /data/upload_manifest.json "$FILESTORE/.upload_manifest.json"

# 3. Crontab from $CRON_SCHEDULE (default: 03:00 UTC on the 2nd of each month,
#    after the previous month has settled). cron.d lines carry a user field.
SCHED="${CRON_SCHEDULE:-0 3 2 * *}"
printf '%s root cd %s && /usr/local/bin/python scripts/run_monthly_refresh.py >> %s 2>&1\n' \
    "$SCHED" "$APP" "$LOG" > /etc/cron.d/monthly-refresh
chmod 0644 /etc/cron.d/monthly-refresh
touch "$LOG"

# 4. Optional immediate run (first-time backfill or a manual kick via redeploy).
if [ "${RUN_ON_START:-false}" = "true" ]; then
    echo "RUN_ON_START=true → starting a refresh now (also logged below)..." >&2
    ( cd "$APP" && /usr/local/bin/python scripts/run_monthly_refresh.py >> "$LOG" 2>&1 ) &
fi

# 5. Start cron, then tail the log as PID 1 so output appears in Easypanel logs.
cron
echo "cron started — schedule: '$SCHED'  | state: /data  | log: $LOG" >&2
exec tail -F "$LOG"
