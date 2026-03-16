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
Set `ENVIRONMENT` in `.env` to `local`, `sandbox`, or `production`. This controls which database and API credentials are used (`app/config.py`, `app/db_config.py`).

## Architecture

Flask backend + React 19 frontend. The frontend is built to `frontend/dist/` and served as static files by Flask in production. In local dev, run both servers separately and proxy API calls from Vite to Flask.

### Data flow
Three external systems feed into the app via webhooks and scheduled polling:

1. **Trello** (`app/trello/`) — receives webhook events (card moves, edits, deletes). Events are queued and processed via a thread pool. A sync lock (`app/sync_lock.py`) prevents Trello and OneDrive from processing concurrently.

2. **Procore** (`app/procore/`) — receives submittal webhook events. Parses ball-in-court, status, type, due date. Writes to `Submittals` and `SubmittalEvents` tables. Sends outbound updates back to Procore.

3. **OneDrive/Excel** (`app/onedrive/`) — APScheduler polls an Excel file hourly, converting rows to Trello cards.

Outbound API failures are queued in `TrelloOutbox`/`ProcoreOutbox` tables and retried by `OutboxService`.

### Key models (`app/models.py`)
- `Job` — job log entries (table: `jobs`)
- `Jobs` — geofence/job site records (table: `job_sites`)
- `Submittals` — Procore submittals (table: `submittals`; previously `procore_submittals`)
- `ReleaseEvents` / `SubmittalEvents` — audit event streams
- `TrelloOutbox` / `ProcoreOutbox` — reliable outbound delivery queue
- `WebhookReceipt` — idempotency for incoming webhooks
- `User`, `SyncOperation`, `SyncLog`, `JobChangeLog`, `ProcoreToken`

### Naming conflicts to keep in mind
- `Job` (main) is the job log. `Jobs` is geofences (table `job_sites`).
- `Submittals` was renamed from `ProcoreSubmittal`; old scripts alias it: `from app.models import Submittals as ProcoreSubmittal`.
- Integration code that bridges branches uses: `from app.models import Job as Releases`.

### Migration order
M1 (users) → M2 (rename submittals table) → M3 (release_events) → M4 (submittal_events) → M5 (procore_outbox) → M6 (webhook_receipts)

### Brain / services layer
- `app/brain/` — query and transformation logic for job log, drafting work load (DWL), and map views
- `app/services/` — `OutboxService` (retry), `JobEventService` (deduplication), `DatabaseMappingService` (field mappings)
- `app/history/` — event audit trail queries

### Frontend structure
React pages under `frontend/src/pages/`, reusable components under `frontend/src/components/`, API calls in `frontend/src/services/`, custom hooks in `frontend/src/hooks/`.
