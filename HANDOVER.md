# Handover

This document is for whoever picks up this project next. The root
`README.md` is stale — it describes an early tutorial scaffold ("Deploy
LangGraph Server with Authentication"). The project has since grown into a
tractability/advocacy research-report agent. Treat this file, not the
README, as the current source of truth until someone rewrites the README.

## 1. What this project does

A LangGraph agent generates "Country Profile" / tractability research
reports on advocacy interventions (e.g. animal welfare policy windows in a
given country or region), backed by curated document stores. Reports are
streamed to a React web frontend through an authenticated proxy server.

Current focus areas (see recent git log for detail): reducing Gemini
"thinking" token spend, refining the report writer's verifier logic
(tolerating shortened tier answers, dash-insensitive comparisons), report
formatting, and NeonDB cost control.

## 2. Architecture map

### Active agent graph
- `src/country_profiles/internal_researcher.py` — **the graph that ships**.
  Exported as `graph`, referenced by `langgraph.json` and baked into the
  Dockerfile's `LANGSERVE_GRAPHS` env var. Pipeline (see `builder.add_node`
  calls near the bottom of the file):
  `ingest_document → normalise_path → dispatch_dimensions → gather_evidence
  → collect_sections → prepare_writing → write_stated_work →
  write_methodology → write_regulatory → write_path_analysis →
  write_windows → write_challenges → write_team → write_followups →
  write_experts → write_evaluation_summary → finalize_report`.
- `src/country_profiles/intervention_tags.py` — the ACE intervention
  vocabulary and tag-alias mapping used to filter the Movement Map store
  during evidence gathering.
- `src/country_profiles/research_assistant.py` — **not used in
  production**. This was an earlier draft build (multi-analyst "interview"
  pattern, OpenRouter + Gemini, Tavily web search + Wikipedia retrieval).
  It is kept in the repo deliberately as a reference for wiring **Tavily
  (or a similar web-search tool) into the active agent** so it can reach
  the live web at key moments, rather than relying solely on the Gemini
  File Search stores. See `search_web` / `search_wikipedia` /
  `search_instructions` in that file for the pattern (ask the LLM to
  return an empty query unless the question needs breaking news or info
  that wouldn't be in the internal vaults, only hitting the web tool when
  it isn't). Do not wire this file's graph directly into `langgraph.json`
  as-is — port the relevant pattern into `internal_researcher.py` instead.

### Server (auth proxy in front of the LangGraph server)
- `server/config.py` — env var loading/validation.
- `server/server_proxy.py` — entrypoint (`ENTRYPOINT` in the Dockerfile).
- `server/app.py` — Starlette app factory, middleware ordering.
- `server/middleware/auth.py` — API-key auth (`x-api-key` header or query
  param).
- `server/middleware/clerk_auth.py` — Clerk JWT verification for the web
  frontend.
- `server/middleware/cors.py` — CORS config.
- `server/proxy.py` — forwards requests (incl. streaming) to the internal
  LangGraph server.
- `server/health.py` — `/ok`, `/health`, `/health-detailed`.
- `server/langgraph_manager.py` — starts/stops the internal LangGraph
  server process.
- `server/feedback_routes.py` / `server/models.py` — feedback endpoints
  (backed by a local SQLite file per `docs/neondb-cost-optimization.md`).
- Full request-flow write-up: `docs/server-architecture.md` (accurate and
  worth reading first).

### Frontend
- `frontend/web/` — React 18 + TypeScript + Vite app (the real UI).
  - `src/hooks/useClerkToken.ts`, `src/components/layout/AuthGate.tsx` —
    Clerk auth wiring.
  - `src/lib/sse-parser.ts`, `src/hooks/useResearch.ts` — SSE streaming of
    report generation from the proxy.
  - `src/components/research/*` — report/activity/sources UI.
  - `components.json` + `src/components/ui/*` — shadcn-style component
    setup on Radix primitives.
- `frontend/api/agent_server.py`, `frontend/chat_local.py`,
  `frontend/chat_remote.py` — example/dev Python clients, not the shipped
  UI.

### Data pipeline
See section 3 below for the full research-ingestion pipeline.

## 3. Research ingestion / filestore pipeline

This is how documents actually get in front of the agent: scrape or collect
source material → convert to clean Markdown → upload into the right Gemini
File Search store, where `internal_researcher.py` retrieves it. Everything
lives under `scripts/`.

### 3.1 Gemini File Search stores (the destinations)

Defined once in `scripts/filestore_scripts/config.py` (kept in sync with the
store IDs the agent reads in `src/country_profiles/internal_researcher.py`):

| Alias | Store | Content |
| --- | --- | --- |
| `foreign-academic` | `FOREIGN_ACADEMIC_STORE` | Foreign academic sources |
| `on-ground` | `ON_GROUND_ADVOCATE_STORE` | On-the-ground advocate sources |
| `local-academic` | `LOCAL_ACADEMIC_STORE` | Local academic sources |
| `goi-pib` | `GOI_PIB_STORE` | Government of India PIB press releases (fisheries) |
| `regulatory-environment` | `REGULATORY_ENVIRONMENT_STORE` | Regulatory/civic-freedom snapshots (e.g. ICNL) |
| `movement-map` | `MOVEMENT_MAP_STORE` | Org/intervention profiles — ACE Movement Map 2026 + Stray Dog Institute India Partner Directory (two collections in one store) |

`setup_store.py --name "..."` creates a brand new store (prints the ID to
paste into `config.py`). There is no script to delete a store — that's a
manual step in the Gemini console/API if one is ever retired.

### 3.2 Converting PDFs — Marker, not a raw scrape

`scripts/filestore_scripts/convert_pdfs.py` uses **[Marker](https://github.com/datalab-to/marker)**
(`marker-pdf`, an optional dependency under `pyproject.toml`'s `filestore`
extra) to turn source PDFs into Markdown before anything is uploaded.
Marker was chosen deliberately over a plain text scrape (e.g. `pypdf`)
because it reconstructs **tables and figures/graphs** into structured
Markdown rather than flattening them into unstructured text — which matters
here since a lot of the source material (regulatory filings, academic PDFs,
government data releases) carries tabular data that the agent needs to cite
accurately.

- Loads Marker's local model weights (~1GB) once per process — the first
  run is slow while it downloads/loads them.
- Idempotent: skips a PDF if a same-named `*_extracted.md` already exists
  and is newer than the source PDF.
- Usage:
  ```bash
  cd scripts/filestore_scripts
  python convert_pdfs.py --input-dir /path/to/pdfs --output-dir /path/to/markdown
  # or a single file:
  python convert_pdfs.py --input-file paper.pdf --output-dir /path/to/markdown
  ```

### 3.3 Uploading — `upload_to_store.py`

The single entry point for pushing files into a File Search store, from
`scripts/filestore_scripts/`:

```bash
python upload_to_store.py --dir /path/to/markdown --store movement-map --mode md-only
```

Key behavior:
- `--store` accepts either an alias from the table above or a raw store ID.
- `--mode {pdf-only,md-only,both}` controls which file types in `--dir` get
  uploaded.
- **Manifest dedup** (`.upload_manifest.json`, local to the script folder,
  gitignored): once a file is uploaded to a given store it's recorded and
  skipped on future runs, by default. This is the normal, append-only mode
  used for most sources.
- `--replace-by-display-name`: **living-document mode**. Before uploading,
  deletes any existing document in the store with the same display name
  (filename), bypassing the manifest, so a fresh snapshot always replaces
  the stale one. Used for pages that get scraped fresh each run (e.g. the
  ICNL Civic Freedom Monitor) rather than being append-only archives.
- `--skip-recent-months N`: skips files whose name ends in a `YYYY_MM`
  within the last N months, because those months' source indexes are still
  growing and not yet "final." Used by the PIB monthly refresh with `N=2`
  so only settled (immutable) months get published — see 3.5.
- `--dry-run` on every mode to preview without side effects.
- Upload retries with exponential backoff (1s/2s/4s) and skips files over
  Gemini's 100MB per-file limit.

`process_and_upload.py` chains 3.2 + 3.3 in one command (`convert_pdfs` →
`upload_to_store`, with `--skip-convert` to only upload already-converted
files) — the convenient path for a one-off manual batch of PDFs.

`migrate_pib_to_monthly.py` is a **one-time cleanup script**, not part of
the recurring pipeline: it deleted legacy per-*year* PIB documents after the
pipeline switched to per-*month* archives, so the two didn't duplicate in
retrieval. Only relevant again if a similar schema change happens.

### 3.4 Automated scrapers (the sources)

Two scrapers currently feed the stores, both under `scripts/scraper_scripts/`,
registered in `scripts/run_monthly_refresh.py`'s `build_pipelines()`:

| Source | What it scrapes | Pipeline stages | Target store | Cadence/shape |
| --- | --- | --- | --- | --- |
| `pib` | Government of India PIB press releases — Ministry of Fisheries (`pib.gov.in/AllRelease.aspx`, fisheries filter) | fetch index (`pib_fetcher.py`) → parse index (`pib_parser.py`) → fetch full article text (`pib_deep_fetcher.py`) → upload | `goi-pib` | **Append-only**, one Markdown archive per month. Only "settled" months (strictly older than last month — see `common/month_logic.is_settled_month`) are ever uploaded, since the current/previous month's index is still growing. |
| `icnl` | ICNL Civic Freedom Monitor — India page (`icnl.org/resources/civic-freedom-monitor/india`) | fetch page (`icnl/fetch.py`) → parse to Markdown (`icnl/parse.py`) → upload | `regulatory-environment` | **Living document** — a single page that gets edited in place upstream. Every run re-scrapes it and replaces the one snapshot in the store (`--replace-by-display-name`), so there's never more than one current copy. |

Both scrapers use **Camoufox** (a stealth/anti-detection Playwright-based
browser, `camoufox[geoip]`) + `beautifulsoup4`/`markdownify` to render and
parse pages that would otherwise be hard to scrape reliably — declared in
`scripts/scraper_scripts/requirements.txt` and `icnl/requirements.txt`.

**Adding a new scraper source** (from `scripts/server/README.md`): create
`scripts/scraper_scripts/<source>/` with `config.py`/`fetch.py`/`parse.py`
following the `icnl/` example, add its stage list to `build_pipelines()`,
create/wire a File Search store for it if it feeds the agent, and add a
cron line (below).

### 3.5 Scheduling — how often this runs

The scrapers run **monthly, via cron on a Linux VPS** (not inside the
Render/Docker deployment, and not GitHub Actions) — see
`scripts/server/README.md`, `run_refresh.sh`, and `setup.sh`:

- `scripts/server/setup.sh` — one-time VPS provisioning: system libs, a
  dedicated venv, scraper + uploader Python deps, and fetching the Camoufox
  browser binary.
- `scripts/server/run_refresh.sh <source>` — the cron entrypoint (also the
  command to run a manual backfill in `tmux`). Runs `nice`/`ionice`'d as a
  low-priority background batch job, logs to
  `logs/refresh-<source>-YYYYMM.log`, and defaults to `pib` if no source is
  given.
- `scripts/run_monthly_refresh.py --source <pib|icnl>` — the actual
  registry-driven pipeline runner: resolves the named source's `Stage` list,
  runs each stage as a subprocess in its own working directory, fails fast
  (non-zero exit) on the first failing stage, and takes a per-source
  lockfile (`.monthly_refresh_<source>.lock`) so overlapping runs of the
  same source can't collide (different sources can still run concurrently).

Recommended crontab (UTC, staggered across the month so the two sources
never collide):

```
0 3 2  * * /absolute/path/to/repo/scripts/server/run_refresh.sh pib
0 3 26 * * /absolute/path/to/repo/scripts/server/run_refresh.sh icnl
```

**First-run note:** the initial PIB backfill re-scrapes all historical
press releases and can take hours — run it once by hand in `tmux` before
handing scheduling over to cron (see `scripts/server/README.md`).

**TODO:** confirm which VPS this cron job actually lives on today, who has
SSH access to it, and whether the crontab matches the recommended schedule
above (get this from Shanil as part of the credentials transfer — section 8).

## 4. External services & credentials

| Service | Used for | Where configured |
| --- | --- | --- |
| Google Gemini (`GOOGLE_API_KEY`) | Primary LLM (`gemini-3-flash-preview`) + native Gemini File Search vector stores | `internal_researcher.py`, `.env` |
| Gemini File Search stores | Movement Map store + other named stores referenced in `internal_researcher.py` (`MOVEMENT_MAP_STORE`, etc.) and `research_assistant.py` (foreign-academic / on-ground-advocate / local-academic vaults) | store IDs hardcoded as constants — **confirm with previous owner who has admin access to create/rotate these** |
| Clerk | Web frontend auth (publishable key client-side, JWT verified server-side) | `frontend/web/.env` (`VITE_CLERK_PUBLISHABLE_KEY`), `server/middleware/clerk_auth.py` |
| NeonDB (Postgres) | LangGraph thread/run/checkpoint storage (`DATABASE_URI`) | Render env vars; see `docs/neondb-cost-optimization.md` |
| Render | Deployment target (always-on instance) | Render dashboard — **get access from previous owner** |
| VPS (cron host) | Runs the monthly scraper refresh (section 3.5) | SSH access to whichever VPS is currently scheduled — **confirm with Shanil** |

Legacy/unused-in-production keys still referenced in `pyproject.toml` or
the old README (OpenAI, YouTube Data API, OpenRouter, Tavily) — confirm
whether any are still paid/active before assuming they're dead.

**TODO (fill in before handing off further):** where the live `.env` /
Render secrets actually live, who holds owner access to Clerk, Neon,
Render, and the Gemini File Search store project.

## 5. Deployment

- `Dockerfile` builds on `langchain/langgraph-api:3.13-wolfi`, copies
  `server/` and `scripts/`, installs deps with `uv`, and hardcodes NeonDB
  cost-control env vars (`LANGGRAPH_THREAD_TTL`, `FF_CRONS_ENABLED=false`,
  `LANGGRAPH_POSTGRES_POOL_MAX_SIZE=10`) — see
  `docs/neondb-cost-optimization.md` for why.
- `docker-compose.yml` — local dev stack (Redis + the server container).
- `langgraph.json` mirrors the same checkpointer TTL for `langgraph dev`.
- One-time manual step after deploy: clear the pre-existing Neon backlog
  via SQL Editor (documented in `docs/neondb-cost-optimization.md`) — TTL
  only reliably covers threads created after it went live.

## 6. Known issues / open questions

- README is stale and should eventually be rewritten to describe the real
  product instead of the auth-proxy tutorial.
- `research_assistant.py` web-search pattern (Tavily/Wikipedia) has not
  been ported into `internal_researcher.py` yet — the production agent
  currently only retrieves from the Gemini File Search stores, so it has
  no way to pull in breaking news or info the curated stores don't have.
- Confirm which of the legacy dependencies (`langchain-openai`,
  `langchain-openrouter`, `langchain-tavily`, `wikipedia`) are safe to drop
  from `pyproject.toml` if the web-search feature isn't picked up soon.
- Verify the Gemini cost-reduction changes (recent commits reducing
  "thinking" spend) haven't regressed report quality.
- Confirm the scraper VPS's crontab actually matches the recommended
  schedule in section 3.5, and that its `.env`/`GOOGLE_API_KEY` and
  Camoufox browser binary are still healthy (nothing currently monitors
  the monthly refresh beyond its own log files).

## 7. Running locally

```bash
uv sync
uv pip install -e .
docker compose up --build      # server + Redis, http://localhost:8000
pytest                          # backend tests

cd frontend/web
npm install
npm run dev                     # Vite dev server
```

Populate `.env` (root) and `frontend/web/.env` from the respective
`.env.example` files before running.

## 8. Contacts / ownership

Contact Shanil for a secure credentials
transfer — Render/Neon billing access, Clerk config, Gemini File Search
store administration, and SSH access to the scraper VPS (section 3.5).
