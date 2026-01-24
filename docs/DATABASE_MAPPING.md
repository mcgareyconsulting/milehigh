# Database Mapping Guide

## Overview

The database mapping functionality allows you to synchronize job data between production and sandbox databases using the `(job, release)` tuple as a primary matching key.

This is useful for:
- Syncing `fab_order` values from production to sandbox
- Mapping any other fields between databases
- Migrating specific data fields without full data migration
- Maintaining consistency between environments

## Architecture

### Components

1. **DatabaseMappingService** (`app/services/database_mapping.py`)
   - Core service for mapping jobs between databases
   - Provides reusable functions for field mapping and updates
   - Can be imported and used programmatically

2. **Map Production to Sandbox Script** (`app/scripts/map_production_to_sandbox.py`)
   - Standalone command-line tool
   - Maps `fab_order` from production to sandbox
   - Provides detailed reporting and dry-run mode

## Usage

### Command Line (Simple)

Map `fab_order` from production to sandbox with a dry run:

```bash
python app/scripts/map_production_to_sandbox.py --dry-run
```

Apply the mapping (without dry-run):

```bash
python app/scripts/map_production_to_sandbox.py
```

Or using the module syntax:

```bash
python -m app.scripts.map_production_to_sandbox --dry-run
```

### Programmatic Usage

#### Basic Fab Order Mapping

```python
from sqlalchemy import create_engine
from app.services.database_mapping import map_production_fab_order_to_sandbox

# Create engines
production_engine = create_engine(os.environ.get("PRODUCTION_DATABASE_URL"))
sandbox_engine = create_engine(os.environ.get("SANDBOX_DATABASE_URL"))

# Run mapping
stats = map_production_fab_order_to_sandbox(
    production_engine,
    sandbox_engine,
    dry_run=False
)

print(f"Matched: {stats.matched}")
print(f"Updated: {stats.updated}")
print(f"Not Found: {stats.not_found}")
```

#### Custom Field Mapping

```python
from app.services.database_mapping import (
    DatabaseMappingService,
    FieldMapping
)

# Fetch data
production_df = DatabaseMappingService.fetch_jobs(
    production_engine,
    ["job", "release", "fab_order", "paint_color", "stage"]
)
sandbox_df = DatabaseMappingService.fetch_jobs(
    sandbox_engine,
    ["job", "release", "fab_order", "paint_color", "stage"]
)

# Define multiple field mappings
field_mappings = [
    FieldMapping("fab_order", "fab_order"),
    FieldMapping("paint_color", "paint_color"),
    FieldMapping("stage", "stage"),
]

# Map jobs
results, stats = DatabaseMappingService.map_jobs_by_key(
    production_df,
    sandbox_df,
    field_mappings=field_mappings
)

# Apply updates
updated_count = DatabaseMappingService.apply_field_updates(
    sandbox_engine,
    results,
    dry_run=False
)
```

#### With Custom Logging

```python
def log_mapper(level, message):
    """Custom logging callback."""
    if level == "error":
        print(f"❌ {message}")
    elif level == "warning":
        print(f"⚠️  {message}")
    elif level == "info":
        print(f"ℹ️  {message}")
    else:
        print(f"   {message}")

updated_count = DatabaseMappingService.apply_field_updates(
    sandbox_engine,
    results,
    dry_run=False,
    log_callback=log_mapper
)
```

#### Single Job Update

```python
from app.services.database_mapping import DatabaseMappingService

# Get a single job
job_data = DatabaseMappingService.get_job_by_key(
    sandbox_engine,
    job_id=12345,
    release="A",
    columns=["id", "job", "release", "fab_order"]
)

# Update specific fields
success = DatabaseMappingService.update_job_fields(
    sandbox_engine,
    job_id=12345,
    release="A",
    fields={"fab_order": 98765.0},
    dry_run=False
)
```

## Data Model

### FieldMapping

Configuration for mapping a single field:

```python
@dataclass
class FieldMapping:
    source_field: str              # Column name in source
    target_field: str              # Column name in target
    transform: Optional[callable]  # Optional transformation function
```

### JobMappingResult

Result of mapping a single job:

```python
@dataclass
class JobMappingResult:
    job_id: int                              # Job number
    release: str                             # Release number
    matched: bool                            # Whether job was found in target
    fields_updated: Dict[str, Tuple]         # {field: (old_val, new_val)}
    error: Optional[str]                     # Error message if not matched
```

### MappingStatistics

Statistics about the overall operation:

```python
@dataclass
class MappingStatistics:
    total_source: int                  # Total jobs in source
    total_target: int                  # Total jobs in target
    matched: int                       # Successfully matched jobs
    not_found: int                     # Jobs not found in target
    updated: int                       # Jobs with field updates
    errors: int                        # Jobs with errors
    field_updates: Dict[str, int]      # Count per field: {field: count}
```

## Examples

### Example 1: Update Fab Order Only

```python
from app.services.database_mapping import (
    DatabaseMappingService,
    FieldMapping
)

# Fetch only fab_order
prod_jobs = DatabaseMappingService.fetch_jobs(
    prod_engine,
    ["job", "release", "fab_order"]
)
sandbox_jobs = DatabaseMappingService.fetch_jobs(
    sandbox_engine,
    ["job", "release", "fab_order"]
)

# Map
results, stats = DatabaseMappingService.map_jobs_by_key(
    prod_jobs,
    sandbox_jobs,
    field_mappings=[FieldMapping("fab_order", "fab_order")]
)

print(f"Found {stats.matched} matching jobs")
print(f"Need to update {len([r for r in results if r.fields_updated])} jobs")
```

### Example 2: Transform During Mapping

```python
# Map with transformation (e.g., ensure numeric type)
field_mappings = [
    FieldMapping(
        "fab_order",
        "fab_order",
        transform=lambda x: float(x) if x is not None else None
    )
]
```

### Example 3: Full Integration in Route Handler

```python
from flask import Blueprint, jsonify
from sqlalchemy import create_engine
from app.services.database_mapping import (
    map_production_fab_order_to_sandbox
)
import os

sync_bp = Blueprint("sync", __name__)

@sync_bp.route("/api/sync/fab-order", methods=["POST"])
def sync_fab_order():
    """Sync fab_order from production to sandbox."""
    try:
        prod_engine = create_engine(os.environ.get("PRODUCTION_DATABASE_URL"))
        sandbox_engine = create_engine(os.environ.get("SANDBOX_DATABASE_URL"))
        
        def log_callback(level, message):
            print(f"[{level.upper()}] {message}")
        
        stats = map_production_fab_order_to_sandbox(
            prod_engine,
            sandbox_engine,
            dry_run=False,
            log_callback=log_callback
        )
        
        return jsonify({
            "success": True,
            "matched": stats.matched,
            "updated": stats.updated,
            "not_found": stats.not_found,
            "errors": stats.errors
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

## Environment Variables Required

- `PRODUCTION_DATABASE_URL` - Connection string for production database
- `SANDBOX_DATABASE_URL` - Connection string for sandbox database

These should be set in your `.env` file or environment:

```env
PRODUCTION_DATABASE_URL=postgresql://user:pass@prod-host/db
SANDBOX_DATABASE_URL=postgresql://user:pass@sandbox-host/db
```

## Output Examples

### Dry Run Output

```
================================================================================
MAP PRODUCTION → SANDBOX
================================================================================

⚠ DRY RUN MODE - No changes will be made

Source (Production): prod-host/db
Target (Sandbox): sandbox-host/db

Testing database connections...
✓ Production database connection successful
✓ Sandbox database connection successful

Fetching jobs from databases...
✓ Fetched 1250 jobs from Production database
✓ Fetched 890 jobs from Sandbox database

Mapping jobs...

================================================================================
MAPPING SUMMARY
================================================================================

Database Stats:
  Production Jobs: 1250
  Sandbox Jobs: 890

Mapping Results:
  Matched: 850
  Not Found in Sandbox: 400
  fab_order Differences: 42

Jobs Not Found in Sandbox (10):
  - 12345-A
  - 12346-B
  ... and 390 more

fab_order Updates Needed (42):
  - 10001-A: 500.0 → 510.0
  - 10002-B: 750.0 → 800.0
  ... and 40 more

================================================================================
Applying Updates...
Total updates to apply: 42
  [DRY RUN] Job 10001-A: fab_order 500.0 → 510.0
  [DRY RUN] Job 10002-B: fab_order 750.0 → 800.0
  ... (42 total)

================================================================================
✓ Dry run completed successfully
================================================================================
```

### Actual Run Output

```
================================================================================
MAP PRODUCTION → SANDBOX
================================================================================

Source (Production): prod-host/db
Target (Sandbox): sandbox-host/db

Testing database connections...
✓ Production database connection successful
✓ Sandbox database connection successful

Fetching jobs from databases...
✓ Fetched 1250 jobs from Production database
✓ Fetched 890 jobs from Sandbox database

Mapping jobs...

================================================================================
MAPPING SUMMARY
================================================================================

Database Stats:
  Production Jobs: 1250
  Sandbox Jobs: 890

Mapping Results:
  Matched: 850
  Not Found in Sandbox: 400
  fab_order Differences: 42

================================================================================
Applying Updates...
Total updates to apply: 42
  ✓ Job 10001-A: fab_order 500.0 → 510.0
  ✓ Job 10002-B: fab_order 750.0 → 800.0
  ... (42 total)
✓ Successfully updated 42 fab_order values
================================================================================
```

## Error Handling

The service handles various error scenarios:

1. **Missing Database URLs** - Clear error messages with required env vars
2. **Connection Failures** - Attempts to connect and reports connection errors
3. **Jobs Not Found** - Logged and counted in statistics without failing
4. **Update Failures** - Reported per job without stopping other updates
5. **Schema Differences** - Fetches only specified columns to avoid issues

## Best Practices

1. **Always Run Dry Run First**
   ```bash
   python app/scripts/map_production_to_sandbox.py --dry-run
   ```

2. **Review the Output** - Especially the "Not Found in Sandbox" section

3. **Use Version Control** - Keep track of when mappings were run

4. **Test in Sandbox First** - Verify the mapping before production

5. **Monitor Logs** - Check for any errors or warnings during execution

6. **Backup Before Running** - Although non-destructive, always have a backup

## Troubleshooting

### Connection Refused

```
✗ Production database connection successful
```

**Solution:** Verify database URLs and network connectivity

```bash
# Check environment variables
echo $PRODUCTION_DATABASE_URL
echo $SANDBOX_DATABASE_URL
```

### Jobs Not Found in Sandbox

If many jobs are "not found", the datasets may not be in sync. This is expected if:
- Sandbox was recently created
- Production has newer jobs
- Releases haven't been created in sandbox yet

### Permission Denied on Updates

```
Error applying updates: permission denied for relation jobs
```

**Solution:** Ensure the database user has UPDATE permissions on the jobs table

## Future Enhancements

Potential improvements to consider:

1. **Bidirectional Mapping** - Map from sandbox to production
2. **Custom Matchers** - Use fields other than (job, release) for matching
3. **Field Transformations** - Built-in common transformations
4. **Conflict Resolution** - Strategies for conflicting values
5. **Scheduling** - Automated periodic syncing
6. **Audit Trail** - Log all changes for compliance

## Support

For issues or questions:

1. Check the logs in `logs/app.log`
2. Review the mapping statistics output
3. Consult this documentation
4. Check the source code inline documentation

