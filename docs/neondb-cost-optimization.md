# NeonDB Cost Optimization

Why the Neon bill grows in this project, what this repo now does about it, and
the settings to check in the Neon console. Based on Neon's
[cost optimization guide](https://neon.com/docs/introduction/cost-optimization)
and its linked pages ([compute lifecycle](https://neon.com/docs/introduction/compute-lifecycle),
[scale to zero](https://neon.com/docs/introduction/scale-to-zero),
[pricing](https://neon.com/pricing)).

## How this project uses Neon

Neon is the Postgres behind the LangGraph API server (`DATABASE_URI` on
Render). It stores LangGraph's operational state only: threads, runs, and
checkpoints. Nothing else reads it — the frontend streams reports over SSE and
never reloads old threads, and the feedback DB is a local SQLite file.

Two properties of the stack drive the bill:

1. **While the Render service is awake, Neon can never idle.** The LangGraph
   server holds a connection pool open, its queue worker polls the `run` table
   continuously, and (before this change) a cron scheduler queried Postgres
   every 5 seconds. Neon bills compute per CU-hour whenever the endpoint is
   active — and since this project runs on an always-on paid Render instance
   (chosen deliberately so users skip the cold start), Neon's compute clock
   runs 24/7: ~730 hours/month at whatever CU size the autoscaler allocates.
   That makes the autoscaling **max** the single biggest cost risk: an hour at
   8 CU bills 32× an hour at 0.25 CU.
2. **Storage only ever grew.** Every run writes a checkpoint per superstep;
   the state includes the full `messages` accumulation and any uploaded
   document as base64 (`document_b64`). No TTL was configured, so threads,
   runs, and checkpoints accumulated forever — and every write also lands in
   Neon's instant-restore (WAL) history, which is billed separately.

## What this repo now configures (Dockerfile defaults)

| Setting | Value | Effect |
| --- | --- | --- |
| `LANGGRAPH_THREAD_TTL` | delete after 30 days, sweep hourly | Threads (with their runs + checkpoints) are deleted 30 days after last activity. The frontend never reopens threads, so nothing user-visible is lost. Shorten `default_ttl` (minutes) if 30 days is still too much storage. |
| `FF_CRONS_ENABLED` | `false` | Stops the cron scheduler's 5-second Postgres polling. This project defines no LangGraph crons. Remove if you ever adopt them. |
| `LANGGRAPH_POSTGRES_POOL_MAX_SIZE` | `10` | Caps connections per replica (default 150). One low-traffic replica needs far fewer, and a small pool sits comfortably on a 0.25 CU compute. |

`langgraph.json` carries the same TTL under `checkpointer.ttl` so
`langgraph dev`/`langgraph build` deployments behave identically. In the
custom Dockerfile deployment the env vars are what count.

### One-time backlog cleanup

The TTL only reliably covers threads created after it deploys (expiry is
stamped per thread), so clear the pre-existing backlog once by hand in the
Neon console's **SQL Editor**. The production proxy authenticates with
short-lived Clerk JWTs, which makes bulk deletion through the REST API
impractical — SQL is the right tool here.

**1. See what's there** (also confirms the table names in your schema —
LangGraph's state lives in tables named like `thread`, `run`, `checkpoints`,
`checkpoint_blobs`, `checkpoint_writes`):

```sql
SELECT relname AS table, pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 15;
```

**2a. Full wipe (recommended)** — nothing in the app ever re-reads old
threads, so the simplest option is to clear all agent state. Run it at a
quiet moment: it also removes any run currently in flight.

```sql
TRUNCATE TABLE checkpoint_writes, checkpoint_blobs, checkpoints, run, thread CASCADE;
```

TRUNCATE releases the disk space immediately (no vacuum needed).

**2b. Age-based alternative** — keep the last 30 days. The explicit `::text`
casts make the joins work whether `thread_id` is stored as uuid or text:

```sql
BEGIN;
CREATE TEMP TABLE stale AS
  SELECT thread_id::text AS tid FROM thread
  WHERE updated_at < now() - interval '30 days';
DELETE FROM checkpoint_writes WHERE thread_id::text IN (SELECT tid FROM stale);
DELETE FROM checkpoint_blobs  WHERE thread_id::text IN (SELECT tid FROM stale);
DELETE FROM checkpoints       WHERE thread_id::text IN (SELECT tid FROM stale);
DELETE FROM run               WHERE thread_id::text IN (SELECT tid FROM stale);
DELETE FROM thread            WHERE thread_id::text IN (SELECT tid FROM stale);
COMMIT;
```

Unlike TRUNCATE, DELETE leaves dead rows behind; autovacuum reclaims them
over the following hours, so the storage graph lags the cleanup.

**3. Verify**: rerun the size query from step 1, and load the app and run a
quick report to confirm normal operation. Note the freed data remains in the
instant-restore (WAL) history until the restore window passes, so the billed
storage settles fully only after that window.

## Settings to check in the Neon console

Do these in the [Neon console](https://console.neon.tech). Start at
**Billing → Usage** to see whether *compute* or *storage* dominates your bill —
that tells you which of the following matters most.

1. **Compute size / autoscaling** (Branches → your branch → compute settings):
   keep the minimum at **0.25 CU** and cap the maximum at **1 CU**. This
   database only shuffles small JSON state rows; it does not need a big
   compute. With an always-on server the monthly floor is
   0.25 CU × 730 h ≈ $19 on Launch rates, and every hour the autoscaler
   spends above the floor multiplies that — a ceiling of 8 CU allows up to
   ~$620/month. One caveat: Neon also scales up to fit the *working set* into
   compute memory, so a checkpoint table bloated by years of un-TTL'd state
   can pin the allocation high; the TTL plus the one-time cleanup above is
   what fixes that, not a bigger compute.
2. **Scale to zero**: leave it **enabled** (default, 5 min of inactivity).
   With the LangGraph server polling 24/7 it will rarely trigger, but it costs
   nothing and covers deploys/outages; the app's `wakeUpServer()` retry logic
   tolerates the ~500 ms first-query wake.
3. **Instant restore / history retention**: the retained WAL is billed as
   extra storage. Default is 1 day on paid plans. This database holds
   ephemeral agent state you would never point-in-time-restore, so drop the
   window to a few hours. In the console it's on the project's
   **Settings → Instant restore** page (a slider; some console versions show
   it on the **Backup & Restore** page as the "restore window"/"history
   window", and org members may need admin rights to see it). If the UI
   doesn't surface it, set it via the API — this always works:

   ```bash
   curl -X PATCH "https://console.neon.tech/api/v2/projects/$PROJECT_ID" \
     -H "Authorization: Bearer $NEON_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"project": {"history_retention_seconds": 21600}}'   # 6 hours
   ```
4. **Branches**: delete stale branches. Child branches accrue their own
   storage, and any branch with its own compute bills compute too.
5. **Plan**: compare Launch (~$0.106/CU-hour) vs Scale (~$0.222/CU-hour) rates
   on [neon.com/pricing](https://neon.com/pricing). If you're on Scale without
   needing its features, downgrading roughly halves the compute rate.

## Things that would undo all of this

- **Raising the autoscaling max "for headroom".** With the server always on,
  the ceiling — not the floor — is what turns into money. Only raise it in
  response to observed pressure (Monitoring showing sustained CPU/memory
  saturation during real usage), never preemptively.
- **Long-running transactions.** Neon treats `idle in transaction` as
  activity, so a stuck transaction blocks scale-to-zero.
- **Disabling scale to zero** "for latency". The first-query wake is ~500 ms;
  the app already waits much longer for Render itself.

## Monitoring

- Neon console → **Monitoring** shows compute activity and suspends; if the
  compute never suspends while nobody is using the app, something is holding
  it awake — check for pingers and stray connections.
- Neon console → **Billing → Usage** breaks the invoice into compute,
  storage, and instant-restore lines; re-check after a week with these
  settings to confirm the trend bends.
