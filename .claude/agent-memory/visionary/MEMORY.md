# Visionary Agent Memory

## Project: Mile High Metal Works — Trello/SharePoint Brain

### Stack
- Backend: Flask 3.1 / Python 3.9, SQLAlchemy 2.0, SQLite (local) / PostgreSQL (prod)
- Frontend: React 19, Vite 7, Tailwind CSS 3, Axios
- Auth: Session-based (login_required decorator)

### Key Paths
- Backend domain: `app/brain/job_log/` — routes, scheduling, features
- Scheduling pure functions: `app/brain/job_log/scheduling/calculator.py` + `config.py`
- Frontend page: `frontend/src/pages/JobLog.jsx`
- Frontend hooks: `frontend/src/hooks/useJobsFilters.js`, `useJobsDataFetching.js`
- Frontend service: `frontend/src/services/jobsApi.js` (not `service/`)

### Brain Domain Architecture Pattern
Every domain under `app/brain/` follows:
1. `engine.py` — pure Python logic, no DB, plain dicts (unit-testable)
2. `service.py` — DB-touching layer calling engine
3. `routes.py` — Flask handlers calling service

New scheduling utilities go in `app/brain/job_log/scheduling/` as pure-function modules.

### Data Layer Notes
- `Releases` model fields: `fab_hrs`, `install_hrs`, `stage`, `stage_group`, `job_comp` (String(8)), `fab_order`
- API serializes as: `"Fab Hrs"`, `"Install HRS"`, `"Stage"`, `"Job Comp"` (string, may be null)
- `job_comp` stored as string (e.g. "75", "100") — must parse to float in JS
- Stage strings in DB match Trello list names: "Cut start", "Fit Up Complete.", "Welded QC", etc.

### Scheduling Stage Config
`SchedulingConfig.STAGE_REMAINING_FAB_PERCENTAGE` in `config.py` is the authoritative
stage → remaining-fab-% map. Reuse it rather than duplicating stage maps.

### Frontend Filter Architecture
- `useJobsFilters` owns `displayJobs` (filtered + sorted)
- All computed values derived from `displayJobs` belong in `useJobsFilters` as `useMemo`
- Stage strings in JS: defined in `stageOptions` array and `stageToGroup` map inside hook

### UI Patterns
- Filter header bottom row uses `justify-between` flex: left = Reset/search/count, right = Last Updated
- Stat chips style: `px-2 py-0.5 bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 rounded text-xs font-semibold`
- Dark mode classes always paired with light classes via `dark:` prefix

### Migrations
Manual Python scripts in `migrations/` — not Alembic. Run ad hoc.
