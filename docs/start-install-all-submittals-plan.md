# Make Start Install settable on all submittals (deferred handoff)

> **Status: ON HOLD** — design is complete and reviewed, but implementation is
> paused pending client confirmation before turning the behavior on. The open
> question for the client is whether a non-propagating planning date on
> non-DRR submittals is useful or confusing (see "Known behavior" below).

## Context

On the DWL, the desired **start install** date can today only be set on a
submittal that is type **DRR** ("Drafting Release Review") *and* already has a
**Rel** number assigned. The Rel is the sole join key that carries the date to
the job log: setting start install writes a `PendingStartInstall` row keyed by
`rel`, and when a release is pasted into the Job Log, the matching unconsumed
pending row stamps the date onto the new `Releases` row.

We want drafters to be able to record a desired install date on **any**
submittal (all types, both the Open and Draft tabs). The risk is real:
**without a Rel there is no join key**, so a date set on a no-Rel submittal has
nowhere to land in the job log, and the current code would try to create a
`PendingStartInstall` with `rel=None` (a `NOT NULL` column → flush error).

**Decisions made:**
1. **Defer the handoff until a Rel exists.** Allow setting the date on any
   submittal; store it on the row. Create/refresh the `PendingStartInstall`
   handoff only when a Rel is present, and auto-create it from the already-set
   date at the moment a Rel is assigned. No Rel → the date stays a DWL planning
   value, never lost.
2. **Keep the DDD overwrite for all types** — setting start install still
   rewrites `due_date` to 15 business days before (the Design Drawings Due
   date), unchanged from today.
3. **All submittal types are eligible, on both Open and Draft tabs.**

**Known behavior to communicate (the client question):** Rel assignment stays
DRR-only (`assign_rel_manual` is unchanged). So a date on a non-DRR submittal
is informational on the DWL and will **not** propagate to the job log. A date
on a DRR submittal set *before* its Rel will propagate as soon as the Rel is
assigned. No schema change is required (the `start_install` column already
exists on `Submittals`).

## Changes

### 1. Service: extract a Rel-guarded pending-sync helper
File: `app/brain/drafting_work_load/service.py`

- Add `DraftingWorkLoadService.sync_pending_start_install(submittal)` that
  keeps the `PendingStartInstall` row in sync with `submittal.rel` +
  `submittal.start_install`, and **no-ops when `submittal.rel is None`** (this
  is the core fix — no join key, nothing to hand off). When a Rel is present it
  upserts the pending row (job_number, submittal_id, start_install, and
  re-opens it by clearing `consumed_*`) if a date is set, or deletes it if the
  date was cleared. This is the existing inline block from
  `update_start_install` (currently lines ~244-258) lifted into a reusable
  method with the `rel is None` guard added.
- In `update_start_install` (lines 197-264): replace the inline pending block
  with a call to `sync_pending_start_install(submittal)`. Update the docstring
  (drop "must be a DRR with a Rel"). The DDD/due_date overwrite logic stays
  as-is per decision 2.

### 2. Backend route: drop the DRR + Rel gate
File: `app/brain/drafting_work_load/routes.py`, `update_submittal_start_install`
(lines 588-649)

- Remove `from app.procore.procore import DRR_TYPE` (line 599) and the gate
  block (lines 611-616) that returns the `drr_rel_required` 400. All
  drafter/admin callers may now set/clear start install on any submittal.
- Update the route docstring to describe the deferred-handoff behavior.
- The rest (event creation, due_date echo) is unchanged.

### 3. Backend route: create the handoff when a Rel is assigned
File: `app/brain/drafting_work_load/routes.py`, `update_submittal_rel`
(starts line 652)

- After `assign_rel_manual(...)` succeeds and before/around the existing
  commit: capture `old_rel = submittal.rel` *before* assignment; after
  assignment, if the submittal has a `start_install`, call
  `DraftingWorkLoadService.sync_pending_start_install(submittal)` so the date
  now hands off under the new Rel.
- **Stale-Rel cleanup on reassignment:** `assign_rel_manual` permits changing
  an existing Rel. If `old_rel` was not None and changed, delete any
  `PendingStartInstall` row keyed by `old_rel` that belongs to this submittal,
  so an orphaned pending row can't wrongly stamp a future release numbered
  `old_rel`. (Rel can't be cleared to None via this route — `assign_rel_manual`
  requires a valid int — so no None case to handle.)

### 4. Frontend: open the cell to all rows
File: `frontend/src/components/TableRow.jsx` (start-install branch, ~594-640)

- Change the gate `canEditStartInstall = canEditDrafterFields &&
  isDraftingReleaseReview && hasRel` to just `canEditDrafterFields` so every
  editable row (any type, with or without a Rel, on both tabs) gets the
  interactive pill.
- Make the modal `jobLabel` tolerate a missing Rel (e.g. `Job 123` with no
  `· Rel n` suffix when `rowRel` is empty).
- Optional but recommended: when there is no Rel, set the pill/modal `title`
  hint to something like "Planning date — transfers to the job log once a Rel
  is assigned" so the deferred-handoff behavior is visible to drafters.
- `StartInstallDwlModal.jsx` and the `handleStartInstallConfirm/Clear`
  handlers need no contract changes (they already POST `submittal_id`).

## Verification

- **Unit/service tests** (`tests/dwl/test_start_install.py` — the existing
  suite that currently asserts the `drr_rel_required` 400):
  - Remove/replace the assertions that expect the gate to reject non-DRR /
    no-Rel submittals; they should now succeed (200, date stored).
  - Add: set start install on a **non-DRR** submittal → date persists, **no**
    `PendingStartInstall` row created.
  - Add: set start install on a **DRR without Rel** → date persists, no pending
    row; then assign a Rel → a `PendingStartInstall` row now exists with the
    stored date and cleared `consumed_*`.
  - Add: **Rel reassignment** with an existing date → pending row moves to the
    new Rel and the old-Rel pending row for that submittal is gone.
  - Keep the existing release-creation handoff tests green (no change to that
    path).
  - Run: `pytest tests/dwl/test_start_install.py` then `pytest`.
- **Manual** (`python run.py` + `cd frontend && npm run dev`): on the DWL,
  confirm the start-install pill is now clickable on a non-DRR row and a
  no-Rel DRR row; set a date and confirm `due_date` updates to the DDD; assign
  a Rel to the DRR row and confirm the date later transfers when that release
  number is pasted into the Job Log.
