# Relevant Files: Total Fab HRS / Total Install HRS

## Backend — New Files

| File | Purpose |
|---|---|
| `app/brain/job_log/scheduling/hours_summary.py` | New pure-function module: `calculate_fab_modifier(stage)`, `calculate_total_fab_hrs(jobs)`, `calculate_total_install_hrs(jobs)` |

## Backend — Unchanged (referenced for context)

| File | Relevance |
|---|---|
| `app/brain/job_log/scheduling/calculator.py` | Existing pure-function scheduling module — `hours_summary.py` follows its pattern exactly |
| `app/brain/job_log/scheduling/config.py` | Defines `STAGE_REMAINING_FAB_PERCENTAGE` — the fab modifier table maps to the same stage strings |
| `app/brain/job_log/scheduling/__init__.py` | Package init — may need to export new functions |
| `app/brain/job_log/routes.py` | Hosts `/brain/jobs` and `/brain/get-all-jobs`; serializes `fab_hrs`, `install_hrs`, `stage`, `Job Comp` — no changes needed |
| `app/models.py` | `Releases` model — `fab_hrs`, `install_hrs`, `stage`, `job_comp` fields confirmed present |

## Frontend — Modified Files

| File | Change |
|---|---|
| `frontend/src/hooks/useJobsFilters.js` | Add `totalFabHrs` and `totalInstallHrs` computed values derived from `displayJobs`; export them from the hook's return object |
| `frontend/src/pages/JobLog.jsx` | Destructure the two new values from `useJobsFilters`; render them as stat chips in the bottom-right filter row, to the left of "Last updated" |

## Frontend — Unchanged (referenced for context)

| File | Relevance |
|---|---|
| `frontend/src/hooks/useJobsDataFetching.js` | Provides `jobs` array; each job has `Fab Hrs`, `Install HRS`, `Stage`, `Job Comp` keys from the API serializer |
| `frontend/src/services/jobsApi.js` | No new API calls needed |

## Tests — New Files

| File | Purpose |
|---|---|
| `tests/test_hours_summary.py` | Unit tests for `calculate_fab_modifier`, `calculate_total_fab_hrs`, `calculate_total_install_hrs` |
