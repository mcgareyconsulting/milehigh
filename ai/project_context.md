# Project Context: Mile High Metal Works — Trello/Procore Sync Brain

## System Overview

This is an internal operations tool for a structural steel fabrication company. It acts as a **sync brain** between three systems: **Trello** (job workflow board), **Procore** (construction project management), and an internal **SQLite/PostgreSQL database** exposed via a React frontend.

The system's core purpose is to keep Trello cards (tracking fabrication job releases through production stages) and Procore submittals (tracking architectural submittal approval workflows) in sync with an internal database — and to provide a unified UI for operations staff.

Key capabilities:
- Receive Trello webhooks → update internal job/release records
- Receive Procore webhooks → update submittal records and trigger DWL reordering
- Let frontend users update job stages, fab order, notes → propagate changes back to Trello via Outbox
- Manage a Drafting Work Load (DWL) priority queue for Procore submittals
- Display a geofenced jobsite map with project manager overlays

---

## Technology Stack

### Backend
| Layer | Technology |
|---|---|
| Web framework | Flask 3.1 (Python 3.9) |
| ORM | Flask-SQLAlchemy 2.0 / SQLAlchemy 2.0 |
| Database (local/test) | SQLite (`instance/jobs.sqlite`) |
| Database (sandbox/prod) | PostgreSQL (hosted on Render) |
| Background tasks | Python `threading` (daemon thread for outbox retry) |
| Async webhook handling | `concurrent.futures.ThreadPoolExecutor` (10 workers) |
| Auth | Session-based (Flask sessions, password hashing) |
| Logging | `structlog` + rotating file handler (`logs/app.log`) |
| CORS | Flask-CORS |
| HTTP client | `requests` |
| Data processing | `pandas`, `numpy`, `openpyxl` |
| Scheduling | `APScheduler` (in dependencies; limited active use) |

### Frontend
| Layer | Technology |
|---|---|
| Framework | React 19 |
| Routing | React Router v7 |
| Build tool | Vite 7 |
| Styling | Tailwind CSS 3 |
| Map | MapLibre GL 4 |
| Drag & drop | dnd-kit (core + sortable) |
| HTTP client | Axios |
| PDF export | jsPDF + jsPDF-autotable |

### External APIs
| Service | Purpose | Auth method |
|---|---|---|
| Trello API | Job board (card moves, updates, custom fields) | API Key + Token |
| Procore API | Submittal data, status updates | OAuth2 client credentials |
| Azure AD | Configured in `.env`; intended for auth (not yet active in code) |

---

## Repository Structure

```
trello_sharepoint/
├── run.py                    # Entrypoint: create_app() + run on port 8000
├── wsgi.py                   # WSGI entrypoint for gunicorn
├── requirements.txt          # Python dependencies
├── pytest.ini                # Test config
│
├── app/                      # Flask application package
│   ├── __init__.py           # App factory: create_app(), blueprint registration, outbox worker
│   ├── config.py             # Config classes (Local/Sandbox/Production), env-based switching
│   ├── db_config.py          # Database URI selection per environment, SQLAlchemy pool settings
│   ├── models.py             # All SQLAlchemy models
│   ├── logging_config.py     # structlog setup, SyncContext helper
│   ├── datetime_utils.py     # Mountain Time formatting
│   ├── sync_lock.py          # File-based sync lock (legacy, mostly unused)
│   ├── combine.py            # Excel + Trello data merging (legacy)
│   ├── seed.py               # DB seeding utilities
│   ├── users.py              # User management helpers
│   │
│   ├── trello/               # Trello integration
│   │   ├── __init__.py       # Blueprint + webhook route + ThreadPoolExecutor
│   │   ├── sync.py           # sync_from_trello(): core webhook processing logic
│   │   ├── api.py            # Trello REST API wrappers
│   │   ├── utils.py          # Webhook parsing, datetime utils, sort helpers
│   │   ├── list_mapper.py    # TrelloListMapper: Trello list name ↔ DB stage mapping
│   │   ├── operations.py     # SyncOperation CRUD helpers
│   │   ├── context.py        # sync_operation_context() context manager
│   │   ├── logging.py        # safe_log_sync_event(), safe_sync_op_call()
│   │   ├── card_creation.py  # create_trello_card_from_excel_data()
│   │   ├── scanner.py        # Trello board scanning utilities
│   │   └── helpers.py        # Misc helpers
│   │
│   ├── procore/              # Procore integration
│   │   ├── __init__.py       # Blueprint
│   │   ├── procore.py        # Core: webhook handling, submittal sync, echo detection
│   │   ├── procore_auth.py   # OAuth2 client credentials token management
│   │   ├── client.py         # get_procore_client() factory
│   │   ├── api.py            # Procore REST API wrappers
│   │   ├── helpers.py        # BIC parsing, user ID resolution, event creation
│   │   ├── webhook_utils.py  # Webhook deduplication (WebhookReceipt)
│   │   └── scripts/          # One-off admin scripts (check, create, delete, sync)
│   │
│   ├── brain/                # Domain logic
│   │   ├── __init__.py       # brain_bp Blueprint
│   │   ├── job_log/          # Job Log domain
│   │   │   ├── routes.py     # API endpoints for jobs, releases, CSV upload
│   │   │   ├── utils.py      # serialize_value() and misc helpers
│   │   │   ├── outbox.py     # Job outbox helpers
│   │   │   ├── job_events.py # Job event helpers
│   │   │   ├── scheduling/   # Schedule calculator (business days, ETA, install dates)
│   │   │   └── features/     # Feature-specific logic (fab_order, notes)
│   │   ├── drafting_work_load/ # DWL domain
│   │   │   ├── routes.py     # API endpoints for submittal ordering
│   │   │   ├── engine.py     # Pure business logic: DraftingWorkLoadEngine, SubmittalOrderingEngine, UrgencyEngine, LocationEngine
│   │   │   └── service.py    # DB-touching service layer wrapping engine
│   │   └── map/              # Jobsite map domain
│   │       ├── routes.py     # Map API endpoints
│   │       └── utils/        # Geofence utilities
│   │
│   ├── auth/                 # Authentication
│   │   ├── routes.py         # /api/auth/login, /logout, /me
│   │   └── utils.py          # login_required decorator, get_current_user()
│   │
│   ├── api/                  # Internal API (currently mostly commented out)
│   │   ├── routes.py         # Disabled /api/jobs endpoint
│   │   └── helpers.py        # transform_job_for_display()
│   │
│   ├── services/             # Cross-cutting services
│   │   ├── outbox_service.py # OutboxService: add(), process_item(), process_pending_items()
│   │   ├── job_event_service.py # JobEventService: create(), close()
│   │   ├── system_log_service.py # SystemLogs service
│   │   └── database_mapping.py  # DB mapping utilities
│   │
│   ├── history/              # History blueprint (event log viewing)
│   └── admin/                # Admin blueprint (health scan, admin page)
│
├── frontend/                 # React SPA
│   ├── src/
│   │   ├── App.jsx           # Router, auth gate, route definitions
│   │   ├── components/       # Shared UI components
│   │   │   ├── AppShell.jsx  # Layout with Navbar
│   │   │   ├── Navbar.jsx    # Top nav with QuickSearch
│   │   │   └── ...
│   │   ├── pages/            # Route-level page components
│   │   │   ├── JobLog.jsx    # Main job tracking table
│   │   │   ├── Events.jsx    # Job event history
│   │   │   ├── DraftingWorkLoad.jsx # Submittal priority queue
│   │   │   ├── PMBoard.jsx   # PM Kanban board
│   │   │   └── maps/JobsiteMap.jsx # MapLibre map with geofences
│   │   ├── hooks/            # Custom React hooks (data fetching, filters, drag & drop)
│   │   ├── services/         # Axios API client modules per domain
│   │   └── utils/            # Formatting, sorting, PDF export, auth helpers
│   └── dist/                 # Built assets served by Flask
│
├── migrations/               # One-off Python migration scripts (run manually)
├── tests/                    # pytest test suite
├── fences/                   # GeoJSON geofence data files
├── docs/                     # Architecture notes and feature docs
└── instance/                 # SQLite database (local dev)
    └── jobs.sqlite
```

---

## Core Domains

### 1. Releases (Job Log)
**Model**: `Releases` — the primary entity. Represents one release of one job (a steel fabrication work order). Identified by `(job, release)` composite key.

Key fields: `job` (int), `release` (str), `job_name`, `stage`, `stage_group`, `fab_order`, `fab_hrs`, `install_hrs`, `trello_card_id`, `trello_list_name`, `banana_color`, `start_install`, `comp_eta`, `viewer_url`, `last_updated_at`, `source_of_update`.

The `stage` field mirrors the Trello list name (e.g. "Released", "Cut start", "Fit Up Complete.", "Ready to Ship").

### 2. Submittals (Drafting Work Load)
**Model**: `Submittals` — Procore submittal records synced into the local DB. Identified by `submittal_id` (Procore's ID).

Key fields: `submittal_id`, `procore_project_id`, `project_number`, `title`, `status`, `ball_in_court`, `order_number`, `submittal_drafting_status`, `due_date`, `was_multiple_assignees`.

`order_number` encodes priority: `0.1–0.9` = urgency queue (FIFO stack, oldest/most urgent = lowest), `1, 2, 3...` = regular ordered queue, `NULL` = unordered.

### 3. Events (Audit Trail)
**Models**: `ReleaseEvents`, `SubmittalEvents` — immutable event log for every change.

Each event has: `action`, `payload` (JSON `{from, to}`), `payload_hash` (SHA-256 dedup), `source` ("Trello" | "Brain" | "Procore"), `external_user_id`, `is_system_echo`, `created_at`, `applied_at`.

### 4. Outbox
**Models**: `TrelloOutbox`, `ProcoreOutbox` — reliable async delivery queue for external API calls.

`TrelloOutbox` links to a `ReleaseEvent` and queues Trello API calls (`move_card`, `update_fab_order`, `update_notes`). `ProcoreOutbox` queues Procore submittal status updates.

### 5. Jobs (Geofenced Jobsites)
**Model**: `Jobs` — jobsite geofences. Stores GeoJSON polygon geometry and links to `Releases`/`Submittals` by `job_number` value (no FK).

**Model**: `ProjectManager` — PM color assignments for map display.

### 6. Users
**Model**: `User` — internal users with username/password auth. Has `procore_id` and `trello_id` for cross-referencing external events to internal users.

---

## Data Flow

### Trello → Brain (Webhook Inbound)
```
Trello card changes
  → POST /trello/webhook
  → parse_webhook_data() extracts event type, card_id, change_types
  → ThreadPoolExecutor.submit(run_sync)  ← returns 200 immediately
    → sync_from_trello(event_info)
      → echo detection: skip if Brain caused this via Outbox < 90s ago
      → timestamp check: skip if event older than DB record
      → fetch card data from Trello REST API
      → update Releases record (stage, list, name, description, due date)
      → TrelloListMapper.apply_trello_list_to_db() maps list → stage
      → create ReleaseEvents for each change (deduped by payload_hash)
      → after list moves: sort source/dest lists by Fab Order
      → db.session.commit()
```

### Brain → Trello (Outbox Outbound)
```
User action on frontend (stage change, fab order, notes)
  → POST /brain/job-log/...
  → JobEventService.create() → ReleaseEvents record
  → OutboxService.add() → TrelloOutbox record
  → db.session.commit()
  → background outbox_retry_worker (daemon thread, polling every 0.5–2s)
    → OutboxService.process_pending_items()
      → process_item(): execute Trello API call
      → on success: mark completed, JobEventService.close()
      → on failure: exponential backoff retry (max 5, delays 2^n seconds)
```

### Procore → Brain (Webhook Inbound)
```
Procore submittal updated
  → POST /procore/webhook
  → WebhookReceipt dedup check (SHA-256 hash, time-bucketed window)
  → echo detection: skip if PROCORE_CONNECTOR_USER_ID triggered it
  → fetch submittal data from Procore API
  → update Submittals record
  → create SubmittalEvents
  → trigger DWL urgency recalculation if ball_in_court changed
```

### Brain → Procore (Outbox Outbound)
```
DWL ordering/status change
  → POST /brain/drafting-work-load/...
  → SubmittalOrderingEngine calculates all affected order updates
  → bulk-update Submittals in DB
  → ProcoreOutbox.add() for status/field sync
  → Procore API call (sync or async)
```

### Frontend Data Fetch
```
React page load
  → axios GET /brain/job-log/releases   (Job Log)
  → axios GET /brain/drafting-work-load/ (DWL)
  → axios GET /brain/map/               (Jobsite Map)
  → Renders with hooks (useDataFetching, useFilters, useDragAndDrop, etc.)
```

---

## Integration Patterns

### Trello
- **Webhooks**: Trello POSTs to `/trello/webhook` on card create/update/move.
- **REST API**: Key+Token auth via `TRELLO_API_KEY` and `TRELLO_TOKEN` env vars.
- **Thread pool**: Webhook handler returns 200 immediately; sync runs in background thread pool (10 workers, `ThreadPoolExecutor`).
- **Custom fields**: Fab Order stored as a Trello custom field (`FAB_ORDER_FIELD_ID`).
- **Echo suppression**: Cross-references `TrelloOutbox` (completed, < 90s) by job+release+change content to skip echoes of Brain's own Trello calls.

### Procore
- **OAuth2 client credentials**: `get_access_token()` fetches and caches tokens in `ProcoreToken` DB model. No user-facing OAuth flow.
- **Webhooks**: Procore POSTs to `/procore/webhook`. Deduplicated via `WebhookReceipts` (SHA-256 of `resource_id:project_id:reason:time_bucket`).
- **Echo suppression**: Filters by `PROCORE_CONNECTOR_USER_ID` — webhooks triggered by this service account are ignored.
- **Sandbox vs Production**: Separate env var sets (`PROCORE_*` vs `PROD_PROCORE_*`), selected by environment.

### Auth
- Session-based with `flask.session`. `login_required` decorator on brain routes.
- `User.procore_id` and `User.trello_id` link internal users to external event actors.

### Database
- **Local**: SQLite at `instance/jobs.sqlite` (no engine options needed).
- **Sandbox/Prod**: PostgreSQL on Render, with connection pooling (`QueuePool`, size=5, overflow=10), SSL required, 30s statement timeout, pre-ping.
- **Migrations**: Manual Python scripts in `migrations/` (not Alembic; run ad hoc against target env).
- **Tests**: Always in-memory SQLite (`TESTING=1` env var forces this).

---

## Architectural Conventions

### Separation of Concerns (Brain domain)
Each domain under `app/brain/` follows a 3-layer pattern:
- **`engine.py`**: Pure Python business logic — no DB imports, works with plain dicts/dataclasses. Fully unit-testable.
- **`service.py`**: DB-touching service layer — calls engine for calculations, writes to DB.
- **`routes.py`**: Flask route handlers — parse request, call service, return JSON.

### Event Sourcing
All state changes create immutable `ReleaseEvents` or `SubmittalEvents` records before the mutation is committed. `payload_hash` (SHA-256 of serialized payload) prevents duplicate events.

Events have lifecycle: created → `applied_at` set when outbox item completes or change confirmed. `is_system_echo=True` marks events caused by Brain's own API calls (hidden in UI by default).

### Outbox Pattern
External API calls are never made inline in request handlers. Instead:
1. A `ReleaseEvent` or `SubmittalEvent` is created.
2. An outbox record (`TrelloOutbox` / `ProcoreOutbox`) is created, linked to the event.
3. A daemon background thread (`outbox_retry_worker`) polls for pending outbox items (every 0.5–2s) and executes the external API call.
4. On failure: exponential backoff (`2^retry_count` seconds, max 5 retries).

### Naming Conventions
- Python: `snake_case` for variables, functions, methods; `PascalCase` for classes.
- Models: plural (`Releases`, `Submittals`, `Users`) matching table names.
- Blueprints: `{name}_bp` suffix.
- Frontend: React components in `PascalCase`; hooks prefixed `use`; service files named `{domain}Api.js`.
- DB table names: `snake_case` (e.g., `release_events`, `trello_outbox`, `webhook_receipts`).

### Frontend Architecture
- Single SPA served from Flask's `/` catch-all (React Router handles client-side routing).
- Auth gate in `App.jsx`: unauthenticated users see `LoginPrompt` on all routes; authenticated users see full app.
- Data fetching via custom hooks (`useDataFetching`, `useJobsDataFetching`) wrapping Axios calls to `/brain/*` endpoints.
- Domain service modules in `frontend/src/services/` (one per backend domain).
- Default route after login: `/job-log`.

### Error Handling
- All Flask exceptions return JSON via global `@app.errorhandler(Exception)`.
- Sync errors in background threads are caught, logged, and reported via `thread_tracker` stats (visible at `GET /trello/thread-stats`).
- Outbox retries surface errors in `error_message` field and log via structlog.
- Frontend: Axios errors handled per-hook; `AlertMessage` component for user-visible errors.

### Logging
- `structlog` with key-value pairs: `logger.info("message", key=value, ...)`.
- `SyncContext` binds `operation_id` to all log calls within a sync operation.
- Rotating file handler writes to `logs/app.log` (1 backup: `app.log.1`).
- `SystemLogs` DB model captures critical errors for in-app display.

---

*Generated by `/generate-project-context` skill. Last updated: 2026-03-09.*
