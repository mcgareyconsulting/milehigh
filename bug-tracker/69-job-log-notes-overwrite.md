# #69 — Job Log Notes Overwrite

**Source:** Board item #69 (open / low / Job Log)
**Author:** Daniel — 2026-04-21
**Description:** "We currently overwrite a new note on the Job Log. We want a pop up that displays note history."

---

## Problem

Editing the Notes cell on the Job Log silently overwrites the prior note. Users have no way to see what a note used to say.

## Existing infrastructure (no backend work needed)

- `ReleaseEvents` already records every `update_notes` event with payload `{from, to}`, timestamp, and source/user.
  - Created in `app/brain/job_log/routes.py:1051` via `JobEventService.create(action='update_notes', ...)`.
- `GET /brain/events?job=X&release=Y` already filters events by release (`app/brain/job_log/routes.py:1968`).

So note history is already captured back to launch. This feature is read-only frontend.

## Changes

### 1. New component — `frontend/src/components/NotesHistoryModal.jsx`

Props:
- `job` (number)
- `release` (string)
- `isOpen` (bool)
- `onClose` (fn)

Behavior:
- On open, fetch `/brain/events?job=X&release=Y&limit=200`.
- Client-side filter to `action === 'update_notes'`.
- Skip rows where `payload.from === payload.to` (dedupe no-op events).
- Render reverse-chronological list. Each row shows:
  - Timestamp formatted in Mountain Time
  - Author (`source`, which is already formatted as `"Brain:username"` or `"Trello"` etc.)
  - Current value (`payload.to`) — primary text
  - Previous value (`payload.from`) — small muted "was: …" line
- Empty state: "No prior notes for this release."

### 2. Trigger in `JobsTableRow.jsx` (Notes cell, around `:1107`)

- Add a small clock/history icon, absolute-positioned in the corner of the Notes cell.
- Visible only on row hover (so it doesn't clutter the dense table).
- Click → opens `NotesHistoryModal`. Stop propagation so it doesn't trigger drag or focus the textarea.

### 3. No backend / DB / migration changes

The events feed already has everything we need.

## Design decisions

- **No auto-popup on edit.** The icon is opt-in; auto-popups in dense tables are noisy.
- **Read-only modal.** Editing continues to happen inline in the cell. (See "Out of scope" below for the restore button discussion.)
- **Client-side action filter.** If the events list grows large for a single release, add an `?action=` server filter then; not now.

## Test plan

- [ ] Pick a release with multiple historical note edits in prod (every Notes change since launch is in `release_events`).
- [ ] Open the modal — confirm history renders newest-first with timestamps and authors.
- [ ] Confirm the icon doesn't interfere with the textarea (drag, edit, scroll).
- [ ] Confirm empty state renders for a release with no edits.
- [ ] Confirm consecutive identical entries are deduped.
- [ ] Light + dark mode.

## Out of scope (explicit)

- **Restore-to-prior-note button.** Not in the bug ask. Revisit if requested — would need a separate `update_notes` call (which itself becomes another history entry, so the audit trail stays intact).

## Risks

- Pure additive frontend change; no risk to existing notes write path.
- If `release_events` for a heavily-edited release grows past 200 entries, the `limit=200` cap could truncate. Bump if it ever matters.
