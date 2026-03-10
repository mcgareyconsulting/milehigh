# Preview Scripts: Converting to SubmittalEvents

## Overview

There are **two preview scripts** that show how your data would be converted to `SubmittalEvents`:

1. **`preview_webhook_to_submittal_events.py`** - Uses `ProcoreWebhookEvents` + `SyncLog`
2. **`preview_sync_operations_to_submittal_events.py`** - Uses `SyncOperation`/`SyncLog` directly ⭐ **RECOMMENDED**

## Recommended Approach: Direct from SyncOperations

Since the new system (`excel_poller_teardown`) doesn't use `ProcoreWebhookEvents` for tracking, the **simpler and more accurate approach** is to create `SubmittalEvents` directly from `SyncOperation`/`SyncLog` data.

### Why This Approach is Better:

✅ **Simpler** - No need to match webhook events to operations  
✅ **More Accurate** - Uses the actual operation logs that contain real change data  
✅ **Matches New System** - The new system creates events from operations, not webhook tracking  
✅ **Complete Data** - `SyncLog` has all the old/new values we need  

---

## Script 1: Direct from SyncOperations (Recommended)

### `preview_sync_operations_to_submittal_events.py`

This script finds all `SyncOperation` records for Procore submittal changes and converts them directly to `SubmittalEvents`.

**Operation Types Tracked:**
- `procore_submittal_create` → `action: 'created'`
- `procore_ball_in_court` → `action: 'updated'` (with ball_in_court changes)
- `procore_submittal_status` → `action: 'updated'` (with status changes)
- `procore_submittal_title` → `action: 'updated'` (with title changes)
- `procore_submittal_manager` → `action: 'updated'` (with manager changes)

### Usage

```bash
# Preview 10 operation groups (default)
python migrations/preview_sync_operations_to_submittal_events.py

# Preview 25 operations
python migrations/preview_sync_operations_to_submittal_events.py --limit 25

# Preview specific submittal
python migrations/preview_sync_operations_to_submittal_events.py --submittal-id 12345

# Show each operation separately (don't group)
python migrations/preview_sync_operations_to_submittal_events.py --no-group
```

### Features

**Operation Grouping:**
- Groups operations by `submittal_id` and time window (5 seconds)
- Multiple field changes within the window become one `SubmittalEvent`
- Matches how the new system would handle rapid updates

**Payload Building:**
- For **create events**: Collects initial values from `SyncLog`
- For **update events**: Builds old/new value pairs for each field changed
- Includes metadata: `submittal_id`, `project_id`, `submittal_title`, `project_name`

### Example Output

```
====================================================================================================
EVENT GROUP #1: Submittal 12345 at 2024-01-15 10:30:00
====================================================================================================

📥 SOURCE DATA (2 SyncOperation(s)):
  - Operation ID: abc123
    Type: procore_ball_in_court
    Started: 2024-01-15 10:30:01
    Source: procore / 12345
  - Operation ID: def456
    Type: procore_submittal_status
    Started: 2024-01-15 10:30:02
    Source: procore / 12345

🔗 FOUND 2 SyncLog entries:
  • Ball in court updated via webhook
    OLD: John Doe
    NEW: Jane Smith
  • Submittal status updated via webhook
    OLD: Open
    NEW: Closed

📤 TARGET DATA (SubmittalEvents):
  - submittal_id: 12345
  - action: updated
  - source: 'Procore'
  - created_at: 2024-01-15 10:30:00

📦 PAYLOAD:
{
  "migrated_from": "SyncOperation + SyncLog",
  "migration_note": "Created from sync operation logs with field changes",
  "ball_in_court": {
    "old": "John Doe",
    "new": "Jane Smith"
  },
  "status": {
    "old": "Open",
    "new": "Closed"
  },
  "submittal_id": "12345",
  "project_id": 67890
}

🔐 PAYLOAD HASH:
  a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
```

---

## Script 2: From Webhook Events (Alternative)

### `preview_webhook_to_submittal_events.py`

This script uses `ProcoreWebhookEvents` as the source and tries to match them with `SyncOperation`/`SyncLog` data.

**Use this if:**
- You want to see how webhook events map to operations
- You need to verify webhook event coverage
- You're debugging webhook processing

### Usage

```bash
# Preview 10 webhook events
python migrations/preview_webhook_to_submittal_events.py

# Preview specific submittal
python migrations/preview_webhook_to_submittal_events.py --submittal-id 12345
```

---

## Comparison

| Feature | SyncOperations Script | Webhook Events Script |
|---------|---------------------|---------------------|
| **Data Source** | `SyncOperation`/`SyncLog` | `ProcoreWebhookEvents` + `SyncLog` |
| **Complexity** | Simple (direct conversion) | Complex (needs matching) |
| **Accuracy** | High (uses actual operations) | Medium (depends on matching) |
| **Matches New System** | ✅ Yes | ❌ No (new system doesn't use webhook tracking) |
| **Time Window Matching** | Not needed | ±10 seconds |
| **Recommended** | ✅ **YES** | For debugging only |

---

## Understanding the Output

### Events with SyncLog Data
- ✅ **Complete payloads** with old/new values for each field that changed
- Shows exactly what changed (ball_in_court, status, title, etc.)
- Matches the format that the new system creates

### Events without SyncLog Data
- ⚠️ **Minimal payloads** with just metadata
- Includes migration note explaining why payload is minimal
- Still creates valid SubmittalEvent records

### Payload Hash
- Used for deduplication in the new system
- Same payload = same hash = duplicate detection
- Based on: `action:submittal_id:payload_json`

### Operation Grouping
- Operations within 5 seconds for the same submittal are grouped
- Multiple field changes become one `SubmittalEvent`
- Matches how the new system handles rapid updates

---

## Next Steps

After reviewing the preview:

1. **Verify the data looks correct** - Check that payloads match expectations
2. **Check SyncLog coverage** - See how many operations have complete data
3. **Run the actual migration** - Use the migration script based on SyncOperations
4. **Test debouncing** - Verify the new system works with migrated events

---

## Notes

- Both scripts are **READ-ONLY** - they don't modify your database
- The SyncOperations approach is simpler and more accurate
- Operation grouping (5 second window) matches how the new system works
- All migrated events will have `source='Procore'` and `user_id=None`
- The payload hash ensures duplicate events are detected
