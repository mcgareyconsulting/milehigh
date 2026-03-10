# Implementation Plan: Total Fab HRS / Total Install HRS

Branch: `ai/total_fab_install_hours` (already active)

---

## Step 1 — Backend: Pure calculation functions

**File to create:** `app/brain/job_log/scheduling/hours_summary.py`

Create a pure-function module following the exact pattern of `calculator.py`. No DB imports.

Functions to implement:

### `calculate_fab_modifier(stage: Optional[str]) -> float`

Returns the weighted modifier for remaining fab hours based on stage.

This feature defines its own explicit modifier table rather than delegating to
`SchedulingConfig.get_stage_remaining_percentage()`. The reason: `SchedulingConfig` returns
0.1 for "Welded QC" (10% remaining), but this feature requires 0.00 for both "Welded" and
"Welded QC" (fabrication complete at the weld stage). The values diverge intentionally.

```python
# Explicit modifier table — do NOT replace with SchedulingConfig delegation
_FAB_MODIFIER_TABLE: Dict[str, float] = {
    'Released': 1.0,
    'Hold': 1.0,
    'Material Ordered': 1.0,
    'Cut start': 0.9,
    'Cut Start': 0.9,       # handle capitalisation variant
    'Fit Up Complete.': 0.5,
    'Fit Up Complete': 0.5,
    'Welded': 0.0,
    'Welded QC': 0.0,
    'Paint complete': 0.0,
    'Paint Complete': 0.0,
    'Store at MHMW for shipping': 0.0,
    'Shipping planning': 0.0,
    'Shipping completed': 0.0,
    'Complete': 0.0,
}

def calculate_fab_modifier(stage: Optional[str]) -> float:
    if not stage:
        return 1.0
    normalized = stage.strip()
    return _FAB_MODIFIER_TABLE.get(normalized, 1.0)  # default 1.0 for unknown stages
```

### `calculate_total_fab_hrs(jobs: List[Dict[str, Any]]) -> float`

```python
def calculate_total_fab_hrs(jobs):
    total = 0.0
    for job in jobs:
        fab_hrs = job.get('fab_hrs') or 0.0
        stage = job.get('stage')
        modifier = calculate_fab_modifier(stage)
        total += fab_hrs * modifier
    return round(total, 2)
```

### `calculate_total_install_hrs(jobs: List[Dict[str, Any]]) -> float`

```python
def calculate_total_install_hrs(jobs):
    total = 0.0
    for job in jobs:
        install_hrs = job.get('install_hrs') or 0.0
        job_comp_raw = job.get('job_comp') or '0'
        try:
            job_comp_pct = min(float(job_comp_raw), 100.0)
        except (ValueError, TypeError):
            job_comp_pct = 0.0
        job_comp_decimal = job_comp_pct / 100.0
        total += install_hrs * job_comp_decimal
    return round(total, 2)
```

Input dict shape expected: `{ 'fab_hrs': float|None, 'install_hrs': float|None, 'stage': str|None, 'job_comp': str|None }`

---

## Step 2 — Backend: Export from package init (optional but recommended)

**File to edit:** `app/brain/job_log/scheduling/__init__.py`

Add exports so callers can import from the package directly:
```python
from app.brain.job_log.scheduling.hours_summary import (
    calculate_fab_modifier,
    calculate_total_fab_hrs,
    calculate_total_install_hrs,
)
```

If `__init__.py` is currently empty or minimal, inspect it first and add only the import lines.

---

## Step 3 — Frontend: Add computed totals to `useJobsFilters`

**File to edit:** `frontend/src/hooks/useJobsFilters.js`

The hook receives `jobs` as its argument (the full unfiltered array from `useJobsDataFetching`).
Both totals are computed from `jobs` directly, not from `displayJobs`, so they remain constant
as filters are applied.

### 3a. Add helpers above the hook body (module scope, outside the function)

Place these before the `export function useJobsFilters` line:

```js
const _parseJobComp = (raw) => {
    const n = parseFloat(raw);
    if (isNaN(n) || n < 0) return 0.0;
    return Math.min(n, 100.0) / 100.0;
};

// Explicit modifier table. "Welded" and "Welded QC" are both 0.00 —
// fabrication is considered complete at the weld stage.
const _FAB_MODIFIER = {
    'Released': 1.0,
    'Hold': 1.0,
    'Material Ordered': 1.0,
    'Cut start': 0.9,
    'Fit Up Complete.': 0.5,
    'Welded': 0.0,
    'Welded QC': 0.0,
    'Paint complete': 0.0,
    'Store at MHMW for shipping': 0.0,
    'Shipping planning': 0.0,
    'Shipping completed': 0.0,
    'Complete': 0.0,
};
```

### 3b. Add two `useMemo` values inside the hook, after the `displayJobs` memo

Both depend on `jobs` (not `displayJobs`):

```js
const totalFabHrs = useMemo(() => {
    const raw = jobs.reduce((sum, job) => {
        const fabHrs = parseFloat(job['Fab Hrs']) || 0;
        const stage = (job['Stage'] ?? '').trim();
        // Unknown stages default to 1.0 (conservative: full hours assumed remaining)
        const modifier = Object.prototype.hasOwnProperty.call(_FAB_MODIFIER, stage)
            ? _FAB_MODIFIER[stage]
            : 1.0;
        return sum + fabHrs * modifier;
    }, 0);
    return parseFloat(raw.toFixed(2));
}, [jobs]);

const totalInstallHrs = useMemo(() => {
    const raw = jobs.reduce((sum, job) => {
        const installHrs = parseFloat(job['Install HRS']) || 0;
        const jobCompDecimal = _parseJobComp(job['Job Comp']);
        return sum + installHrs * jobCompDecimal;
    }, 0);
    return parseFloat(raw.toFixed(2));
}, [jobs]);
```

`parseFloat(raw.toFixed(2))` produces a number rounded to two decimal places (e.g. `342.50`)
without converting it to a string, keeping the value numeric for the JSX render.

### 3c. Add to return object

```js
return {
    // ... existing exports ...
    totalFabHrs,
    totalInstallHrs,
};
```

---

## Step 4 — Frontend: Render stat chips in `JobLog.jsx`

**File to edit:** `frontend/src/pages/JobLog.jsx`

### 4a. Destructure new values from the filters hook

At line ~41 (the `useJobsFilters` destructure):
```js
const {
    // ... existing ...
    totalFabHrs,
    totalInstallHrs,
} = useJobsFilters(jobs);
```

### 4b. Update the bottom-right filter div

Current code (around line 809–814):
```jsx
{/* Bottom Right: Last updated */}
<div className="flex items-center justify-end">
    <div className="text-xs text-gray-600 dark:text-slate-400 whitespace-nowrap">
        Last updated: <span className="font-semibold text-gray-800 dark:text-slate-200">{formattedLastUpdated}</span>
    </div>
</div>
```

Replace with:
```jsx
{/* Bottom Right: Fab HRS, Install HRS, Last updated */}
<div className="flex items-center justify-end gap-1.5">
    <div className="px-2 py-0.5 bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 rounded text-xs font-semibold whitespace-nowrap">
        Fab HRS: <span className="text-gray-900 dark:text-slate-100 font-bold">{totalFabHrs.toFixed(2)}</span>
    </div>
    <div className="px-2 py-0.5 bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 rounded text-xs font-semibold whitespace-nowrap">
        Install HRS: <span className="text-gray-900 dark:text-slate-100 font-bold">{totalInstallHrs.toFixed(2)}</span>
    </div>
    <div className="text-xs text-gray-600 dark:text-slate-400 whitespace-nowrap">
        Last updated: <span className="font-semibold text-gray-800 dark:text-slate-200">{formattedLastUpdated}</span>
    </div>
</div>
```

`.toFixed(2)` is called at the render site to guarantee the display string always shows two
decimal places (e.g. `342.00` not `342`), even when the computed value is a whole number.

The chip style mirrors the existing "Total: N records" chip at line 804 for visual consistency.

---

## Step 5 — Tests

**File to create:** `tests/test_hours_summary.py`

Write pytest unit tests for the three new backend functions.

Test cases:

```python
from app.brain.job_log.scheduling.hours_summary import (
    calculate_fab_modifier,
    calculate_total_fab_hrs,
    calculate_total_install_hrs,
)

class TestCalculateFabModifier:
    def test_released_returns_1(self):
        assert calculate_fab_modifier('Released') == 1.0

    def test_hold_returns_1(self):
        assert calculate_fab_modifier('Hold') == 1.0

    def test_material_ordered_returns_1(self):
        assert calculate_fab_modifier('Material Ordered') == 1.0

    def test_cut_start_returns_09(self):
        assert calculate_fab_modifier('Cut start') == 0.9

    def test_fit_up_returns_05(self):
        assert calculate_fab_modifier('Fit Up Complete.') == 0.5

    def test_welded_returns_0(self):
        # Welded (no QC) is 0.00 — fabrication complete at weld stage
        assert calculate_fab_modifier('Welded') == 0.0

    def test_welded_qc_returns_0(self):
        # Welded QC is also 0.00 — same as Welded
        assert calculate_fab_modifier('Welded QC') == 0.0

    def test_paint_complete_returns_0(self):
        assert calculate_fab_modifier('Paint complete') == 0.0

    def test_shipping_completed_returns_0(self):
        assert calculate_fab_modifier('Shipping completed') == 0.0

    def test_complete_returns_0(self):
        assert calculate_fab_modifier('Complete') == 0.0

    def test_none_stage_returns_1(self):
        assert calculate_fab_modifier(None) == 1.0

    def test_empty_string_returns_1(self):
        assert calculate_fab_modifier('') == 1.0

    def test_unknown_stage_returns_1(self):
        # Conservative default: assume full hours remain for any unrecognised stage
        assert calculate_fab_modifier('Some Unknown Stage') == 1.0


class TestCalculateTotalFabHrs:
    def test_empty_list(self):
        assert calculate_total_fab_hrs([]) == 0.0

    def test_single_released_job(self):
        jobs = [{'fab_hrs': 100.0, 'stage': 'Released'}]
        assert calculate_total_fab_hrs(jobs) == 100.0

    def test_cut_start_multiplied(self):
        jobs = [{'fab_hrs': 100.0, 'stage': 'Cut start'}]
        assert calculate_total_fab_hrs(jobs) == 90.0

    def test_welded_contributes_zero(self):
        jobs = [{'fab_hrs': 100.0, 'stage': 'Welded'}]
        assert calculate_total_fab_hrs(jobs) == 0.0

    def test_welded_qc_contributes_zero(self):
        jobs = [{'fab_hrs': 100.0, 'stage': 'Welded QC'}]
        assert calculate_total_fab_hrs(jobs) == 0.0

    def test_null_fab_hrs_treated_as_zero(self):
        jobs = [{'fab_hrs': None, 'stage': 'Released'}]
        assert calculate_total_fab_hrs(jobs) == 0.0

    def test_multiple_jobs_summed(self):
        jobs = [
            {'fab_hrs': 100.0, 'stage': 'Released'},       # 100 * 1.0 = 100.0
            {'fab_hrs': 100.0, 'stage': 'Cut start'},      # 100 * 0.9 = 90.0
            {'fab_hrs': 100.0, 'stage': 'Welded'},         # 100 * 0.0 = 0.0
            {'fab_hrs': 100.0, 'stage': 'Welded QC'},      # 100 * 0.0 = 0.0
            {'fab_hrs': 100.0, 'stage': 'Paint complete'}, # 100 * 0.0 = 0.0
        ]
        assert calculate_total_fab_hrs(jobs) == 190.0

    def test_result_rounded_to_two_decimal_places(self):
        jobs = [{'fab_hrs': 10.0, 'stage': 'Cut start'}]  # 10 * 0.9 = 9.0 exactly
        result = calculate_total_fab_hrs(jobs)
        assert result == 9.0
        # Verify it's a float with two decimal precision (not e.g. 8.999999999)
        assert result == round(result, 2)


class TestCalculateTotalInstallHrs:
    def test_empty_list(self):
        assert calculate_total_install_hrs([]) == 0.0

    def test_null_job_comp_treated_as_zero(self):
        jobs = [{'install_hrs': 100.0, 'job_comp': None}]
        assert calculate_total_install_hrs(jobs) == 0.0

    def test_empty_string_job_comp_treated_as_zero(self):
        jobs = [{'install_hrs': 100.0, 'job_comp': ''}]
        assert calculate_total_install_hrs(jobs) == 0.0

    def test_50_percent_job_comp(self):
        jobs = [{'install_hrs': 100.0, 'job_comp': '50'}]
        assert calculate_total_install_hrs(jobs) == 50.0

    def test_100_percent_job_comp(self):
        jobs = [{'install_hrs': 80.0, 'job_comp': '100'}]
        assert calculate_total_install_hrs(jobs) == 80.0

    def test_job_comp_exceeding_100_capped(self):
        jobs = [{'install_hrs': 100.0, 'job_comp': '150'}]
        assert calculate_total_install_hrs(jobs) == 100.0

    def test_non_numeric_job_comp_treated_as_zero(self):
        jobs = [{'install_hrs': 100.0, 'job_comp': 'N/A'}]
        assert calculate_total_install_hrs(jobs) == 0.0

    def test_multiple_jobs_summed(self):
        jobs = [
            {'install_hrs': 100.0, 'job_comp': '50'},   # 50.0
            {'install_hrs': 80.0,  'job_comp': '100'},  # 80.0
            {'install_hrs': 60.0,  'job_comp': None},   # 0.0
        ]
        assert calculate_total_install_hrs(jobs) == 130.0

    def test_result_rounded_to_two_decimal_places(self):
        jobs = [{'install_hrs': 10.0, 'job_comp': '33'}]  # 10 * 0.33 = 3.3
        result = calculate_total_install_hrs(jobs)
        assert result == round(result, 2)
```

---

## Verification Checklist

- [ ] `hours_summary.py` created with all three functions
- [ ] `_FAB_MODIFIER_TABLE` in `hours_summary.py` has `'Welded': 0.0` and `'Welded QC': 0.0`
- [ ] `__init__.py` updated to export new functions
- [ ] `useJobsFilters.js` helpers `_parseJobComp` and `_FAB_MODIFIER` are module-scoped (outside the function)
- [ ] `useJobsFilters.js` `totalFabHrs` and `totalInstallHrs` depend on `jobs`, not `displayJobs`
- [ ] `useJobsFilters.js` exports `totalFabHrs` and `totalInstallHrs`
- [ ] `JobLog.jsx` destructures `totalFabHrs` and `totalInstallHrs` from `useJobsFilters`
- [ ] `JobLog.jsx` renders `{totalFabHrs.toFixed(2)}` and `{totalInstallHrs.toFixed(2)}`
- [ ] Chips are visually consistent with existing "Total: N records" chip
- [ ] Totals do NOT change when filters are applied (they reflect the full dataset)
- [ ] All backend unit tests pass: `pytest tests/test_hours_summary.py`
- [ ] UI smoke test: apply a stage filter, confirm Fab HRS and Install HRS remain unchanged
- [ ] UI smoke test: values display two decimal places (e.g. `342.50`, not `342`)

---

## Notes for Implementer

- The `_FAB_MODIFIER` object in the frontend JS and `_FAB_MODIFIER_TABLE` in the backend must
  use identical stage strings. The authoritative stage string list is `useJobsFilters.stageOptions`
  (values, not labels) — e.g. `"Cut start"` (lowercase s), `"Fit Up Complete."` (with trailing dot).

- The API field for fabrication hours is `"Fab Hrs"` (capital F, lowercase h) as serialized
  at `routes.py` line 366. The install hours field is `"Install HRS"` (all-caps HRS). Use
  these exact key strings in the JS reduce callbacks.

- `"Job Comp"` arrives as a string (`"75"`, `"100"`, `""`) or `null`. The `_parseJobComp`
  helper handles all cases including `null`, empty string, and non-numeric values.

- `totalFabHrs` and `totalInstallHrs` must depend on `jobs` (the raw unfiltered array), NOT
  on `displayJobs`. This is the defining constraint of this feature: totals are dataset KPIs,
  not filtered subtotals.

- The backend `_FAB_MODIFIER_TABLE` intentionally diverges from `SchedulingConfig` for
  "Welded" and "Welded QC" (this feature uses 0.00; the scheduling engine uses 0.10 for
  "Welded QC"). Do not replace the explicit table with a `SchedulingConfig` delegation.

- `.toFixed(2)` is called in JSX at the render site, not in the `useMemo`. The `useMemo`
  stores a number; the render converts it to a display string. This keeps the value
  numeric for any future consumers of the hook.
