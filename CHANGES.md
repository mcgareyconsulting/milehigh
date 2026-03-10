# Codebase Self-Healing Changelog

Track of all changes made during automated loop iterations on branch `claude_experiment`.

---

## Iteration 1

### 1. `ReleaseEvents.payload_hash` — Added DB-level UniqueConstraint
**File:** `app/models.py`
**Why:** `SubmittalEvents` already had a `UniqueConstraint` on `payload_hash` preventing DB-level duplicates. `ReleaseEvents` only had an application-level check in `JobEventService.create()`, leaving a race window where two concurrent Trello webhook threads could both pass the check and insert duplicate events. Added the same constraint pattern.
**Migration:** `migrations/add_unique_payload_hash_release_events.py`

### 2. Extracted history routes out of `app/__init__.py`
**New file:** `app/history/__init__.py` (Blueprint: `history_bp`)
**Removed from:** `app/__init__.py` (~320 lines)
**Routes moved:**
- `GET /api/jobs/<job>/<release>/history`
- `GET /api/jobs/history`
- `GET /api/submittals/history`
**Helpers moved:**
- `_get_job_change_history()`
- `_get_submittal_change_history()`
- `_extract_new_value_from_payload()`
- `_extract_submittal_new_value_from_payload()`
**Why:** `app/__init__.py` was 1,641 lines. Extracting a clean, self-contained feature group (history/audit) is the lowest-risk first step toward making the file manageable.

---

---

## Architectural Direction (Owner Notes)

**Goal: Simplify and stabilize the core data loop.**

### Keep and tune tightly:
- **Job Log** — core operational view
- **Drafting Work Load** — submittal prioritization
- **Events** (ReleaseEvents, SubmittalEvents) — audit trail
- **Trello integration** — webhook receiver + outbound API (card moves, updates)
- **Procore integration** — webhook receiver + outbound API (submittal status, ball-in-court)

### Direction for webhooks and data flow:
- Each integration directory (`app/trello/`, `app/procore/`, `app/brain/`) should own its own webhook handling and data flow
- Move away from `app/sync/` as a shared coordination layer — that responsibility belongs in the integration directories themselves

### Remove / simplify:
- `sync_lock.py` and the sync lock mechanism — broken and not affecting operational flow; remove it
- Shipping routes (`/shipping/*`) — redundant
- Fab-order routes (`/fab-order/*`) — redundant
- Fix-trello-list routes (`/fix-trello-list/*`) — redundant
- Name-check routes (`/name-check/*`) — redundant
- Files routes (`/files/*`) — redundant
- Seed cross-check route — redundant
- Any feature not directly serving Job Log, DWL, Events, Trello, or Procore

### Guiding principle:
Everything that doesn't directly serve Job Log, Drafting Work Load, or the Trello/Procore data connections can go. Use best judgement — if it's not being called by the frontend or a webhook, it's probably dead weight.

---

## Iteration 2

### 3. Removed dead route groups from `app/__init__.py`
**File:** `app/__init__.py`
**Lines removed:** ~985 (1,315 → 330)
**Routes removed:**
- `GET/POST /shipping/audit`
- `GET/POST /shipping/enforce-excel`
- `GET /shipping/store-at-mhmw/scan`
- `POST /shipping/store-at-mhmw/run`
- `GET /sync/status`
- `GET /sync/stats`
- `GET /seed/cross-check`
- `GET /seed/run-one`
- `GET /fab-order/scan`
- `POST /fab-order/update`
- `GET /fix-trello-list/scan`
- `GET/POST /fix-trello-list/run`
- `GET /name-check/scan`
- `POST /name-check/update`
- `GET /files/list`
- `GET /files/download`
- `GET /files/read-pkl`
**Why:** None of these routes serve Job Log, Drafting Work Load, or the Trello/Procore data connections. They were admin/utility scripts not called by the frontend or any active webhook path.

### 4. Deleted `app/sync_lock.py`
**Why:** Broken and not affecting operational flow per architectural direction. No references remain after route removal.

### 5. Cleaned up unused imports in `app/__init__.py`
**Removed:** `pandas`, `SyncOperation`, `SyncLog`, `SyncStatus`, `seed_from_combined_data`, `incremental_seed_missing_jobs`, `get_trello_excel_cross_check_summary`, `combine_trello_excel_data`, `BackgroundScheduler`, `func`, `datetime`, `timedelta`
**Why:** All were only used by the dead routes now removed.

### 6. Trimmed `API_ROUTE_PREFIXES` in `app/__init__.py`
**Removed prefixes:** `sync/`, `shipping/`, `files/`, `seed/`, `fab-order/`, `fix-trello-list/`, `name-check/`
**Added:** `brain/`
**Why:** Catch-all only needs to know about prefixes that actually have routes.

---

---

## Iteration 3 (current session)

### 7. Deleted all 21 orphaned scripts in `app/scripts/`
**Why:** Zero of the 21 scripts were imported by any route or webhook handler. All were CLI-only invocation wrappers around functions that already live in integration modules. `app/procore/scripts/` was preserved — user confirmed those webhook management scripts are needed.

### 8. Deleted `app/api/routes.py` and cleaned `app/api/__init__.py`
**File:** `app/api/__init__.py`, `app/api/routes.py`
**Why:** `routes.py` was 100% commented out; `api_bp` was never registered. Removed the blueprint definition and the `from app.api import routes` import. `app/api/helpers.py` is kept — it is actively imported by `app/brain/job_log/routes.py` and `app/trello/list_mapper.py`.

### 9. Deleted `app/services/database_mapping.py`
**Why:** 437-line cross-database sync utility with zero callers outside the now-deleted `app/scripts/test_database_mapping.py`. Not imported by any route, webhook, or service.

### 10. Deleted `test_csv_preview.py` (project root)
**Why:** Standalone dev-only script that was the sole remaining caller of `preview_csv_jobs_data` from `app/seed.py`. Not part of any test suite.

### 11. Removed legacy stub routes from `app/procore/__init__.py`
**Removed:**
- `GET /procore/api/webhook/payloads` — explicitly labelled "Legacy endpoint", returned empty array with migration message
- `GET /procore/api/webhook/submittal-data` — same, legacy stub
**Why:** Both were dead stubs left over from when webhook payloads were logged to disk. That mechanism was already removed; the stubs had no callers.

### 12. Removed commented-out dead code from `app/procore/procore.py`
**Removed:** Commented-out `procore_authorization()` function (OAuth flow replaced by current token mechanism)

---

---

## Iteration 4

### 13. Deleted `app/brain/job_log/services/` (entire directory)
**Files deleted:** `outbox_service.py`, `job_event_service.py`
**Why:** Both were shadow duplicates of `app/services/outbox_service.py` and `app/services/job_event_service.py`. Zero imports anywhere in the codebase — the active versions in `app/services/` are what all routes use.

### 14. Deleted `app/brain/job_log/features/fab_order/payloads.py`
**Why:** Defined `UpdateFabOrderRequest` and `FabOrderChangePayload` TypedDicts that were never imported or used anywhere.

### 15. Removed `has_submittals_update_trigger()` from `app/procore/webhook_utils.py`
**Why:** 40-line function with zero callers — not imported by any route, webhook handler, or script.

### 16. Cleaned up `app/combine.py`
**Removed:** `list_duplicate_trello_identifiers()`, `get_excel_data_by_identifier()`, and commented-out example block at bottom
**Why:** Both functions had zero callers. `get_excel_data_by_identifier()` was already marked "Excel functionality removed" in its own comment. Removed unused `collections.defaultdict`, `typing.List/Dict/Tuple` imports.

### 17. Removed `get_card_attachments_by_job_release()` from `app/trello/api.py`
**Why:** 94-line function with zero external callers. (Note: `get_card_attachments_by_card_id` is kept — it IS called internally by `update_mirror_card_date_range`.)

### 18. Removed 4 dead functions from `app/trello/sync.py`
**Removed:** `check_database_connection()`, `compare_timestamps()`, `as_date()`, `is_formula_cell()`
**Why:** All 4 had zero callers — internal or external. Also removed stale comment about OneDrive removal.

### 19. Removed 5 dead imports from `app/trello/sync.py`
**Removed:** `numpy.safe_eval`, `openpyxl`, `pandas as pd`, `pandas.Timestamp`, `math`, `date`, `timezone`, `time` from datetime
**Why:** All became unused after removing the dead functions above.

---

---

## Iteration 6

### 20. Removed `clear_trello_board()` and `sync_releases_to_trello()` from `app/trello/scanner.py`
**Lines removed:** ~278 (1010 → 732)
**Why:** Both functions had zero external callers after `app/scripts/` was deleted in Iteration 3. `sync_releases_to_trello` was only called by the deleted `sync_releases_to_trello.py` script; `clear_trello_board` was only called by `sync_releases_to_trello`.

### 21. Replaced 8-second Procore debounce with `payload_hash` deduplication
**File:** `app/procore/__init__.py`
**Removed:** `DEBOUNCE_SECONDS = 8`, `_recent_submittal_event_for_debounce()`, debounce check block in `procore_webhook()`
**Removed dead imports:** `pathlib.Path`, `datetime.date`, `datetime.timedelta`, `collections.defaultdict`, `pandas`
**Why:** The time-based debounce incorrectly blocked legitimate events (two real changes to the same submittal within 8s). `payload_hash` dedup in `create_submittal_event()` — backed by a DB-level `UniqueConstraint` — is content-based and permanent. Duplicate Procore webhook deliveries will now cause one extra API call but cannot create duplicate events. `SubmittalEvents` already had `UniqueConstraint('payload_hash')` from Iteration 1.

---

## Planned (future iterations)

- Add integration tests for webhook → event → history pipeline
- Evaluate `app/seed.py` (1929 lines, no web callers) — consider archiving or splitting
- Scan `app/procore/procore.py` for dead helper functions within `comprehensive_health_scan` chain
