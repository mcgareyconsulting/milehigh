# Expanded Feature Specification: Total Fab HRS / Total Install HRS

## Problem Statement

Operations staff reviewing the Job Log have no quick way to see aggregate hour totals across
all visible jobs. They must mentally sum individual row values to estimate total fabrication
workload remaining and total installation hours committed. This slows production planning and
daily capacity conversations.

## Desired Behavior

Two summary stats appear in the filter header of the Job Log — "Total Fab HRS" and
"Total Install HRS" — positioned to the left of the existing "Last updated" timestamp on the
bottom-right row of the filter panel.

These values reflect **all jobs in the database**, regardless of the current filter state.
The totals are static summaries of the full dataset and do not change as filters are applied.
They are computed once from the unfiltered `jobs` array provided by `useJobsDataFetching`.

### Total Install HRS formula

```
Total Install HRS = sum over ALL jobs of (install_hrs * job_comp_decimal)
```

Where `job_comp_decimal` is the numeric interpretation of the `job_comp` field (e.g. "75" → 0.75,
"100" → 1.0, null or unparseable → 0.0).

### Total Fab HRS formula

```
Total Fab HRS = sum over ALL jobs of (fab_hrs * fab_modifier)
```

Where `fab_modifier` is determined by the job's `stage`:

| Stage | Modifier |
|---|---|
| `"Released"` | 1.00 |
| `"Hold"` | 1.00 |
| `"Material Ordered"` | 1.00 |
| `"Cut start"` | 0.90 |
| `"Fit Up Complete."` | 0.50 |
| `"Welded"` | 0.00 |
| `"Welded QC"` | 0.00 |
| All READY_TO_SHIP stages (`"Paint complete"`, `"Store at MHMW for shipping"`, `"Shipping planning"`) | 0.00 |
| All COMPLETE stages (`"Shipping completed"`, `"Complete"`) | 0.00 |
| Unknown/missing stage | 1.00 (conservative default) |

"Welded" and "Welded QC" both use modifier 0.00 — fabrication is considered complete at the
welding stage regardless of QC status.

### Display format

Values are displayed to **two decimal places**, with a label:
- `Fab HRS: 342.50`
- `Install HRS: 118.25`

If either value is zero (no jobs or all zeroes), display `0.00`.

## UI Location

Bottom row of the filter header, between the existing "Total: N records" chip and the
"Last updated" timestamp. The bottom row currently uses a two-column flex layout
(`justify-between`): left side holds Reset Filters / search inputs / record count; right side
holds Last Updated. The two new stat chips are inserted **inside** the right-side div, to the
left of the Last Updated text.

Target DOM location (paraphrased):
```
[Bottom Right div]
  [Fab HRS: 342]  [Install HRS: 118]  Last updated: ...
```

The chips should visually match the "Total: N records" chip style
(`px-2 py-0.5 bg-white border border-gray-300 text-gray-700 rounded text-xs font-semibold`).

## System Constraints

- Calculations must run entirely on the **frontend** against the full unfiltered `jobs` array — no new API call required.
- The backend already stores `fab_hrs`, `install_hrs`, `stage`, and `job_comp` on each serialized
  job row. No new DB columns are needed.
- The modifier logic must live in a **pure function** in the backend scheduling module
  (`app/brain/job_log/scheduling/`) for reusability, even though the initial UI consumer
  calls it on the frontend (the frontend reimplements the same logic in JS).
- Backend pure function placement ensures future server-side aggregation endpoints can share it.

## Edge Cases

| Scenario | Behavior |
|---|---|
| `fab_hrs` is null/missing | Treat as 0 |
| `install_hrs` is null/missing | Treat as 0 |
| `job_comp` is null, empty, or non-numeric | Treat as 0.0 (not yet set) |
| `job_comp` exceeds 100 | Cap at 100 before dividing |
| Stage not in modifier map | Default modifier = 1.0 (conservative: assume full hours remain) |
| `jobs` array is empty | Display `0.00` for both |
| Non-FABRICATION stages (READY_TO_SHIP, COMPLETE) | Modifier = 0.00; those jobs contribute 0 fab hrs |

## Performance Considerations

- Both calculations are O(n) over the full `jobs` array. With a typical dataset of ~200–400 active
  releases, this is negligible and safe to run inside `useMemo`.
- No debounce required — the values derive from `jobs` (the raw fetch result) which is already
  stable state from `useJobsDataFetching`. They recompute only when `jobs` changes, not on
  every filter interaction.

## Security Considerations

- Read-only display: no user input, no mutation, no API call.
- Values are derived from data already fetched and visible to the authenticated user.
- No additional authorization surface.

## API Behavior

No new API endpoints are required for this feature.

The existing `/brain/get-all-jobs` and `/brain/jobs` endpoints already return `fab_hrs`,
`install_hrs`, `stage`, and `Job Comp` in each row's serialized payload. No backend changes
are strictly required for the frontend display.

However, the backend should also receive the pure calculation functions as reusable utilities
in `app/brain/job_log/scheduling/` per the client's stated requirement.

## Confirmed Decisions

1. **Scope:** Totals reflect **all jobs in the database**, not the currently filtered set.
   The chips are dataset-level KPIs that remain constant as filters change.

2. **Welded modifier:** Both `"Welded"` and `"Welded QC"` use modifier **0.00**.
   Fabrication is considered complete at the weld stage regardless of QC status.

3. **Display precision:** Values are displayed to **two decimal places** (e.g., `342.50`).
