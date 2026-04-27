# #68 — Undo on Event Tab

**Source:** Board item #68 (open / normal / General)
**Author:** Daniel — 2026-04-21
**Description:** "Add Undo/Rollback button on Event Tab for accidental changes."

---

## Scope

Confirmed with Daniel 2026-04-25:

- Undo reverts **the targeted row only** for the targeted field.
- No cascade rollback. Downstream effects of the original change (scheduling recalcs, other rows updated by the same stash batch, etc.) are not unwound.
- Staleness UX: client-side eligibility check so the button is correctly enabled/disabled before the user clicks (friendlier than 409 surprises).
- Stash-apply batch undo is out of scope for this item.

## Approach

Per-event Undo button on the Events page. On click, the system applies `payload.from` as a normal update through the existing pipeline. The undo itself produces a new event (with `from` / `to` swapped) — so undos are themselves reversible without a special redo mechanism.

## Existing infrastructure

- All four user-edit actions persist `payload.from`: `update_stage`, `update_notes`, `update_fab_order`, `update_start_install`. Cleanly reversible.
- Each action has an existing update path (route or command) that runs the full event / outbox / cascade pipeline.
- `Events.jsx` is already admin-only.

## Changes

### 1. Undo eligibility — backend rules

**Whitelist actions:**
- `update_stage`
- `update_notes`
- `update_fab_order`
- `update_start_install`
- `update_assignments` (only after Phase 1 of #29 lands)

**Always blocked:**
- `email_received` (read-only event type)
- Stash-apply batch events (would dismantle the batch — separate feature, see "Out of scope")
- No-op events where `payload.from === payload.to`

**Staleness check:** Only allow undo when the release's current value for that field matches `payload.to`. If it doesn't, a later edit has superseded the target event and undoing would silently overwrite that later change. Return `409` with: `"Stale — current value is X, expected Y. Undo would overwrite a later change."`

### 2. New endpoint — `POST /brain/events/<event_id>/undo`

- Admin only.
- Loads `ReleaseEvents` row.
- Validates: action in whitelist, payload well-formed, not a no-op, passes staleness check.
- Routes to the existing command / route for that action, passing `payload.from`:
  - `update_stage` → existing stage update path
  - `update_notes` → existing notes update path
  - `update_fab_order` → `UpdateFabOrderCommand`
  - `update_start_install` → existing start-install update path
- Sets `source='Brain:undo:{username}'` so the audit trail makes intent obvious.
- The downstream call creates its own `ReleaseEvents` row normally — the undo is itself an event.

### 3. Frontend — Events page

- Per-row Undo button on `Events.jsx`.
- **Eligibility resolved client-side at fetch time.** Join the current release value into each event row so the button can be correctly enabled or disabled before any click. Disabled state shows a tooltip explaining why: "Not undoable", "Already in this state", or "Newer change exists — undo that first".
- Click → confirmation dialog showing the diff: e.g. *"Set Stage on #1234-A from `Paint` back to `Welded QC`?"*
- POST to the new endpoint. On success, refresh the events feed.
- On unexpected `409` (rare race condition): toast `"Newer changes exist — refresh and try again."`

### 4. Audit clarity

The undo creates a normal-looking `update_*` event with `source='Brain:undo:{username}'`. In the events table, render that source with a subtle badge (`↶ undo`) so the trail tells the story at a glance.

## Limitation surfaced in the confirm dialog

Single-row, single-field. Worth a one-line note in the confirm dialog so users don't expect cascade rollback:

> *Undo reverts this row only. Cascaded changes (scheduling, other rows in the same stash session) are not rolled back.*

## Test plan

- [ ] Click Undo on a stage event → release reverts; new event row appears with `source='Brain:undo:...'`.
- [ ] Notes / fab_order / start_install undo each work end-to-end.
- [ ] Stale event (release was edited again after the target event) → button disabled with tooltip; direct API hit returns 409.
- [ ] Undo the undo → original `to` value restored. Trail shows ↶ → ↶ chain.
- [ ] Trello outbox fires correctly for stage / notes / fab_order undos (same pipeline as a normal edit).
- [ ] Cascade (scheduling recalc) fires once on fab_order / stage undo.
- [ ] Non-admin can't see the button; direct API hit returns 403.
- [ ] Email events show no Undo button.
- [ ] Stash-apply batch events show no Undo button.

## Out of scope

- **Stash-apply rollback.** Separate "Roll back stash session" feature later — distinct unit of work, treat as its own bug.
- **Cascade rollback.** Downstream rows changed by the original action stay as-is.
- **Bulk undo.** Selecting multiple events and undoing them as a batch.

## Risks

- **State mismatch.** Two admins editing the same release at the same time can produce 409s. Acceptable — friendly toast + refresh covers it.
- **Eligibility precompute cost.** Joining current values onto every event row at fetch time adds a small backend join. Fine at current event volume; revisit if the events feed grows large.
