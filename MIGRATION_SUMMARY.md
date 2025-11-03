# Migration Summary: JobChangeLog Model

## Changes Confirmed

### 1. New Model: `JobChangeLog` (app/models.py)
Added a new model to track state changes and field updates for jobs over time:

- **Table**: `job_change_logs`
- **Purpose**: Audit trail for job state transitions (e.g., "Fitup Complete" → "Welding Complete")
- **Key Fields**:
  - `job`, `release`: Job identifiers
  - `change_type`: Type of change ("state_change", "field_change")
  - `from_value`, `to_value`: Previous and new state/value
  - `field_name`: Field that changed (e.g., "fitup_comp", "state")
  - `changed_at`: Timestamp of change
  - `operation_id`: Links to SyncOperation for traceability
  - `source`: Origin of change ("Excel", "Trello", "Manual")
  - `triggered_by`: Description of what caused the change
- **Indexes**: Optimized for queries on job/release, timestamp, operation_id, and change_type

### 2. New Module: `state_tracker.py` (app/sync/state_tracker.py)
New module that handles state change detection and tracking:

- **JobStateConfig**: Defines state mappings and progression order
  - States: Created → Fitup Complete → Welding Complete → Paint Complete → Shipped
- **track_job_state_change()**: Logs state changes to JobChangeLog
- **detect_and_track_state_changes()**: Detects field changes and tracks state transitions

### 3. Integration: `sync.py` (app/sync/sync.py)
Integrated state tracking into sync operations:

- **sync_from_trello()**: 
  - Captures old values before updates (lines 159-165)
  - Calls `detect_and_track_state_changes()` after commit (lines 252-258)
  
- **sync_from_onedrive()**: 
  - Captures old values before updates (lines 423-429)
  - Stores old_values in updated_records tuple (line 483)
  - Calls `detect_and_track_state_changes()` after commit (lines 491-498)

### 4. Bug Fix
Fixed a bug in `sync_from_onedrive()` where `updated_records` was storing tuples of `(rec, formula_status)` but the code was trying to unpack 3 values including `old_values`. Now correctly stores `(rec, formula_status, old_values)`.

## Migration Instructions

### Option 1: Run Migration Script (Recommended)
```bash
python migrations/add_job_change_log_table.py
```

The script will:
- Check if the table already exists
- Create the table if needed
- Verify the table structure
- Show a summary of columns and indexes

### Option 2: Automatic Creation
Since your app uses `db.create_all()`, the table will be automatically created on the next app startup if it doesn't exist. However, running the migration script explicitly is recommended for better control and verification.

### Option 3: Manual SQL (For Production)
If you prefer to run SQL directly on your production database:

```sql
CREATE TABLE job_change_logs (
    id INTEGER PRIMARY KEY,
    job INTEGER NOT NULL,
    release VARCHAR(50),
    change_type VARCHAR(50) NOT NULL,
    from_value VARCHAR(200),
    to_value VARCHAR(200) NOT NULL,
    field_name VARCHAR(100),
    changed_at DATETIME NOT NULL,
    operation_id VARCHAR(36),
    source VARCHAR(50) NOT NULL,
    triggered_by VARCHAR(100)
);

-- Create indexes
CREATE INDEX idx_job_release ON job_change_logs(job, release);
CREATE INDEX idx_changed_at ON job_change_logs(changed_at);
CREATE INDEX idx_operation_id ON job_change_logs(operation_id);
CREATE INDEX idx_change_type ON job_change_logs(change_type);
```

## Verification

After running the migration, verify it worked:

```python
from app import create_app
from app.models import JobChangeLog, db

app = create_app()
with app.app_context():
    # Check table exists
    inspector = inspect(db.engine)
    assert 'job_change_logs' in inspector.get_table_names()
    
    # Check can query (should return 0 initially)
    count = JobChangeLog.query.count()
    print(f"JobChangeLog records: {count}")
```

## Next Steps

1. Run the migration script
2. Test a sync operation to verify state changes are being tracked
3. Query `JobChangeLog` to see state transitions being logged

## Notes

- The migration is **idempotent** - safe to run multiple times
- Existing data is **not affected** - this only adds a new table
- State tracking will begin immediately after migration for all new sync operations

