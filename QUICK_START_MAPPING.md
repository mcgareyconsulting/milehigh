# Quick Start: Database Mapping

## TL;DR

Map `fab_order` from production to sandbox in 2 commands:

```bash
# 1. Preview changes (dry run)
python app/scripts/map_production_to_sandbox.py --dry-run

# 2. Apply changes (when ready)
python app/scripts/map_production_to_sandbox.py
```

## Prerequisites

1. ✅ Set environment variables:
   ```bash
   export PRODUCTION_DATABASE_URL="postgresql://..."
   export SANDBOX_DATABASE_URL="postgresql://..."
   ```

2. ✅ Verify connections work:
   ```bash
   python -c "from sqlalchemy import create_engine; create_engine('$PRODUCTION_DATABASE_URL').connect()"
   ```

## One-Minute Tutorial

### Step 1: Dry Run (Safe Preview)
```bash
python app/scripts/map_production_to_sandbox.py --dry-run
```

**Output:** Shows what would be updated without making changes.

### Step 2: Review Output
Look for:
- ✅ **Matched** - Jobs found in both databases
- ⚠️ **Not Found in Sandbox** - Production jobs not in sandbox
- 📋 **Updates Needed** - Jobs needing fab_order updates

### Step 3: Apply (When Ready)
```bash
python app/scripts/map_production_to_sandbox.py
```

**Output:** Confirms all updates were applied successfully.

## Programmatic Usage

```python
from app.services.database_mapping import map_production_fab_order_to_sandbox
from sqlalchemy import create_engine
import os

# Create engines
prod = create_engine(os.environ.get("PRODUCTION_DATABASE_URL"))
sandbox = create_engine(os.environ.get("SANDBOX_DATABASE_URL"))

# Map and apply
stats = map_production_fab_order_to_sandbox(prod, sandbox, dry_run=False)

# Check results
print(f"Matched: {stats.matched}")
print(f"Updated: {stats.updated}")
print(f"Errors: {stats.errors}")
```

## Common Scenarios

### Scenario 1: First Time Setup
```bash
# Step 1: Check what would sync
python app/scripts/map_production_to_sandbox.py --dry-run

# Step 2: If happy, apply
python app/scripts/map_production_to_sandbox.py
```

### Scenario 2: Sync Specific Field
```python
from app.services.database_mapping import (
    DatabaseMappingService,
    FieldMapping
)

# Fetch data
prod_jobs = DatabaseMappingService.fetch_jobs(prod, 
    ["job", "release", "paint_color"])
sandbox_jobs = DatabaseMappingService.fetch_jobs(sandbox,
    ["job", "release", "paint_color"])

# Map
results, stats = DatabaseMappingService.map_jobs_by_key(
    prod_jobs, sandbox_jobs,
    field_mappings=[FieldMapping("paint_color", "paint_color")]
)

# Apply
DatabaseMappingService.apply_field_updates(sandbox, results)
```

### Scenario 3: Sync Multiple Fields
```python
from app.services.database_mapping import (
    DatabaseMappingService,
    FieldMapping
)

field_mappings = [
    FieldMapping("fab_order", "fab_order"),
    FieldMapping("paint_color", "paint_color"),
    FieldMapping("stage", "stage"),
]

results, stats = DatabaseMappingService.map_jobs_by_key(
    prod_df, sandbox_df,
    field_mappings=field_mappings
)
```

## Troubleshooting

### ❌ "Database connection failed"
```bash
# Check env var is set
echo $PRODUCTION_DATABASE_URL
echo $SANDBOX_DATABASE_URL

# Test connection manually
psql $PRODUCTION_DATABASE_URL -c "SELECT 1"
```

### ❌ "Jobs not found in sandbox"
This is normal if:
- Sandbox is fresh/empty
- Production has newer jobs
- Different releases

### ❌ "Permission denied"
Ensure database user has UPDATE permission:
```sql
GRANT UPDATE ON jobs TO your_user;
```

### ❌ "No fab_order updates needed"
All jobs are already in sync! ✅

## Output Format

### Dry Run Example
```
================================================================================
MAP PRODUCTION → SANDBOX
================================================================================

✓ Production database connection successful
✓ Sandbox database connection successful
✓ Fetched 1250 jobs from Production database
✓ Fetched 890 jobs from Sandbox database

MAPPING SUMMARY
Database Stats:
  Production Jobs: 1250
  Sandbox Jobs: 890

Mapping Results:
  Matched: 850
  Not Found in Sandbox: 400
  fab_order Differences: 42

fab_order Updates Needed:
  - 10001-A: 500.0 → 510.0
  - 10002-B: 750.0 → 800.0
  ... and 40 more

✓ Dry run completed successfully
```

### Applied Example
```
Applying Updates...
Total updates to apply: 42
  ✓ Job 10001-A: fab_order 500.0 → 510.0
  ✓ Job 10002-B: fab_order 750.0 → 800.0
  ... (42 total)
✓ Successfully updated 42 fab_order values
```

## API Reference (Quick)

### Service: `DatabaseMappingService`

**Methods:**
- `fetch_jobs(engine, columns, where_clause)` - Get jobs from DB
- `map_jobs_by_key(source_df, target_df, field_mappings)` - Match jobs
- `apply_field_updates(engine, results, dry_run)` - Apply changes
- `get_job_by_key(engine, job_id, release)` - Get one job
- `update_job_fields(engine, job_id, release, fields)` - Update one job

**Convenience:**
- `map_production_fab_order_to_sandbox(prod_eng, sandbox_eng)` - One-call sync

## Next Steps

1. Read full docs: `docs/DATABASE_MAPPING.md`
2. Run tests: `python app/scripts/test_database_mapping.py`
3. Review implementation: `app/services/database_mapping.py`
4. Integrate into your app: See examples in `docs/DATABASE_MAPPING.md`

## Get Help

1. Check full documentation: `docs/DATABASE_MAPPING.md`
2. Review test examples: `app/scripts/test_database_mapping.py`
3. Check inline code comments
4. Review logs in `logs/app.log`

---

**Safety:** Always run with `--dry-run` first to preview changes!

