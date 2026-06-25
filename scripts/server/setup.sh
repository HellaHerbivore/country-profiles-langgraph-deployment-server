#!/usr/bin/env bash
# One-time provisioning for the monthly PIB refresh on a Linux VPS (Debian/Ubuntu).
# Idempotent — safe to re-run. From the repository root:
#   bash scripts/server/setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$REPO_ROOT/.venv"
cd "$REPO_ROOT"

echo "==> System libraries (Firefox/Camoufox runtime + virtual display)..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    libgtk-3-0 libx11-xcb1 libasound2 xvfb python3-venv python3-pip

echo "==> Virtualenv at $VENV ..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip

echo "==> Python dependencies (scraper + uploader)..."
"$VENV/bin/pip" install --quiet -r scripts/scraper_scripts/requirements.txt
"$VENV/bin/pip" install --quiet google-genai python-dotenv colorama

echo "==> Camoufox browser binary..."
"$VENV/bin/python" -m camoufox fetch

echo "==> Verifying both halves import..."
( cd scripts/scraper_scripts  && "$VENV/bin/python" -c "from camoufox.async_api import AsyncCamoufox; print('    browser deps OK')" )
( cd scripts/filestore_scripts && "$VENV/bin/python" -c "from config import GOI_PIB_STORE; from upload_to_store import load_manifest; print('    uploader deps OK')" )

echo "==> API key check (.env at repo root)..."
if [ -f "$REPO_ROOT/.env" ] && grep -q '^GOOGLE_API_KEY=' "$REPO_ROOT/.env"; then
    echo "    GOOGLE_API_KEY found in .env"
else
    echo "    !! Missing — run:  echo 'GOOGLE_API_KEY=your-key' > $REPO_ROOT/.env"
fi

cat <<EOF

Setup complete. Remaining steps:
  1. Make sure $REPO_ROOT/.env contains GOOGLE_API_KEY.
  2. Schedule it — run 'crontab -e' and add this line:

       0 3 2 * * $REPO_ROOT/scripts/server/run_refresh.sh

     (03:00 on the 2nd of each month; adjust with https://crontab.guru)
  3. First backfill is a long one-off — see scripts/server/README.md.
EOF
