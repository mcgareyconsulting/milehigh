# MHMW Logging & Emission Standard

How every part of this system — current and future — emits telemetry. The goal is
uniformity: one idiom, one shape, one vocabulary, so everything is queryable together
and log volume scales with business activity, never with reader count.

Status: adopted 2026-07-05. Decisions marked ⚖ were made with explicit trade-offs and
can be revisited; everything else is settled.

Related docs: `docs/observability-guide.md` (the why / the wider landscape),
`docs/logging-cleanup-plan.md` (the volume/hygiene cleanup that preceded this).

---

## 1. One idiom

All runtime code gets its logger exactly one way:

```python
from app.logging_config import get_logger
logger = get_logger(__name__)
```

- **Never** `logging.getLogger(...)` (stdlib) in `app/` runtime code.
- **Never** `app.logger` / `current_app.logger` — Flask's logger bypasses structlog
  and renders a different shape. Use the module-level `get_logger(__name__)` even
  inside routes and webhook handlers.
- **Never** `print()` on a runtime path (anything reachable from a request, webhook,
  scheduler job, or worker thread). `print()` ignores log levels and never reaches the
  file/pipeline. Exception: CLI scripts under `scripts/` and `app/*/scripts/` may
  print — that's their user interface.
- **Never** `logging.basicConfig()` anywhere. Configuration lives solely in
  `app/logging_config.py`.

## 2. Events, not sentences

Log calls take a **stable snake_case event name** plus keyword fields. Data goes in
fields, never interpolated into the message.

```python
# YES
logger.info("submittal_created", submittal_id=sid, project_id=pid, source="webhook")

# NO — unqueryable, and the event name changes every time the wording does
logger.info(f"Successfully created submittal {sid} for project {pid}")
```

- **F-strings (and %-format / .format) are banned in logger calls.** If you need a
  value, it's a field.
- Event names are permanent identifiers (they end up in queries and dashboards).
  Naming: `<noun>_<past_tense_verb>` for state changes (`release_archived`,
  `stage_updated`), `<noun>_<verb>_failed` for failures (`procore_push_failed`),
  `<noun>_<verb>_skipped` for deliberate no-ops. Don't rename an established event
  without checking what queries/dashboards reference it.
- The `meetings/` and `lake/` modules are the house reference for this style.

## 3. Canonical field registry

Reuse these names exactly; never invent a synonym (`uid`, `jobNum`, `sub_id`…).
Add new names here first when a genuinely new concept appears.

| Field | Meaning |
|---|---|
| `request_id` | Correlation id for the request/webhook/job (bound, not hand-passed) |
| `user_id` | Numeric `User.id` of the acting user |
| `job` | Job number string (e.g. `"580"`) |
| `release` | Release number string |
| `job_release` | Combined `job-release` string (e.g. `"580-659"`) |
| `release_id` | Numeric `Releases.id` |
| `submittal_id` | Procore submittal id |
| `project_id` | Procore project id |
| `card_id` | Trello card id |
| `event_id` | `ReleaseEvents` / `SubmittalEvents` row id |
| `operation_id` | Sync-operation id (webhook/queue processing bundle) |
| `feature` | Feature slug (`"meeting_extraction"`, `"pdf_review"`, `"job_log"`) |
| `source` | Origin system: `"trello"`, `"procore"`, `"onedrive"`, `"user"`, `"scheduler"` |
| `status` | Outcome: `"ok"`, `"error"`, `"skipped"`, `"queued"`, HTTP status where apt |
| `duration_ms` | Elapsed time in milliseconds (int) |
| `count` | Number of items processed/returned |
| `error` | `str(exc)` — always paired with `exc_info=True` at ERROR |
| `error_type` | Exception class name |
| `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms` | AI-call ledger fields |

⚖ We use our own domain-shaped registry rather than OpenTelemetry semantic-convention
names. If we adopt an OTel pipeline later, a rename map at the collector translates.

## 4. The levels contract

| Level | Meaning | Rules |
|---|---|---|
| `DEBUG` | Narrative — *how* something happened | Off in prod by default (`LOG_LEVEL` env var). Unlimited chattiness allowed. |
| `INFO` | A state actually **changed** | One line per change, emitted by the layer that **owns** the change (command/service — not echoed by route + command + service). Reads, polls, and no-ops NEVER log at INFO. |
| `WARNING` | Unexpected but handled | Not for normal control flow ("not found" on a user-driven lookup is DEBUG or a 404, not a warning). |
| `ERROR` | An operation failed | **Always** `exc_info=True` (or `logger.exception`). Never sampled, never suppressed, never `str(e)` alone. |

The test for INFO: *would I want one line per occurrence of this in production, forever?*
If the occurrence is a read, the answer is no.

**Failure capture at boundaries:** every call to an external system (Trello, Procore,
Graph, Anthropic) and every background-job/worker/scheduler entry point must catch and
emit an ERROR event with `error`, `error_type`, `exc_info=True`, and correlation fields.
Bare `except: pass` and swallowed exceptions are defects.

## 5. Canonical wide line (the target shape)

⚖ **Target:** every unit of work — HTTP request, webhook delivery, scheduled job run,
outbox batch — emits **exactly one wide completion event** carrying its full context:

```python
logger.info("request_complete", method=..., path=..., status=200, duration_ms=42,
            user_id=17, count=0, request_id=...)
logger.info("webhook_complete", source="procore", event_type="update",
            submittal_id=..., status="ok", duration_ms=310, changes=2)
```

- The wide line is INFO; the play-by-play that used to be many INFO lines becomes
  DEBUG or fields on the wide line.
- Implementation is a request/job-scoped accumulator (Flask `g` /
  `structlog.contextvars`): middleware creates it, business logic adds fields, a
  `finally`/`teardown` emits it — **even when an exception unwinds the stack** (then
  with `status="error"`).
- Until the accumulator middleware exists, new code should still *think* in this shape:
  prefer one rich completion event over several thin progress events.

## 6. Log line vs. event table (the durability rule)

Two streams, one rule:

> **If losing the record would matter next week, it's a database event row.
> If it only matters while debugging, it's a log line.**

- DB event rows (`ReleaseEvents`, `SubmittalEvents`, ledgers): business state changes,
  external sync outcomes, integration failures, auth/admin actions, AI calls. These are
  what the Brain and audit queries read. Durable, schema'd, never in stdout only.
- Log lines: everything else. Assume they evaporate (Render stdout rotates away).
- Never put a business fact only in a log line; never put debug chatter in Postgres.

## 7. Correlation

Correlation fields (`request_id`, `operation_id`, `user_id`) are **bound once** per
unit of work via `structlog.contextvars` (at `before_request` / job entry / thread
handoff) and ride on every line automatically. Hand-threading ids through function
signatures just to log them is a smell; binding is the mechanism. New background
paths must propagate the binding across the async boundary.

## 8. Output format

- stdout: **single-rendered JSON**, one object per line, ISO-8601 UTC timestamps,
  `event` as the message key. (No plaintext wrapper around a JSON payload — the
  double-render in `logging_config.py` is a known defect being fixed.)
- Secrets and credentials never appear in any log field at any level: no tokens, no
  API keys, no passwords, no connection strings (log the host, never the URI). When
  logging payloads, log ids and counts, not bodies.

## 9. Migration policy (the ratchet)

⚖ Existing violations (~700 runtime `print()`s, f-string logs, stdlib loggers) are
migrated by **ratchet**, not big-bang:

1. **All new code** follows this standard fully — no exceptions.
2. **Any file you touch** for other reasons: migrate the logging in the code you're
   already changing (same PR, no scope creep beyond it).
3. **Hot paths** (`app/trello/api.py`, `app/procore/webhook_utils.py`, webhook
   handlers) get dedicated conversion tasks — see `docs/logging-cleanup-plan.md`
   Phase 3.
4. Never mass-rewrite untouched cold paths just for style.

## Quick reference (pin this)

```python
from app.logging_config import get_logger
logger = get_logger(__name__)

logger.debug("cursor_filter_applied", since=since_ts)                  # narrative
logger.info("stage_updated", release_id=rid, from_stage=a, to_stage=b) # state change
logger.warning("trello_queue_full", queued=n)                          # anomaly, handled
logger.error("procore_push_failed", submittal_id=sid, error=str(e),
             error_type=type(e).__name__, exc_info=True)               # failure + trace
```

- one idiom (`get_logger`) · events not sentences · registry field names ·
  INFO = state changed · errors always carry tracebacks · one wide line per unit of
  work · durable facts go to Postgres, not stdout · bind correlation, don't thread it.
