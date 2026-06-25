# Monthly PIB refresh — scheduled scrape -> upload, packaged for Easypanel/Docker.
#
# Runs scripts/run_monthly_refresh.py on a cron schedule inside a long-running
# container (Easypanel's recommended cron pattern). Bundles BOTH halves the
# refresh needs: the stealth browser (camoufox + Xvfb) and the uploader
# (google-genai). State (scraped data + upload manifest) lives on the /data
# volume so settled-month skipping and append-only uploads survive restarts.
#
# Build context = repository ROOT. In Easypanel set:
#   Build -> Dockerfile path = scripts/docker/monthly-refresh.Dockerfile
FROM python:3.13-slim

# Firefox/Camoufox runtime libraries, the virtual display, and cron.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgtk-3-0 libx11-xcb1 libasound2 xvfb cron ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps: scraper side (camoufox, bs4, playwright) + uploader side.
COPY scripts/scraper_scripts/requirements.txt /tmp/scraper-requirements.txt
RUN pip install --no-cache-dir -r /tmp/scraper-requirements.txt \
    && pip install --no-cache-dir google-genai python-dotenv colorama

# Bake the Camoufox browser binary into the image at build time.
RUN python -m camoufox fetch

# Application code (scraper_scripts, filestore_scripts, run_monthly_refresh.py).
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/docker/entrypoint.sh

# Persistent state (scraped data + upload manifest). Mount a volume here.
VOLUME ["/data"]

ENTRYPOINT ["/app/scripts/docker/entrypoint.sh"]
