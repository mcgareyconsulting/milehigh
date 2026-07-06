# Logging Cleanup Plan

Production (Render, ~30 concurrent users) is drowning in steady-state log noise.
Guiding principle for every task below: **log volume must scale with business
activity (writes, changes, failures) — never with reader count.** Any log line
on a GET/polling success path fails this test. Non-200s, real state changes,
and failures must keep logging exactly as before.

Work in phase order. Each phase is one commit. Run `pytest` after each phase —
all tests must pass before moving on. Do not refactor beyond what a task asks.

---

## Phase 1 — Urgent (security + the dead filter)

### 1.1 Stop logging DB credentials
`app/__init__.py` (~line 303) logs the first 50 chars of
`SQLALCHEMY_DATABASE_URI` at startup. Postgres URLs are
`postgresql://user:password@host/db`, so this leaks the password into Render
logs and `logs/app.log`. Replace it with a log of the environment name and the
DB **host only** (parse with `urllib.parse.urlsplit`; never log username,
password, or the raw string, truncated or not).

### 1.2 Activate the gunicorn access-log filter
`gunicorn.conf.py` defines `_QuietPathFilter` and a custom `Logger` class, but
gunicorn only honors module-level variables that match setting names — the file
never assigns `logger_class = Logger`, so the filter has never run. Add that
assignment. Then extend `_QUIET_PATHS` so it also suppresses successful (200)
access lines for the job-log delta poll: match `/brain/jobs?since=` (the query
string is present in the access line; matching on `?since=` keeps initial
full loads visible). **Do not** suppress non-200 responses — the existing
filter already only drops lines containing `" 200 `; preserve that behavior.

---

## Phase 2 — Volume: silence the steady state

### 2.1 Runtime log level from env
`app/__init__.py` (~line 44) hardcodes `configure_logging(log_level="INFO", ...)`.
Read the level from a `LOG_LEVEL` env var, defaulting to `INFO`. This makes
every `debug` demotion below recoverable in prod without a deploy.

### 2.2 Job-log cursor poll (`app/brain/job_log/routes.py`, `get_jobs`)
Search for `[CURSOR]` in this file (~lines 480–640). Rules:
- Delta polls (`since` param present) that return **zero** rows must emit no
  INFO lines at all. Demote the per-poll narration to `debug`.
- When a delta poll returns rows, emit **one** INFO line carrying the row
  count and latest timestamp.
- Initial full loads (no `since`) may keep one INFO line.
- Leave the invalid-`since` warning at `warning`.

### 2.3 Trello webhook path (`app/trello/__init__.py`, ~lines 95–175)
- "Skipping unhandled webhook" fires for the majority of all Trello traffic
  (every comment, label, checklist tick on the board) → demote to `debug`.
- The per-handled-webhook quartet ("submitted to thread pool", "sync started",
  "sync completed successfully", "Sync completed in Ns") → collapse to a single
  INFO completion line that includes the duration; demote the rest to `debug`.
- Leave every `warning`/`error` (queue full, lock failures, sync failed) alone.

### 2.4 Procore webhook path (`app/procore/__init__.py`)
Procore sends 2–5 duplicate deliveries per change, and our own outbound writes
bounce back as webhooks — so per-delivery INFO lines are multiplied noise.
Demote to `debug`: the "Received Procore webhook" receipt line, the
"Duplicate webhook delivery rejected (burst dedup)" line, the "webhook user"
id-resolution line, the connector bounce-back ("processing for side-effect
diffs") line, and the "no changes applied (DB already in sync)" line.
Keep at INFO: lines reporting an actual DB change (submittal created/updated).
Keep all warnings/errors unchanged.

### 2.5 Remove the rogue basicConfig
`app/sync_lock.py` calls `logging.basicConfig(level=logging.INFO)` at import
time, which can attach a duplicate root handler and fight the central
dictConfig in `app/logging_config.py`. Delete the `basicConfig` call only —
keep the module's `getLogger` line and all its log statements.

### 2.6 Restore stack traces in the shared route wrapper
`app/route_utils.py` (~line 50): the non-`raw_error` branch logs
`error=str(exc)` without a traceback, and it wraps many routes. Add
`exc_info=True` to that `logger.error` call. Change nothing else about the
wrapper (response shape, rollback, status codes).

---

## Phase 3 — Deferred (separate effort; do NOT do as part of this plan)

Listed so nobody "helpfully" starts them here: converting the ~700 runtime
`print()` calls in `app/trello/` and `app/procore/` to loggers; fixing the
stdout formatter mismatch in `app/logging_config.py` (console handler uses the
plain formatter around structlog's pre-rendered JSON); migrating the five
`logging.getLogger` modules to structlog; converting f-string logs to
structured key-values; request-id binding via `structlog.contextvars`.

---

## Guardrails

- **Never** touch `print()` calls anywhere in this plan — including
  `app/*/scripts/` (CLI output, intentional) and `app/seed.py`.
- **Never** change what warnings/errors log, or any response body/status code.
- The heartbeat (`Scheduler heartbeat: alive`, `app/__init__.py`) is
  intentional — leave it.
- Loggers here are a mix of structlog (`get_logger`) and Flask's `app.logger`;
  demotions are just `info` → `debug` on the same logger object. Don't swap
  logger types or rewrite messages beyond what a task specifies.
- Frontend (`console.log` noise in `frontend/src/`) is out of scope.

## Verification

1. `pytest` green after each phase.
2. `grep -rn "SQLALCHEMY_DATABASE_URI" app/__init__.py` — no log statement
   includes the raw value.
3. `grep -n "logger_class" gunicorn.conf.py` — assignment exists.
4. Manual: start the app, hit `GET /brain/jobs?since=<recent ISO timestamp>`
   twice with no data changes → zero INFO lines emitted. Hit it without
   `since` → at most one INFO line.
5. `grep -n "basicConfig" app/ -r` — only matches outside runtime code, if any.
6. Confirm the Render start command runs gunicorn from the repo root (so
   `./gunicorn.conf.py` auto-loads) and does not pass `--logger-class`.
   (Human step — flag it in the PR description.)
