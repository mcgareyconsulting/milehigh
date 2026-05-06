# Procore Webhook Hardening Plan (Phase 1 + Phase 2)

Tracks the cleanup work surfaced by the 2026-05-05 investigation of submittals
71374996 (BIC drift) and 69723920 (status drift). One-shot resync was applied
via `scripts/resync_drifted_submittals.py`; the bugs that caused the drift are
listed below.

## Goals

1. Stop losing legitimate events to over-eager dedup. (Phase 1)
2. Stop losing fields to Procore's eventual-consistency races. (Phase 1)
3. Stop relying on webhooks being delivered at all — self-heal drift on a schedule. (Phase 2)

---

## Phase 1 — Surgical fixes

### 1.1 — Remove `payload_hash` unique constraint

**Why.** `migrations/add_unique_payload_hash_submittal_events.py` creates a
unique index on `submittal_events.payload_hash`. Two real human actions
producing identical `{old, new}` payloads collide and the second is silently
dropped. This is what produced the audit gaps for 71374996 on 4/29 14:26 and
4/30 13:22:34 / 13:26:33. Burst dedup at the receipt layer is the right place
to dedup, not content-based.

**Files.**
- New migration: drop index `uq_submittal_events_payload_hash`. Confirm
  naming convention vs the existing M1–M6 files in `migrations/versions/`
  before naming.
- `app/procore/helpers.py:295–305` — remove the `IntegrityError` "duplicate"
  branch in `create_submittal_event`. Re-raise on any IntegrityError so
  genuine errors aren't masked.
- Keep the `payload_hash` column. Still useful for forensic queries.

**Acceptance.**
- Migration applies cleanly on a prod copy locally.
- Running the resync script a second time would no longer be blocked by
  hash collision.
- Test: insert two `SubmittalEvents` rows with identical `payload_hash`
  succeeds.

---

### 1.2 — Use `Procore-Delivery-Id` header for burst dedup

**Why.** `is_duplicate_webhook` keys on
`sha256(resource_id:project_id:event_type:bucket)` where
`bucket = int(time / 15)`. At bucket boundaries, two deliveries 1–2 seconds
apart can land in different buckets and both pass dedup. We saw this on
71374996 (4/30 13:26:42–43 logs) and 4/29 14:26:30 (a webhook 2s after the
first was processed despite being a duplicate). Procore stamps each delivery
with a unique header — verify exact header name from a recent webhook payload.

**Files.**
- `app/procore/__init__.py:96–108` — pass
  `request.headers.get("Procore-Delivery-Id")` (or correct header) into
  `is_duplicate_webhook`.
- `app/procore/helpers.py:213` — `is_duplicate_webhook` accepts optional
  `delivery_id`. If present, receipt key =
  `sha256("procore:delivery:{delivery_id}")`. Otherwise fall back to the
  existing bucketed scheme.
- Add a small log line on dedup that says which strategy fired.

**Acceptance.**
- A delivery with a known `Delivery-Id` writes a receipt; the same delivery
  replayed within an hour is rejected as duplicate (vs. only-15s today).
- A webhook without the header still works (back-compat).
- Bucket-boundary scenario from the 4/30 logs no longer leaks duplicates.

**Open question.** Confirm the header name. If you have a recent webhook
captured in `WebhookReceipt`'s logs, fish out the headers; otherwise add one
log line to the handler that dumps `request.headers` and check after the
next webhook arrives.

---

### 1.3 — Retry-on-mismatch in `check_and_update_submittal`

**Why.** Procore commits multi-field updates non-atomically. A single
poll-back can return BIC updated but `status` stale (69723920) or the BIC
array stale relative to workflow sequence (71374996). One short retry catches
the common eventual-consistency window.

**Files.**
- `app/procore/procore.py:613` `check_and_update_submittal` — after the first
  `handle_submittal_update` call, if any tracked field disagrees with DB,
  sleep ~1.5s and call `handle_submittal_update` again. If the second result
  differs from the first on *any* field, prefer the second (more recent).
  Apply changes from the later read.
- `app/config.py` — add `PROCORE_WEBHOOK_RETRY_ENABLED` (default `True`) and
  `PROCORE_WEBHOOK_RETRY_DELAY_SECONDS` (default `1.5`) so we can disable
  without redeploy if it causes issues.

**Acceptance.**
- Mock Procore client returning stale-then-fresh shows the handler picks the
  fresh read.
- Mock Procore client returning identical reads applies them once, no
  double-apply.
- Webhook latency increases by ~1.5s only when there's a real change; no-op
  webhooks skip the retry (since the first read matched DB).

**Risk.** Adds 1.5s latency per real-change webhook. Webhooks already
process async on a worker pool, so user-facing impact is zero. Procore
delivery retry budgets are minutes, not seconds.

---

### Phase 1 tests

- `tests/procore/test_dedup.py` — bucket boundary scenario; delivery-id
  scenario; both with and without header.
- `tests/procore/test_check_and_update_retry.py` — mock client returning
  `[stale, fresh]` reads; assert handler applies the fresh one.
- `tests/procore/test_event_dedup_removed.py` — assert `create_submittal_event`
  accepts identical-hash inserts.

**Total Phase 1 effort:** ~1 working day if no Procore API surprises.

---

## Phase 2 — Reconciliation safety net

### 2.1 — Reconciliation service

**Why.** Phase 1 narrows the failure surface but doesn't close it. Procore
sometimes doesn't fire a webhook at all (or a delivery is genuinely lost
during a deploy). The system needs to self-heal.

**Files.**
- New: `app/services/submittal_reconciliation.py`
  - `reconcile_submittal(submittal_id) -> ReconciliationResult` — fetch
    Procore truth, diff vs DB across `status`, `ball_in_court`, `title`,
    `submittal_manager`. For each drift: update the DB row, write a
    `SubmittalEvents` row with `payload['reconciliation'] = True` and
    `payload['detected_at']`, source `'Procore'` for consistency with origin.
  - `reconcile_active_submittals(stale_after_hours=24) -> List[ReconciliationResult]`
    — iterate `Submittals.query.filter(Submittals.status.in_(['Open', 'Draft']),
    Submittals.last_updated < now - stale_after_hours)`.
- Reuses logic from `scripts/resync_drifted_submittals.py` — that script
  becomes a thin wrapper over the service.

**Acceptance.**
- In-memory DB test: seed a row with stale BIC, mock Procore to return current
  truth, call `reconcile_submittal`, verify row updated + event written +
  payload tagged `reconciliation: True`.
- The 71374996 and 69723920 fixes done manually on 2026-05-05 would have been
  caught and applied automatically by this service within an hour of the
  missed webhook.

---

### 2.2 — Scheduled job

**Files.**
- `app/__init__.py` — add an APScheduler job calling
  `reconcile_active_submittals`. Schedule: hourly (configurable via
  `SUBMITTAL_RECONCILE_INTERVAL_MINUTES`, default 60).
- Gate on the same `WERKZEUG_RUN_MAIN`/`IS_RENDER_SCHEDULER` check the
  existing scheduler uses.
- Wrap the call in a `SyncContext` so it gets a correlation id and structured
  logging.

**Acceptance.**
- Job runs every hour on the scheduler worker only (not duplicated across web
  workers).
- Job logs: number of submittals checked, number drifted, list of
  `submittal_id`s repaired.

**Tunables.**
- `SUBMITTAL_RECONCILE_INTERVAL_MINUTES` — interval.
- `SUBMITTAL_RECONCILE_STALE_AFTER_HOURS` — minimum row idle time before
  reconciliation considers it a candidate. Don't reconcile rows that just got
  webhook updates 30 seconds ago — they're already fresh.
- `SUBMITTAL_RECONCILE_MAX_BATCH_SIZE` — cap per-run to avoid blowing the
  Procore rate limit. Iterate in batches with delay if the eligible set is
  large.

---

### 2.3 — Visibility

**Files.**
- `app/brain/admin/routes.py` — new endpoint
  `GET /admin/reconciliation/recent` returns last N reconciliation events
  (filter `SubmittalEvents.payload['reconciliation'] == True`).
- Frontend: add a small admin page or extend the existing history view with a
  "reconciliation" filter. Lower priority — JSON endpoint is enough to start.

**Acceptance.**
- Admin can see, after a reconciliation run, exactly which submittals were
  repaired and what changed. Removes the need for manual `psql` digging.

---

### Phase 2 tests

- `tests/procore/test_reconciliation.py` — service-level tests with seeded DB
  rows + mocked Procore client. Cases: no drift (no-op), single-field drift
  (BIC), multi-field drift, Procore unreachable (graceful skip), submittal
  not in Procore anymore (log + skip, don't delete).
- Manual validation in sandbox: introduce intentional drift on a sandbox
  submittal, run job, verify repair.

**Total Phase 2 effort:** ~2 working days.

---

## Rollout order

1. **Phase 1.1** — drop unique constraint + remove dedup branch. Smallest
   blast radius.
2. **Phase 1.3** — retry-on-mismatch. Biggest event-coverage improvement.
3. **Phase 1.2** — delivery-id dedup. Requires verifying header name.
4. **Phase 2.1 + 2.2 + 2.3** — ship together as one PR.

Each phase ships independently. Rollback for each is a single revert.

---

## Open questions

1. Confirm Procore webhook delivery header name (need one real webhook to
   inspect).
2. For Phase 2, which fields should the reconciliation service compare? Today
   the handler tracks `ball_in_court`, `status`, `title`, `submittal_manager`.
   Probably also `due_date` given recent activity on it.
3. Phase 2 reconciliation must skip rows that are *intentionally* manually
   overridden in Brain (e.g., status flipped via
   `/brain/drafting_work_load/.../status`). Need a flag or a "last brain
   override" timestamp to know not to clobber a recent local edit.

---

## Bugs surfaced during the 2026-05-05 investigation

1. **Payload-hash dedup suppresses legitimate events** when a value oscillates
   back through the same string (71374996 audit gaps). Addressed by 1.1.
2. **`parse_ball_in_court_from_submittal` trusts the lagging `ball_in_court`
   array** over current pending-approver state. When the array lags a
   workflow sequence advance, we record the wrong BIC (71374996 BIC drift).
   Addressed by 1.3 (retry catches the lag) and Phase 2 (reconciliation
   self-heals if it doesn't).
3. **Multi-field atomic Procore actions can leak fields silently** when
   Procore's API returns a partially-propagated view at the moment we poll
   (69723920 status drift). Addressed by 1.3 + Phase 2.
4. **Burst-dedup bucket boundary leaks duplicates.** Addressed by 1.2.
