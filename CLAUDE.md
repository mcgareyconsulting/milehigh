# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
python run.py              # Run Flask app on http://localhost:8000
flask db migrate -m "msg"  # Generate migration from model changes
flask db upgrade           # Apply migrations
pytest                     # Run all tests
pytest tests/dwl/          # Run a specific test suite
pytest tests/test_hours_summary.py  # Run a single test file
```

### Frontend
```bash
cd frontend
npm run dev      # Vite dev server on http://localhost:5173
npm run build    # Build to frontend/dist/ (served by Flask in prod)
npm run lint     # ESLint
```

### Environment
Set `ENVIRONMENT` in `.env` to `local`, `sandbox`, or `production`. This controls which database and API credentials are used (`app/config.py`, `app/db_config.py`). No `.env.example` exists; infer required variables from `app/config.py`.

### Testing
Tests use `TESTING=1` env var (set automatically in `tests/conftest.py`) to force in-memory SQLite, preventing any connection to real databases. Domain-specific test suites live in subdirectories (`tests/dwl/`, `tests/procore/`, `tests/brain/`) with their own `conftest.py` fixtures.

Test layering: pure unit (no Flask/DB) → service (real logic, in-memory DB or mocked DB) → integration (HTTP via `test_client` + in-memory DB). External services (Procore, Trello, OneDrive) are always mocked; the DB is always real (in-memory). Shared fixtures (`app`, `client`, `mock_admin_user`, `mock_non_admin_user`) live in `tests/conftest.py`. See `tests/README.md` for the full strategy, coverage map, and known gaps.

## Architecture

Flask backend + React 19 frontend. The frontend is built to `frontend/dist/` and served as static files by Flask in production. In local dev, run both servers separately and proxy API calls from Vite to Flask.

### Blueprints
The app registers these blueprints in `app/__init__.py`: `trello_bp`, `procore_bp`, `brain_bp`, `auth_bp`, `history_bp`, `admin_bp`, `onedrive_bp`.

### Authentication (`app/auth/`)
Session-based auth using Flask sessions. User model has role flags: `is_admin`, `is_drafter`, `is_active`, plus `password_set` for the first-login flow.

Key decorators in `app/auth/utils.py`:
- `@login_required` — returns 401 if not authenticated
- `@admin_required` — returns 403 if not admin
- `@drafter_or_admin_required` — returns 403 if neither

Helper: `get_current_user()` returns the `User` from session (returns `None` outside request context, e.g. background threads).

### Data flow
Three external systems feed into the app via webhooks and scheduled polling:

1. **Trello** (`app/trello/`) — receives webhook events (card moves, edits, deletes). Events are queued (`Queue(maxsize=1000)`) and processed via a `ThreadPoolExecutor(max_workers=10)`. A sync lock (`app/sync_lock.py`) prevents Trello and OneDrive from processing concurrently.

2. **Procore** (`app/procore/`) — receives submittal webhook events. Parses ball-in-court, status, type, due date. Writes to `Submittals` and `SubmittalEvents` tables. Has burst dedup (15-second window). Sends outbound updates back to Procore.

3. **OneDrive/Excel** (`app/onedrive/`) — APScheduler polls an Excel file hourly, converting rows to Trello cards.

Outbound API failures are queued in `TrelloOutbox`/`ProcoreOutbox` tables and retried by `OutboxService` with exponential backoff (2^n seconds, max 5 retries).

### Background processing (`app/__init__.py`)
- **APScheduler** with a 3-worker thread pool. Only starts on one process (checks `WERKZEUG_RUN_MAIN` or `IS_RENDER_SCHEDULER` env var to avoid duplication in multi-worker deploys).
- **Scheduled jobs**: Trello queue drainer (every 5 min), heartbeat (every 30 min).
- **Daemon thread**: `outbox_retry_worker` runs continuously, processing pending outbox items (2s sleep when idle, 0.5s when active, 5s on error).

### Board / Bug Tracker (`app/brain/board/`)
Admin-only Kanban board for tracking bugs, features, and tasks. All routes require `@admin_required`.

Models: `BoardItem` (status: open/in_progress/deployed/closed, priority: low/normal/high/urgent, category, position for drag-drop), `BoardActivity` (comments and status_change records), `Notification` (in-app @mention notifications).

Comment creation auto-parses `@FirstName` mentions and creates `Notification` records. Frontend polls `/brain/notifications/unread-count` for the notification bell.

### Key models (`app/models.py`)
- `Releases` — current job log entries (table: `releases`); the model the app reads/writes
- `Job` — legacy job log model (table: `jobs`); kept for older code paths. Integration code that bridges branches aliases `from app.models import Job as Releases`.
- `Projects` — geofence/job site records (table: `projects`); formerly `Jobs` (table `job_sites`). Has `geofence_geojson` (JSON polygon) as the single canonical geometry column, used by both the map renderer and the on-site location filter. Links to job log by `job_number` string value, not FK.
- `ProjectManager` — PM display rows (color, name) used by the map and PM views; linked to `Projects` via `pm_id` FK
- `Submittals` — Procore submittals (table: `submittals`; previously `procore_submittals`)
- `ReleaseEvents` / `SubmittalEvents` — audit event streams with payload-hash dedup
- `TrelloOutbox` / `ProcoreOutbox` — reliable outbound delivery queue
- `BoardItem` / `BoardActivity` / `Notification` — bug tracker and notifications
- `WebhookReceipt` — idempotency for incoming webhooks
- `User`, `SyncOperation`, `SyncLog`, `JobChangeLog`, `ProcoreToken`

### Naming conflicts to keep in mind
- `Releases` (table `releases`) is the current job log. `Job` (table `jobs`) is the legacy model — most application code uses `Releases`.
- `Projects` (table `projects`) holds geofence/job-site rows; replaced the former `Jobs` model (table `job_sites`).
- `Submittals` was renamed from `ProcoreSubmittal`; old scripts alias it: `from app.models import Submittals as ProcoreSubmittal`.
- Integration code that bridges branches uses: `from app.models import Job as Releases`.
- The Projects geofence is stored in a single column, `geofence_geojson` (the previous split with a `geometry` column was consolidated; both the on-site filter and the map renderer read from `geofence_geojson`).

### Migration order
M1 (users) → M2 (rename submittals table) → M3 (release_events) → M4 (submittal_events) → M5 (procore_outbox) → M6 (webhook_receipts)

### Brain / services layer
- `app/brain/` — query and transformation logic for job log, drafting work load (DWL), map views, and the board/bug tracker
- `app/brain/job_log/features/` — feature folders that own one bounded behavior each (`fab_order/`, `notes/`, `stage/`, `start_install/`). Each folder has `command.py` (DB write + event + outbox + cascade) plus optionally `events.py`, `payloads.py`, `results.py` and any one-off migrations or helpers. Commands accept `defer_cascade=True` and `undone_event_id` for use by the undo endpoint. The Job Log routes file delegates here rather than holding the logic inline.
  - `fab_order/renumber_fabrication.py` — admin button on Job Log; compresses FABRICATION-group `fab_order` to a contiguous block starting at 3, preserves ties and the 80.555 placeholder, queues Trello sync only when `Config.FAB_ORDER_FIELD_ID` is set.
  - `fab_order/migrate_unified.py` — one-time tier migration (Complete=NULL, tier 1 = 1, tier 2 = 2, dynamic stages 3+).
  - `start_install/clear_hard_date_cascade.py` — idempotently clears a hard `start_install` date (`start_install_formulaTF=True`, `start_install_formula=None`) when a release enters the complete zone: stage='Complete' (via `UpdateStageCommand`), job_comp='X' (via `update_job_comp` route), or invoiced='X' (via `update_invoiced` route). Emits a child `ReleaseEvents` row linked by `parent_event_id` for audit bundling. No-op when the date is already formula-driven.
- `app/services/` — `OutboxService` (retry), `JobEventService` (deduplication with time-bucketed hashing), `DatabaseMappingService` (field mappings)
- `app/history/` — event audit trail queries
- `scripts/` — operational scripts run from the CLI (e.g. `scripts/refresh_jobsites_from_procore.py` rebuilds `docs/jobsites.json` from Procore project data and upserts `ProjectManager` rows). Default is dry-run; pass `--apply` to write.

### Undo
The `/brain/events/<id>/undo` endpoint (in `app/brain/job_log/routes.py`) reverses a `ReleaseEvents` row. Undoable actions: `update_stage`, `update_fab_order`, `update_notes`, `update_start_install`. The undo re-runs the appropriate command with the original "from" value, passing `undone_event_id` to perturb the dedup hash and link the new event to its source. Linked child events (e.g. `job_comp` cascade from a stage change) are also reverted in the same bundle, and scheduling recalc runs once after all reverts. A symmetric `/brain/submittal-events/<id>/undo` exists for Procore submittal events.

### Fab order renumber
`/brain/renumber-fabrication-fab-orders` (admin-only POST) compresses FABRICATION-group `fab_order` values to a contiguous block starting at 3, preserving relative order. Supports `?dry_run=true`. Implementation: `app/brain/job_log/features/fab_order/renumber_fabrication.py`. `DEFAULT_FAB_ORDER` (80.555) rows are preserved as-is. Rows sharing the same current fab_order share the same new value.

### Logging
Structured logging via `structlog` (`app/logging_config.py`). Use `get_logger(__name__)` in every module. `SyncContext` context manager wraps sync operations with correlation IDs and timing. Output is JSON-structured; also writes to rotating file (`logs/app.log`, 10MB max, 5 backups).

### Frontend structure
React pages under `frontend/src/pages/`, reusable components under `frontend/src/components/`, API calls in `frontend/src/services/`, custom hooks in `frontend/src/hooks/`. Uses Tailwind CSS, react-router-dom, axios, @dnd-kit for drag-drop, maplibre-gl for maps.
