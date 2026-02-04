# Branch Comparison: main vs excel_poller_teardown

## Overview
This document summarizes the key differences between `main` and `excel_poller_teardown` branches, focusing on:
- Procore subdirectory changes
- models.py changes
- Drafting Work Load UI elements

---

## 🔴 PROcore Subdirectory Changes

### 1. **app/procore/__init__.py** (Webhook Handler)

#### Key Changes:
- **Debouncing System Overhaul**:
  - **main**: Uses `ProcoreWebhookEvents` table with 0.5 second debounce window
  - **excel_poller_teardown**: Uses `SubmittalEvents` table with 8 second debounce window
  - Changed from `UPDATE_DEBOUNCE_SECONDS = 0.5` to `DEBOUNCE_SECONDS = 8`
  
- **Event Tracking**:
  - **main**: Tracks events in `ProcoreWebhookEvents` with `resource_id`, `project_id`, `event_type`
  - **excel_poller_teardown**: Uses `SubmittalEvents` with `action`, `payload`, `payload_hash` pattern (similar to JobEvents)

- **Import Changes**:
  - Removed: `from app.sync.context import sync_operation_context`
  - Added: `from app.trello.context import sync_operation_context`
  - Changed: `ProcoreWebhookEvents` → `SubmittalEvents`

#### Impact:
- More robust event tracking with payload hashing
- Longer debounce window (8s vs 0.5s) may reduce duplicate processing
- Better integration with event-driven architecture

---

### 2. **app/procore/procore.py** (Business Logic)

#### Key Changes:

**A. Event Creation System**:
- **NEW**: `_create_submittal_payload_hash()` function - creates SHA-256 hash of payloads to prevent duplicates
- **NEW**: Creates `SubmittalEvents` records for both `create` and `update` actions
- Events include full payload with old/new values for updates

**B. Submittal Creation**:
- **NEW**: Extracts `created_at` from Procore API response (with fallback to `datetime.utcnow()`)
- **REMOVED**: `last_bic_update` field tracking (now calculated from events)
- **NEW**: Creates `SubmittalEvent` after successful submittal creation

**C. Submittal Updates**:
- **REMOVED**: Direct `last_bic_update` field updates
- **NEW**: Creates `SubmittalEvent` with payload containing old/new values for:
  - `ball_in_court`
  - `status`
  - `title`
  - `submittal_manager`
  - `order_bumped` flag

**D. Order Bump Logic**:
- **SIMPLIFIED**: Removed complex decimal conversion for numbers >= 10
  - **main**: `current_order >= 10 ? current_order / 100.0 : current_order / 10.0`
  - **excel_poller_teardown**: Always `current_order / 10.0`

**E. New Function**:
- **NEW**: `get_viewer_url_for_job()` - Gets viewer URL without updating Trello (for backfilling)

#### Impact:
- Event-driven architecture with full audit trail
- Better tracking of changes over time
- Simplified order bump logic (may affect urgency calculations)

---

### 3. **app/procore/api.py** (API Client)

#### Key Changes:

**A. Bug Fix**:
- **FIXED**: `params=None` AttributeError issue
  ```python
  # Before: params could be None, causing AttributeError
  # After: Ensures params defaults to empty dict
  if params is None:
      params = {}
  ```

**B. Pagination Support**:
- **NEW**: `get_submittals()` now supports pagination for v2.0 API
- Handles paginated responses: `{"data": [...], "total": N, "per_page": M, "page": P}`
- Automatically fetches all pages (100 items per page)

#### Impact:
- Fixes memory issue from [[memory:10929777]]
- Better handling of large submittal lists
- More robust API client

---

## 🟡 models.py Changes

### Major Model Changes:

#### 1. **New Models Added**:

**A. `User` Model**:
```python
- id, username, password_hash
- is_active, is_admin
- Relationships: job_events, submittal_events
```

**B. `SubmittalEvents` Model**:
```python
- submittal_id, action, payload (JSON)
- payload_hash (for deduplication)
- source, user_id, created_at, applied_at
```

**C. `JobEvents` Model**:
```python
- job, release, action, payload (JSON)
- payload_hash, source, user_id
- created_at, applied_at
```

**D. `Outbox` Model**:
```python
- event_id (FK to JobEvents)
- destination, action
- status, retry_count, max_retries
- next_retry_at, error_message
```

**E. `SystemLogs` Model**:
```python
- timestamp, level, category, operation
- message, context (JSON)
```

#### 2. **Removed Models**:

- **REMOVED**: `ProcoreWebhookEvents` (replaced by `SubmittalEvents`)
- **REMOVED**: `JobChangeLog` (replaced by `JobEvents`)

#### 3. **ProcoreSubmittal Model Changes**:

**A. Removed Fields**:
- `due_date` - Removed completely
- `last_bic_update` - Removed (now calculated from events)

**B. New Methods**:
- `get_last_ball_in_court_update_time()` - Queries `SubmittalEvents` for last BIC update
- `get_time_since_ball_in_court_update()` - Calculates time delta since last BIC update

**C. Enhanced `to_dict()` Method**:
- **NEW**: `last_ball_in_court_update` (ISO format)
- **NEW**: `time_since_ball_in_court_update_seconds`
- **NEW**: `days_since_ball_in_court_update` (for aging reports)
- **CHANGED**: `last_updated` and `created_at` now return ISO format strings

#### 4. **Job Model Changes**:

**A. Field Replacements**:
- **REMOVED**: `cut_start`, `fitup_comp`, `welded`, `paint_comp`, `ship`
- **ADDED**: `stage`, `stage_group`, `banana_color`

**B. Impact**:
- Simplified job tracking with stage-based system
- Color coding support (red/yellow/green)

---

## 🟢 Drafting Work Load UI Changes

### 1. **frontend/src/pages/DraftingWorkLoad.jsx**

#### Major Removals:

**A. Removed Features**:
- ❌ **Excel Upload**: Entire file upload functionality removed
  - Removed: `uploadFile`, `uploading`, `uploadError`, `uploadSuccess` states
  - Removed: File input and upload button
  - Removed: Upload success/error alerts

- ❌ **Re-Order Button**: Group reordering functionality removed
  - Removed: `reorderGroup`, `updating` states
  - Removed: Re-order button and confirmation dialog
  - Removed: `handleReorderClick`, `handleReorderConfirm`, `handleReorderCancel`

- ❌ **Due Date**: Due date editing removed
  - Removed: `updateDueDate` mutation
  - Removed: Due date column/field

- ❌ **Procore Status Filter**: Filter removed
  - Removed: `selectedProcoreStatus`, `procoreStatusOptions`
  - Removed: Procore Status filter button group
  - Removed: Tab-based filter visibility logic

**B. Tab Filtering Changes**:
- **main**: Draft tab shows all except 'Open' and 'Closed'
- **excel_poller_teardown**: Draft tab shows only status = "Draft"
- **main**: Open tab shows only status = "Open"
- **excel_poller_teardown**: Open tab shows all except status = "Draft"

**C. Column Visibility**:
- **NEW**: Hides "Submittals Id" column (`visibleColumns` filter)
- **REMOVED**: Dynamic column filtering based on tab

**D. UI Simplifications**:
- Removed banana icon from header
- Simplified header layout
- Removed upload success/error alerts

#### Impact:
- Cleaner, simpler UI
- Removed Excel import functionality (likely moved to different workflow)
- More focused on core drafting workload management

---

### 2. **frontend/src/hooks/useDataFetching.js**

#### Changes:

**A. Data Validation**:
- **REMOVED**: Defensive check for missing `submittals` in API response
  ```javascript
  // Removed this check:
  if (!data || !data.submittals) {
      console.warn('API response missing submittals:', data);
      // ...
  }
  ```

**B. Polling Logic**:
- **CHANGED**: Polling always starts (not conditional on tab visibility)
- **CHANGED**: Polling interval checks visibility inside callback
- **SIMPLIFIED**: Less complex visibility change handling

#### Impact:
- Slightly less defensive (assumes API always returns valid data)
- More consistent polling behavior

---

### 3. **frontend/src/hooks/useFilters.js**

#### Major Changes:

**A. New Utility Functions**:
- **NEW**: `getColumnValue()` - Maps display column names to database field names
- **NEW**: `compareValues()` - Handles text, numbers, dates, nulls for sorting

**B. Removed Features**:
- ❌ **Procore Status Filter**: Completely removed
  - Removed: `selectedProcoreStatus` state
  - Removed: `procoreStatusOptions` calculation
  - Removed: Filter matching logic

**C. Sorting System**:
- **CHANGED**: From `projectNameSortMode` ('normal', 'a-z', 'z-a') to generic `columnSort`
- **NEW**: `columnSort` state: `{ column: string, direction: 'asc' | 'desc' | null }`
- **NEW**: `handleColumnSort()` function for general column sorting
- **ENHANCED**: Default sort maintains Ball In Court grouping with multi-assignee handling

#### Impact:
- More flexible sorting system (can sort any column)
- Removed Procore Status filtering capability
- Better handling of different data types in sorting

---

### 4. **app/brain/routes/dwl_routes.py** → **app/brain/drafting_work_load/routes.py**

#### Changes:

**A. File Location**:
- **MOVED**: From `app/brain/routes/dwl_routes.py` to `app/brain/drafting_work_load/routes.py`
- Better organization (dedicated module for DWL)

**B. Authentication**:
- **NEW**: All routes now require `@login_required` decorator
  - `/drafting-work-load` (GET)
  - `/drafting-work-load/order` (PUT)
  - `/drafting-work-load/notes` (PUT)
  - `/drafting-work-load/submittal-drafting-status` (PUT)

**C. Removed Routes**:
- ❌ `/drafting-work-load/due-date` (PUT) - Due date updates removed
- ❌ `/drafting-work-load/reorder-group` (POST) - Group reordering removed

**D. Query Filtering**:
- **CHANGED**: `/drafting-work-load` now filters by status:
  ```python
  # Before: All submittals
  submittals = ProcoreSubmittal.query.all()
  
  # After: Only Open and Draft
  submittals = ProcoreSubmittal.query.filter(
      ProcoreSubmittal.status.in_(['Open', 'Draft'])
  ).all()
  ```

#### Impact:
- Better security (authentication required)
- Cleaner API (removed unused endpoints)
- More focused data (only relevant statuses)

---

### 5. **app/brain/services/dwl_service.py**

#### Changes:

**A. Notes Update**:
- **CHANGED**: Notes updates now update `last_updated` timestamp
  ```python
  # Before: Notes changes don't affect ordering
  # Do NOT update last_updated
  
  # After: Notes changes update timestamp
  submittal.last_updated = datetime.utcnow()
  ```

**B. Removed Method**:
- ❌ `reorder_group_to_start_from_one()` - Removed (no longer needed)

#### Impact:
- Notes changes now affect submittal ordering
- Simpler service (removed unused functionality)

---

## 📊 Summary of Key Differences

### Architecture Changes:
1. **Event-Driven System**: Moved from simple webhook tracking to full event sourcing with `SubmittalEvents` and `JobEvents`
2. **Authentication**: Added `@login_required` to all DWL routes
3. **Debouncing**: Increased from 0.5s to 8s, using event-based deduplication

### Feature Removals:
1. ❌ Excel upload functionality
2. ❌ Group reordering feature
3. ❌ Due date field and editing
4. ❌ Procore Status filter
5. ❌ `last_bic_update` direct field (now calculated from events)

### Feature Additions:
1. ✅ Event tracking with payload hashing
2. ✅ Aging report support (`days_since_ball_in_court_update`)
3. ✅ Pagination support in API client
4. ✅ Generic column sorting
5. ✅ Stage-based job tracking

### Bug Fixes:
1. ✅ Fixed `params=None` AttributeError in ProcoreAPI
2. ✅ Better error handling in API client

---

## 🎯 Cherry-Picking Recommendations

### High Value (Recommended):
1. **Event System** (`SubmittalEvents` model + creation logic) - Better audit trail
2. **API Pagination** (`app/procore/api.py`) - Handles large datasets
3. **params=None Fix** (`app/procore/api.py`) - Critical bug fix
4. **Aging Report Support** (`ProcoreSubmittal.get_last_ball_in_court_update_time()`) - Useful feature

### Medium Value (Consider):
1. **Authentication** (`@login_required` decorators) - Security improvement
2. **Generic Column Sorting** (`useFilters.js`) - More flexible UI
3. **Simplified Order Bump** (if you want simpler logic)

### Low Value / Risky:
1. **8s Debounce** - May be too long, test carefully
2. **Removed Excel Upload** - Only if you don't need it
3. **Stage-based Jobs** - Only if you want to replace current system

---

## ⚠️ Breaking Changes

1. **Database Schema**: Requires migration for new models (`SubmittalEvents`, `JobEvents`, `Outbox`, `User`, `SystemLogs`)
2. **Removed Fields**: `due_date`, `last_bic_update` in `ProcoreSubmittal`
3. **Job Model**: `cut_start`, `fitup_comp`, etc. replaced with `stage`, `stage_group`
4. **API Routes**: Removed `/due-date` and `/reorder-group` endpoints
5. **Authentication**: All DWL routes now require login

---

## 🔧 Migration Considerations

If cherry-picking:
1. Create database migrations for new models
2. Migrate data from `ProcoreWebhookEvents` to `SubmittalEvents` (if needed)
3. Update frontend to handle removed features
4. Test authentication flow
5. Verify event creation doesn't cause performance issues

