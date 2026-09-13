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
- `scripts/filestore_scripts/` — converts and uploads documents into the
  Gemini File Search stores (`convert_pdfs.py`, `upload_to_store.py`,
  `setup_store.py`, `migrate_pib_to_monthly.py`, `process_and_upload.py`).
- `scripts/scraper_scripts/` — PIB (Press Information Bureau) fetcher and
  parser feeding those stores; has its own `Dockerfile`/`requirements.txt`.
- `scripts/run_monthly_refresh.py` + `scripts/server/run_refresh.sh` —
  scheduled/manual refresh entry points.

## 3. External services & credentials

| Service | Used for | Where configured |
| --- | --- | --- |
| Google Gemini (`GOOGLE_API_KEY`) | Primary LLM (`gemini-3-flash-preview`) + native Gemini File Search vector stores | `internal_researcher.py`, `.env` |
| Gemini File Search stores | Movement Map store + other named stores referenced in `internal_researcher.py` (`MOVEMENT_MAP_STORE`, etc.) and `research_assistant.py` (foreign-academic / on-ground-advocate / local-academic vaults) | store IDs hardcoded as constants — **confirm with previous owner who has admin access to create/rotate these** |
| Clerk | Web frontend auth (publishable key client-side, JWT verified server-side) | `frontend/web/.env` (`VITE_CLERK_PUBLISHABLE_KEY`), `server/middleware/clerk_auth.py` |
| NeonDB (Postgres) | LangGraph thread/run/checkpoint storage (`DATABASE_URI`) | Render env vars; see `docs/neondb-cost-optimization.md` |
| Render | Deployment target (always-on instance) | Render dashboard — **get access from previous owner** |

Legacy/unused-in-production keys still referenced in `pyproject.toml` or
the old README (OpenAI, YouTube Data API, OpenRouter, Tavily) — confirm
whether any are still paid/active before assuming they're dead.

**TODO (fill in before handing off further):** where the live `.env` /
Render secrets actually live, who holds owner access to Clerk, Neon,
Render, and the Gemini File Search store project.

## 4. Deployment

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

## 5. Known issues / open questions

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

## 6. Running locally

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

## 7. Contacts / ownership

Contact Shanil for a secure credentials
transfer — Render/Neon billing access, Clerk config, and Gemini File
Search store administration.
