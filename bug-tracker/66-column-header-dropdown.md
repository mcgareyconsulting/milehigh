# #66 — Column Header Dropdown

**Source:** Board item #66 (open / low / Job Log)
**Author:** Daniel — 2026-04-21
**Description:** "Add Excel style column header drop-down to improve filtering capabilities on Job Log."

---

## Problem

The Job Log filters via a separate top panel: project multi-select, stage buttons, and a global search. There is no column-level filtering. If a user wants every release with `Welded QC = X` or `Paint color = "Black"`, there is no way to ask that question without scanning manually.

## Model

Excel-style header dropdown per filterable column:

- Click a small `▾` icon on the right edge of the header → popover opens.
- Popover contains:
  - Search box (filters the checklist)
  - "Sort A→Z / Sort Z→A"
  - Checkbox list of unique values present in the **currently filtered** set
  - "(Blanks)" option for null/empty
  - Clear / Apply buttons
- Active filter renders a colored funnel icon in the header so it's obvious at a glance which columns are filtered.
- Column filters compose with existing project/stage/search filters via **AND**.

## Phase 1 columns

Confirmed: include `Release #`. Skip dates, Notes, and other freeform/complex columns.

- Job #
- Release #
- Project name
- Stage *(note: redundant with the existing stage button strip — keep both for now; revisit consolidation after observing usage)*
- Fab Order
- Paint color
- Welded QC
- Job Comp
- Invoiced
- PM
- Drafter

**Explicitly out of phase 1:** Notes, Start Install, any date column. Date columns deserve a range picker, not a checklist — that's a separate piece of work.

## Implementation

### 1. New component — `frontend/src/components/ColumnHeaderFilter.jsx`

Props:
- `column` (string)
- `values` (array of unique values present in the currently filtered set)
- `selected` (array — currently selected values)
- `onChange(selected)` (fn)
- `sort` ({ direction: 'asc' | 'desc' | null })
- `onSort(direction)` (fn)

Renders the `▾` trigger and the popover (search, sort buttons, checklist, "(Blanks)", Clear/Apply). Built with existing Tailwind palette — no new dependencies. Closes on outside click or Escape.

### 2. Extend `frontend/src/hooks/useJobsFilters.js`

- New state: `columnFilters` — `{ [columnName]: Set<string> }`, persisted to `localStorage` under `jl_column_filters`.
- New state: `columnSort` — `{ column, direction }`, persisted under `jl_column_sort`.
- Extend `matchesFilters` to AND-in `columnFilters`.
- When `columnSort` is set, override the existing sort in `sortJobs`.
- `resetFilters` clears `columnFilters` and `columnSort`.

### 3. Wire into `frontend/src/pages/JobLog.jsx` header (around `:1083`)

- For each phase-1 column, render `<ColumnHeaderFilter>` next to the label inside the `<th>`.
- Compute `uniqueValuesByColumn` via `useMemo` from currently-displayed jobs so each dropdown reflects only values reachable under other active filters (Excel-style).
- Render a funnel indicator on the header when `columnFilters[col]?.size > 0`.

### 4. No backend changes

All filtering remains client-side, consistent with the rest of the page.

## Test plan

- [ ] Apply column filter → row count drops, funnel icon appears.
- [ ] Combine column filter + project + stage + search → AND semantics hold.
- [ ] Sort A→Z / Z→A overrides default order; restored on clear.
- [ ] localStorage persistence — refresh page, filters and sort survive.
- [ ] Reset Filters button clears column filters and column sort.
- [ ] "(Blanks)" matches null and empty values.
- [ ] Dropdown's value list reflects only currently-reachable values, not the entire dataset.
- [ ] Light + dark mode.
- [ ] Doesn't interfere with row drag-and-drop or column drag/resize (verify).

## Open questions / follow-ups

- **Stage column duplication.** Both the dropdown and the stage button strip filter Stage. Keep both this round and observe; retire the redundant one in a follow-up if usage suggests it.
- **Date range filtering.** Tracked separately if/when needed.
- **Mobile.** Popovers on small screens are awkward; Job Log is a desktop tool, so acceptable.

## Risks

- Pure additive frontend change; no risk to existing filter or sort code paths until a column filter or column sort is actually set.
- Performance with ~hundreds of releases × ~10 filterable columns is fine. If dataset grows past a few thousand rows, memoize unique-value computation per column independently.
