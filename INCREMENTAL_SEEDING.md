# Incremental Seeding Documentation

## Overview

The incremental seeding functionality allows you to update your database with missing jobs from your Trello/Excel cross-check without rebuilding the entire database. This is perfect for running outside of the main database build process while still updating your job records.

## How It Works

1. **Fetches unique Trello cards** from the 5 target lists:
   - "Fit Up Complete."
   - "Paint complete"
   - "Shipping completed"
   - "Store at MHMW for shipping"
   - "Shipping planning"

2. **Cross-validates with Excel data** - Only processes jobs that have BOTH:
   - A valid Trello card in one of the 5 target lists
   - Matching Excel data with job/release information

3. **Filters out incomplete matches**:
   - Trello cards without Excel data (logged but skipped)
   - Excel rows without Trello cards (logged but skipped)

4. **Checks existing database records** by querying for job+release combinations

5. **Only creates new Job records** for jobs that have both Trello cards AND Excel data but are missing from the database

6. **Tracks the operation** with detailed logging and cross-check statistics

## Usage Options

### 1. Command Line Script
```bash
# Run the standalone script
python run_incremental_seed.py
```

### 2. Web API Endpoints

#### Run Incremental Seeding
```bash
# Default batch size (50)
curl -X POST http://localhost:5000/seed/incremental

# Custom batch size
curl -X POST "http://localhost:5000/seed/incremental?batch_size=25"
```

#### Check Seeding Status
```bash
curl http://localhost:5000/seed/status
```

#### Get Cross-Check Analysis
```bash
# Get detailed Trello/Excel cross-check summary
curl http://localhost:5000/seed/cross-check
```

### 3. Python Function Call
```python
from app.seed import incremental_seed_missing_jobs, run_incremental_seed_example, get_trello_excel_cross_check_summary

# Direct function call
result = incremental_seed_missing_jobs(batch_size=50)

# With example wrapper (includes nice output)
result = run_incremental_seed_example()

# Get cross-check analysis without making changes
summary = get_trello_excel_cross_check_summary()
```

## Return Values

The incremental seeding function returns a dictionary with:

```python
{
    "operation_id": "abc12345",           # Unique operation ID for tracking
    "total_items": 150,                   # Total items from Trello/Excel cross-check
    "existing_jobs": 120,                 # Jobs already in database
    "new_jobs_created": 30,               # New jobs added to database
    "status": "completed"                 # "completed" or "up_to_date"
}
```

## Features

- ✅ **Safe batched processing** - Processes records in configurable batches
- ✅ **Database integrity** - Uses existing unique constraints (job+release)
- ✅ **Operation tracking** - Full sync operation logging and monitoring
- ✅ **Memory efficient** - Garbage collection and session cleanup
- ✅ **Error handling** - Graceful error handling with detailed logging
- ✅ **Trello integration** - Preserves Trello card associations when available
- ✅ **Excel data mapping** - Full Excel field mapping with safe type conversion

## Integration with Existing System

The incremental seeding integrates seamlessly with your existing infrastructure:

- Uses the same `Job` model and database schema
- Leverages existing `SyncOperation` and `SyncLog` tracking
- Reuses the proven `combine_trello_excel_data()` flow
- Maintains the same data validation and truncation logic
- Compatible with existing sync lock management

## Performance

- **Batch processing**: Configurable batch sizes (1-200 records)
- **Memory management**: Automatic cleanup between batches
- **Database efficiency**: Single query per job to check existence
- **Logging**: Structured logging for monitoring and debugging

## Monitoring

Track operations via:
- Web endpoint: `/seed/status` - Shows database stats and recent operations
- Sync operations table: Query `SyncOperation` with `operation_type='incremental_seed'`
- Application logs: Detailed operation logging with operation IDs
