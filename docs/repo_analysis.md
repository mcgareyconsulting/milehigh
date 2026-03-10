# Repository Analysis: Total Fab HRS / Total Install HRS

## Architecture Assessment

This feature is additive and touches two isolated areas: a new backend utility module and a
small frontend UI addition. No database changes, no new API routes, no new models.

---

## Backend Observations

### Scheduling module pattern

`app/brain/job_log/scheduling/` already contains:
- `calculator.py` — pure functions, no DB imports, works on plain dicts.
- `config.py` — constants (`STAGE_REMAINING_FAB_PERCENTAGE`).
- `service.py` — DB-touching layer calling calculator.
- `preview.py` — preview/reporting helper.

The new `hours_summary.py` must follow the same pure-function pattern as `calculator.py`.
It receives a list of job dicts and returns floats. No DB imports.

### Stage modifier alignment

The fab modifier for this feature is conceptually identical to `STAGE_REMAINING_FAB_PERCENTAGE`
in `config.py`. However, the feature description explicitly states a simplified three-bucket
mapping (cut=10%, fitup=50%, welded/qc=0%) rather than the full percentage table.

Implementation must decide: use `SchedulingConfig.get_stage_remaining_percentage()` directly,
or define a separate explicit modifier map. Recommendation: reuse
`SchedulingConfig.get_stage_remaining_percentage()` to avoid drift — the values match.

| Stage | `SchedulingConfig` value | Feature modifier |
|---|---|---|
| Released | 1.0 | 1.0 (default) |
| Cut start | 0.9 | 0.10 |
| Fit Up Complete. | 0.5 | 0.50 |
| Welded QC | 0.1 | 0.00 (described as welded/qc = 0%) |
| Paint complete+ | 0.0 | 0.00 |

There is a discrepancy: the feature description says "cut = 10%" but `SchedulingConfig` says
90% remaining (i.e., 10% complete, 90% remaining). The "modifier" in this feature means
"how much fab hrs remains weighted by stage" which is exactly the `SchedulingConfig` percentage.
The `cut = 10%` in the context likely means "10% complete, so 90% remains" — but is stated
ambiguously. Recommend confirming, and in the meantime implementing the modifier to use
`SchedulingConfig.get_stage_remaining_percentage()` for consistency.

**Action item**: Clarify with client whether "modifier" = remaining percentage or completion
percentage.

### job_comp field

`Releases.job_comp` is stored as `db.Column(db.String(8))`. The serialized API key is
`"Job Comp"`. Values are strings like `"75"`, `"100"`, `""`, or `None`.

The install hours formula `install_hrs * job_comp_decimal` requires parsing this string to
float. The parsing must be done in the frontend JavaScript utility.

---

## Frontend Observations

### Data already available

Both `useJobsDataFetching` and the `/brain/get-all-jobs` route already return per-row:
- `"Fab Hrs"` → `fab_hrs` float
- `"Install HRS"` → `install_hrs` float
- `"Stage"` → stage string
- `"Job Comp"` → job_comp string

No API changes are needed.

### Best hook placement

`useJobsFilters.js` already owns `displayJobs` (the filtered/sorted job list) and exports
it. Adding `totalFabHrs` and `totalInstallHrs` as `useMemo` values inside this hook is the
correct placement — they are derived from the same filtered set.

### UI placement

The filter panel bottom row in `JobLog.jsx` (around line 809–814) uses:
```jsx
{/* Bottom Right: Last updated */}
<div className="flex items-center justify-end">
    <div className="text-xs text-gray-600 ...">
        Last updated: ...
    </div>
</div>
```

The two new chips are inserted inside this `flex items-center justify-end` div, to the left
of the Last updated text node. This requires converting the inner layout to a `flex gap`
pattern:
```
[Fab HRS chip] [Install HRS chip] [Last updated text]
```

The chip style matches the "Total: N records" chip at line 804.

### No new component needed

The stat chips are simple inline JSX — no dedicated component is warranted at this scale.

---

## Summary of Changes

| Layer | Files changed | Risk |
|---|---|---|
| Backend utility | 1 new file | Low |
| Backend init export | 1 minor edit (optional) | Low |
| Frontend hook | 1 existing file | Low |
| Frontend page | 1 existing file (UI only) | Low |
| Tests | 1 new test file | Low |

Total risk: Low. The feature is read-only, derived, and isolated from all write paths.
