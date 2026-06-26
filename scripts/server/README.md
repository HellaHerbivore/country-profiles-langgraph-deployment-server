# Monthly scraper refreshes on a VPS (cron)

Runs the scraper pipelines that feed the Gemini File Search stores, once a month
via cron, directly on a Linux VPS. No Docker, no time limits. Scraped data and
the PIB upload manifest persist on disk between runs.

Each **source** is one pipeline selected by name:

| Source | Pipeline | Store | Model |
| --- | --- | --- | --- |
| `pib`  | fetch index → parse → deep-fetch full text → upload | `goi-pib` | Append-only per-month archives; uploads only *settled* months. |
| `icnl` | fetch page → parse → upload | `regulatory-environment` | Single living document (ICNL Civic Freedom Monitor – India); each run **replaces** the one snapshot. |

- `setup.sh` — one-time provisioning (system libs, venv, deps, camoufox browser).
- `run_refresh.sh <source>` — the cron entrypoint (and the command for a backfill).
  Defaults to `pib` if no source is given.

Logs land in `logs/refresh-<source>-YYYYMM.log`.

## Setup (run once on the VPS)

```sh
# 1. Get the code
git clone https://github.com/HellaHerbivore/country-profiles-langgraph-deployment-server.git
cd country-profiles-langgraph-deployment-server

# 2. Provision (installs system libs via sudo, builds the venv, fetches the browser)
bash scripts/server/setup.sh

# 3. API key
echo 'GOOGLE_API_KEY=your-key' > .env

# 4. Schedule each source on its own day — 'crontab -e', then add:
#    0 3 2  * * /absolute/path/to/repo/scripts/server/run_refresh.sh pib
#    0 3 26 * * /absolute/path/to/repo/scripts/server/run_refresh.sh icnl
```

## First backfill (per source, by hand)

The first PIB run re-scrapes all history (hours). Run each source once in tmux so
it survives disconnects, then let cron take over:

```sh
tmux new -s backfill
bash scripts/server/run_refresh.sh pib     # detach: Ctrl-b d ; reattach: tmux attach -t backfill
bash scripts/server/run_refresh.sh icnl
```

Watch a run with: `tail -f logs/refresh-icnl-$(date +%Y%m).log`

## One-time PIB store migration (PIB only)

The PIB store may still hold legacy per-*year* documents that must be removed so
they don't duplicate the per-*month* ones. Do this once, by hand:

```sh
cd scripts/filestore_scripts
../../.venv/bin/python migrate_pib_to_monthly.py --dry-run   # preview
../../.venv/bin/python migrate_pib_to_monthly.py             # apply
cd ../..
```

## Adding a new scraper source

1. Create `scripts/scraper_scripts/<source>/` with `config.py`, `fetch.py`,
   `parse.py` (and an optional deep-fetch stage), following the `icnl/` example.
2. Add the source's stage list to `build_pipelines()` in
   `scripts/run_monthly_refresh.py`.
3. If it feeds the agent, create its store
   (`filestore_scripts/setup_store.py --name "..."`), add the store id to
   `filestore_scripts/config.py` and `src/country_profiles/internal_researcher.py`,
   and add a frontend toggle in `frontend/web/src/lib/sources.ts`.
4. Add a cron line: `… run_refresh.sh <source>`.
