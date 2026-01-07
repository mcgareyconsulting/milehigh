# Migration Summary

## Changes Confirmed

### 1. New Column: `viewer_url` on `jobs` (app/models.py)
- **Column**: `viewer_url VARCHAR(512)`
- **Purpose**: Persists the Procore drafting document viewer link whenever `/procore/add-link` runs.
- **API Impact**: `/procore/add-link` now returns the `card_id` and `viewer_url` in the success payload.
- **Migration**: Run `python migrations/add_viewer_url_to_jobs.py` to alter the table (idempotent).

### 2. Deprecation and Removal: JobChangeLog and State Tracker
The Job Change Log feature and state tracker have been deprecated and removed. We keep `job_events` as the single source of truth for activity.

- Removed:
  - Model `JobChangeLog` from `app/models.py`
  - Module `app/sync/state_tracker.py`
  - Integration calls from `app/sync/sync.py`
  - Migration script `migrations/add_job_change_log_table.py`

If your database contains the `job_change_logs` table, drop it using the migration below.

## Migration Instructions

### Drop deprecated `job_change_logs` table (if present)

```bash
python migrations/drop_job_change_log_table.py
python migrations/add_viewer_url_to_jobs.py  # if not already applied
```

## Verification

```python
from app import create_app
from app.models import Job, db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    # Check table dropped
    inspector = inspect(db.engine)
    assert 'job_change_logs' not in inspector.get_table_names()

    # Check viewer_url column is accessible
    job = Job.query.first()
    if job:
        print(f"viewer_url column value: {job.viewer_url}")
``` 
