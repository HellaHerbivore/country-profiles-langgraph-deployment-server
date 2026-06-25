# Scheduled monthly PIB refresh (Easypanel / Docker)

Runs the full pipeline — scrape index → parse → deep-fetch full text → upload
only *settled* months to the `goi-pib` File Search store — on a monthly cron
schedule, inside one long-running container.

Files:
- `monthly-refresh.Dockerfile` — bundles the stealth browser (camoufox + Xvfb)
  **and** the uploader (google-genai), bakes the browser binary, runs cron.
- `entrypoint.sh` — seeds `.env` from the API key, persists state on `/data`,
  writes the crontab from `$CRON_SCHEDULE`, starts cron, streams logs to stdout.

## Deploy on Easypanel

1. **Create service** → **App**. Name it e.g. `pib-monthly-refresh`.
2. **Source** → connect this GitHub repo, pick the branch to deploy.
3. **Build** → choose **Dockerfile**, set the path to:
   `scripts/docker/monthly-refresh.Dockerfile`
4. **Environment** → add:
   - `GOOGLE_API_KEY` = your Gemini API key (required).
   - `CRON_SCHEDULE` = `0 3 2 * *` *(optional; default is 03:00 UTC on the 2nd
     of each month — edit with [crontab.guru](https://crontab.guru)).*
   - `RUN_ON_START` = `true` *(optional; runs one refresh immediately on deploy —
     useful for the first backfill, then set back to `false`).*
5. **Volumes** → add a volume mounted at `/data` (keeps scraped data + the upload
   manifest across restarts, so months aren't re-scraped every run).
6. This is a worker — **no domain/port** needed. Deploy.

Logs (including each run's output) appear in the service's **Logs** tab.

## First run / backfill & the one-time store migration

The store currently holds legacy per-*year* documents. Before/around the first
per-*month* backfill, run the one-off cleanup once (Easypanel → service →
**Console/Terminal**):

```sh
cd /app/scripts/filestore_scripts
python migrate_pib_to_monthly.py --dry-run   # preview
python migrate_pib_to_monthly.py             # apply (deletes legacy per-year docs)
```

Then trigger the first full refresh (either set `RUN_ON_START=true` and redeploy,
or from the console):

```sh
cd /app && python scripts/run_monthly_refresh.py
```

After that, cron handles it monthly. Because `/data` is persistent, each monthly
run only re-scrapes the current + previous month and uploads newly-settled ones.
