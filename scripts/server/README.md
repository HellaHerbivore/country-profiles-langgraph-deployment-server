# Monthly PIB refresh on a VPS (cron)

Runs the full pipeline — scrape index → parse → deep-fetch full text → upload
only *settled* months to the `goi-pib` store — once a month via cron, directly
on a Linux VPS. No Docker, no time limits. Scraped data and the upload manifest
persist on disk between runs, so each monthly run only re-scrapes the current +
previous month.

- `setup.sh` — one-time provisioning (system libs, venv, deps, camoufox browser).
- `run_refresh.sh` — the cron entrypoint (and the command for the first backfill).

## Setup (run once on the VPS)

```sh
# 1. Get the code
git clone https://github.com/HellaHerbivore/country-profiles-langgraph-deployment-server.git
cd country-profiles-langgraph-deployment-server

# 2. Provision (installs system libs via sudo, builds the venv, fetches the browser)
bash scripts/server/setup.sh

# 3. API key
echo 'GOOGLE_API_KEY=your-key' > .env

# 4. Schedule it — 'crontab -e', then add the line setup.sh printed:
#    0 3 2 * * /absolute/path/to/repo/scripts/server/run_refresh.sh
```

Logs land in `logs/refresh-YYYYMM.log`.

## First backfill + one-time store migration

The first run re-scrapes all history (hours), and the store still holds legacy
per-*year* documents that must be removed so they don't duplicate the new
per-*month* ones. Do this once, by hand:

```sh
# a) Remove the legacy per-year docs from the store (preview, then apply)
cd scripts/filestore_scripts
../../.venv/bin/python migrate_pib_to_monthly.py --dry-run
../../.venv/bin/python migrate_pib_to_monthly.py
cd ../..

# b) Run the first full backfill in tmux so it survives disconnects
tmux new -s backfill
bash scripts/server/run_refresh.sh        # detach with Ctrl-b d; reattach: tmux attach -t backfill
```

After the backfill, cron takes over monthly. Watch a run with:
`tail -f logs/refresh-$(date +%Y%m).log`
