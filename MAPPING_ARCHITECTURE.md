# Database Mapping Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER                           │
├─────────────────────────────────────────────────────────────────┤
│  • HTTP Routes (/api/sync/fab-order)                           │
│  • Background Tasks (Celery, APScheduler)                      │
│  • Admin Dashboard                                             │
│  • CLI Tools                                                    │
└────────────────────────┬────────────────────────────────────────┘
                         │ imports & uses
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SERVICE LAYER (Core)                          │
├─────────────────────────────────────────────────────────────────┤
│  DatabaseMappingService                                        │
│  ├─ fetch_jobs()                                              │
│  ├─ create_job_lookup()                                       │
│  ├─ map_jobs_by_key()        ◄──── Main Mapping Logic        │
│  ├─ apply_field_updates()                                     │
│  ├─ get_job_by_key()                                          │
│  └─ update_job_fields()                                       │
│                                                                 │
│  Convenience Functions                                         │
│  └─ map_production_fab_order_to_sandbox()                    │
│                                                                 │
│  Data Classes                                                  │
│  ├─ FieldMapping                                              │
│  ├─ JobMappingResult                                          │
│  └─ MappingStatistics                                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                    ┌────┴────┐
                    ▼         ▼
        ┌───────────────────────────────────┐
        │   Production DB  │  Sandbox DB    │
        │   (PostgreSQL)   │  (PostgreSQL)  │
        └───────────────────────────────────┘
```

## Data Flow

### Mapping Process

```
1. FETCH PHASE
   Production DB ──────────► fetch_jobs(prod_engine) ──────► Production DataFrame
   Sandbox DB ──────────► fetch_jobs(sandbox_engine) ──────► Sandbox DataFrame

2. MAPPING PHASE
   Production DF
   + Sandbox DF
   + FieldMappings ──────────► map_jobs_by_key() ──────► JobMappingResult[]
                                                          + MappingStatistics

3. UPDATE PHASE
   JobMappingResult[]
   + Sandbox Engine ──────────► apply_field_updates() ──────► Updated Jobs
                                      (transactional)         Database

4. REPORT PHASE
   MappingStatistics ──────────► User Output ──────► Console/Logs
```

## Component Architecture

### 1. DatabaseMappingService

**Responsibilities:**
- Database operations (SELECT, UPDATE)
- Job matching by (job, release)
- Field comparison and update logic
- Transaction management
- Error handling

**Key Methods:**

```python
fetch_jobs()
├── Query: SELECT columns FROM jobs WHERE clause
├── Input: engine, columns[], where_clause
└── Output: pd.DataFrame

create_job_lookup()
├── Logic: Index DataFrame by (job, release)
├── Input: DataFrame, key_columns
└── Output: Dict[Tuple, Dict]

map_jobs_by_key()
├── Logic: Match production → sandbox by key
├── Logic: Compare fields from FieldMappings
├── Input: prod_df, sandbox_df, field_mappings[]
└── Output: JobMappingResult[], MappingStatistics

apply_field_updates()
├── Logic: Build UPDATE statements
├── Logic: Execute in transaction
├── Input: engine, results[], dry_run
└── Output: int (update count)
```

### 2. Data Classes

```python
FieldMapping
├── source_field: str
├── target_field: str
└── transform: Optional[callable]

JobMappingResult
├── job_id: int
├── release: str
├── matched: bool
├── fields_updated: Dict[str, Tuple[old, new]]
└── error: Optional[str]

MappingStatistics
├── total_source: int
├── total_target: int
├── matched: int
├── not_found: int
├── updated: int
├── errors: int
└── field_updates: Dict[str, int]
```

### 3. CLI Tool (map_production_to_sandbox.py)

**Flow:**

```
1. Parse arguments (--dry-run)
2. Get database URLs from environment
3. Create engines
4. Test connections
5. Fetch jobs from both databases
6. Map jobs
7. Print summary
8. Apply updates (if not dry-run)
9. Print results
10. Dispose engines
```

**Output Stages:**

```
Connection Testing
    ↓
Data Fetching
    ↓
Mapping
    ↓
Summary Report
    ├─ Matched count
    ├─ Not found list
    ├─ Updates needed list
    └─ Statistics
    ↓
Apply Updates (if not dry-run)
    ├─ [DRY RUN] preview OR actual updates
    └─ Success count
```

## Matching Algorithm

### Primary Key: (job, release)

```python
def match_jobs(production_df, sandbox_df):
    """
    Match jobs by (job, release) tuple.
    
    Complexity: O(n + m)
    - n = production jobs
    - m = sandbox jobs (for lookup dict)
    """
    
    # Create lookup index - O(m)
    sandbox_lookup = {}
    for _, row in sandbox_df.iterrows():
        key = (row['job'], row['release'])
        sandbox_lookup[key] = row_data
    
    # Match each production job - O(n)
    results = []
    for _, prod_row in production_df.iterrows():
        key = (prod_row['job'], prod_row['release'])
        
        if key in sandbox_lookup:  # O(1) dict lookup
            # MATCHED - Compare fields
            results.append(JobMappingResult(matched=True, ...))
        else:
            # NOT FOUND
            results.append(JobMappingResult(matched=False, ...))
    
    return results
```

## Field Mapping Process

### Single Field Mapping

```
┌─ FieldMapping(source="fab_order", target="fab_order")
│
├─ For each (job, release):
│  1. Get source_value from production
│  2. Get target_value from sandbox
│  3. If transform defined:
│     └─ source_value = transform(source_value)
│  4. Compare values
│  5. If different:
│     └─ Record update: (job, release, field, old, new)
│
└─ Result: List[JobMappingResult] with fields_updated dict
```

### Multiple Field Mapping

```
FieldMappings[]
└─ For each FieldMapping:
   └─ Compare and track differences
   
Result: JobMappingResult with all field updates
Example: {
    'fab_order': (500.0, 510.0),
    'paint_color': ('red', 'blue'),
    'stage': ('pending', 'in_progress')
}
```

## Update Mechanism

### Transaction-Safe Updates

```python
def apply_field_updates(engine, results, dry_run):
    """
    Apply updates transactionally.
    
    All-or-nothing semantics:
    - If any job update fails, entire transaction rolls back
    - If all succeed, all changes are committed
    """
    
    with engine.begin() as conn:  # ◄── Transaction starts
        for result in results:
            if result.matched and result.fields_updated:
                # Build dynamic UPDATE statement
                SET_clause = ", ".join(f"{field} = :{field}")
                params = {
                    "job": result.job_id,
                    "release": result.release,
                    **result.fields_updated
                }
                
                # Execute: UPDATE jobs SET ... WHERE job AND release
                conn.execute(sql, params)  # ◄── Transactional
    
    # ◄── Transaction commits here or rolls back on error
```

## Error Handling Flow

```
┌─ Connection Error
│  └─ Report and exit
├─ Missing Columns
│  └─ Fetch only available columns
├─ Unmatched Jobs
│  ├─ Log as "not found"
│  └─ Continue processing
├─ Update Failures
│  ├─ Log error for job
│  ├─ Transaction rolls back (all-or-nothing)
│  └─ Continue with next job
└─ Type Mismatches
   └─ Apply optional transformation
```

## Integration Points

### Pattern 1: HTTP Endpoint

```python
@app.route("/api/sync/fab-order", methods=["POST"])
def sync_fab_order():
    """REST endpoint for on-demand sync."""
    stats = map_production_fab_order_to_sandbox(
        production_engine,
        sandbox_engine,
        dry_run=False,
        log_callback=app_logger
    )
    return jsonify(stats)
```

### Pattern 2: Scheduled Task

```python
@celery.task
def sync_fab_order_periodic():
    """Background task running every hour."""
    try:
        stats = map_production_fab_order_to_sandbox(
            prod_engine, sandbox_engine,
            dry_run=False,
            log_callback=task_logger
        )
        if stats.errors > 0:
            alert_admin(f"Sync had {stats.errors} errors")
    except Exception as e:
        log_error(f"Periodic sync failed: {e}")
```

### Pattern 3: CLI Tool

```bash
# Direct usage
python app/scripts/map_production_to_sandbox.py --dry-run
python app/scripts/map_production_to_sandbox.py
```

### Pattern 4: Embedded in Route Handler

```python
def process_request(data):
    """Handle incoming data with sync."""
    # Process data
    # ...
    # Sync if needed
    if needs_sync():
        DatabaseMappingService.apply_field_updates(
            sandbox_engine,
            results,
            dry_run=False
        )
```

## Performance Characteristics

### Time Complexity
- Fetch: O(n) where n = jobs in database
- Mapping: O(n + m) where n = prod, m = sandbox
- Updates: O(k) where k = jobs needing updates

**Total: O(n + m + k)** - Linear in database size

### Space Complexity
- Lookup dict: O(m) where m = sandbox jobs
- Results list: O(n) where n = production jobs
- DataFrames: O(n + m) for temporary storage

**Total: O(n + m)** - Linear in database size

### Database Queries
- Read Production: 1 query
- Read Sandbox: 1 query
- Update Sandbox: 1 per updated job (or batch if optimized)

**Total: 2-3 queries typical, scales with updates**

## Scaling Considerations

### Current Design (Handles 10K+ jobs)
```
Memory: ~100-500MB for 10K jobs
Time: ~30-60 seconds for 10K jobs
DB Load: Minimal (2 reads, batch updates)
```

### For 100K+ Jobs
1. **Batch Processing**
   - Fetch in chunks
   - Process incrementally

2. **Index Optimization**
   - Add (job, release) index if missing
   - Can speed up lookups

3. **Bulk Updates**
   - Use CASE statements for batch updates
   - Reduce transaction overhead

4. **Parallel Processing**
   - Split jobs by ranges
   - Process in parallel workers

## Deployment

### Prerequisites
```
✓ Environment variables set
✓ Database connections working
✓ Proper database permissions
✓ Network connectivity
```

### Deployment Steps
```
1. Deploy code changes
2. Run: python app/scripts/map_production_to_sandbox.py --dry-run
3. Review output
4. Run: python app/scripts/map_production_to_sandbox.py
5. Verify results in both databases
6. Monitor logs for errors
```

## Testing Strategy

### Unit Tests (Future)
```python
def test_fetch_jobs():
    """Test job fetching."""
def test_create_lookup():
    """Test lookup creation."""
def test_map_jobs():
    """Test job mapping logic."""
def test_field_comparison():
    """Test field comparison."""
```

### Integration Tests
```bash
python app/scripts/test_database_mapping.py --dry-run
```

### Manual Testing
```bash
# Basic test
python app/scripts/map_production_to_sandbox.py --dry-run

# Custom mapping test
python app/scripts/test_database_mapping.py

# Integration test in route
curl http://localhost:5000/api/sync/fab-order
```

## Monitoring & Logging

### Key Metrics
- Jobs matched
- Jobs not found
- Fields updated
- Update errors
- Processing time
- Database queries executed

### Log Levels
```
DEBUG: Detailed field comparisons
INFO: Matching results, updates applied
WARNING: Missing jobs, partial failures
ERROR: Connection failures, update failures
```

### Sample Logs
```
[INFO] Fetched 1250 jobs from Production
[INFO] Fetched 890 jobs from Sandbox
[INFO] Mapped 850 jobs successfully
[WARNING] 400 jobs not found in Sandbox
[INFO] fab_order updates needed: 42
[INFO] Updated 42 jobs in 2.3 seconds
```

## Future Enhancements

### Short Term
1. Batch update optimization
2. Scheduled syncing
3. Admin dashboard UI

### Medium Term
1. Bidirectional sync
2. Conflict resolution
3. Audit trail

### Long Term
1. Multi-database support
2. Custom matchers
3. Real-time streaming

