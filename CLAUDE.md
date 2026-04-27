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
- `Job` — job log entries (table: `jobs`)
- `Jobs` — geofence/job site records (table: `job_sites`)
- `Submittals` — Procore submittals (table: `submittals`; previously `procore_submittals`)
- `ReleaseEvents` / `SubmittalEvents` — audit event streams with payload-hash dedup
- `TrelloOutbox` / `ProcoreOutbox` — reliable outbound delivery queue
- `BoardItem` / `BoardActivity` / `Notification` — bug tracker and notifications
- `WebhookReceipt` — idempotency for incoming webhooks
- `User`, `SyncOperation`, `SyncLog`, `JobChangeLog`, `ProcoreToken`

### Naming conflicts to keep in mind
- `Job` (main) is the job log. `Jobs` is geofences (table `job_sites`).
- `Submittals` was renamed from `ProcoreSubmittal`; old scripts alias it: `from app.models import Submittals as ProcoreSubmittal`.
- Integration code that bridges branches uses: `from app.models import Job as Releases`.

### Migration order
M1 (users) → M2 (rename submittals table) → M3 (release_events) → M4 (submittal_events) → M5 (procore_outbox) → M6 (webhook_receipts)

### Brain / services layer
- `app/brain/` — query and transformation logic for job log, drafting work load (DWL), map views, and the board/bug tracker
- `app/services/` — `OutboxService` (retry), `JobEventService` (deduplication with time-bucketed hashing), `DatabaseMappingService` (field mappings)
- `app/history/` — event audit trail queries

### Logging
Structured logging via `structlog` (`app/logging_config.py`). Use `get_logger(__name__)` in every module. `SyncContext` context manager wraps sync operations with correlation IDs and timing. Output is JSON-structured; also writes to rotating file (`logs/app.log`, 10MB max, 5 backups).

### Frontend structure
React pages under `frontend/src/pages/`, reusable components under `frontend/src/components/`, API calls in `frontend/src/services/`, custom hooks in `frontend/src/hooks/`. Uses Tailwind CSS, react-router-dom, axios, @dnd-kit for drag-drop, maplibre-gl for maps.
