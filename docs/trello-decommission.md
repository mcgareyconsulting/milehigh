# Trello decommission roadmap

The internal PM board (`frontend/src/pages/PMBoard.jsx` + the Job Log) now does
everything Trello does for us and more: 18-stage drag-drop, inline editing,
scheduling overlay, a Gantt view, and (as of the `feature/improved-pm-board`
work) attachments — drawings and photos — surfaced directly on the card.

This document is the **ordered plan** for retiring Trello. It is a roadmap, not
an instruction to act now. Trello is currently still **both** a data source
(webhook list-moves → stage) and a sink (card moves, fab-order custom field,
due dates, mirror-card moves, Excel→card creation), and stage advancement is
still mixed across users. Do not delete anything in `app/trello/` until the
phases below are worked through in order.

## Current coupling (what has to be unwound)

Inbound (Trello → app DB), in `app/trello/sync.py`:
- card name / description / due date → `Releases.trello_*` fields
- list move → `stage` (rank-gated via `app/trello/list_mapper.py`)

Outbound (app DB → Trello):
- stage change → `move_card` outbox action (`features/stage/command.py`)
- fab order → `update_fab_order` custom-field outbox action
- hard `start_install` → main-card due date (`features/start_install/command.py`)
- installer assignment → mirror-card move (`features/start_install/assign_installer.py`)
- Excel row → new card (`app/trello/api.py::create_trello_card_from_excel_data`)

Shared infrastructure that is **NOT** Trello-specific and must survive:
`OutboxService`, `JobEventService`, `SyncLockManager` (`app/sync_lock.py`),
`ReleaseEvents`, and the `source_of_update` column — all are also used by the
Procore integration.

## Phases (in dependency order)

### Phase 1 — Make the board authoritative for stage
Confirm operationally that all PMs and shop staff advance stage on the internal
board, not by dragging Trello cards. Then gate inbound list→stage application in
`app/trello/sync.py` behind a flag (default off once verified) so a stray Trello
move can no longer overwrite the DB stage. Card metadata sync (name/desc/due)
can remain until Phase 2.
- **Risk:** a user still working in Trello silently stops affecting the board.
  Mitigate by announcing the cutover and watching `source_of_update='Trello'`
  event volume drop to ~zero before flipping the flag.

### Phase 2 — Stop outbound writes
Flag off the outbox actions: `move_card`, `update_fab_order`, the start-install
due-date push, and the mirror-card move. No data loss — these only update
Trello. Leave the outbox plumbing in place (Procore uses it).
- **Risk:** none to app data; Trello simply goes stale. Verify by confirming no
  new `TrelloOutbox` rows are created after the flag flip.

### Phase 3 — Replace card creation
Once releases originate internally and/or from Procore (not from the Excel →
Trello card path), retire `create_trello_card_from_excel_data` and the OneDrive
poller's card-creation step. Excel ingestion that feeds the DB stays; only the
Trello-card side is removed.

### Phase 4 — Decouple install data fully
Drop the `InstallerTeam.trello_list_id` reliance and the mirror-card concept
once mirrors are no longer used. `Releases.num_guys` is already the source of
truth for `comp_eta`; `InstallerTeam` is already loosely coupled (no FK, never
read by scheduling), so this is mostly deleting the mirror-move code path.

### Phase 5 — Delete pure-Trello code
With inbound and outbound dark, remove, roughly in this order:
- `app/trello/scripts/`, `scanner.py`, `context.py`, `logging.py`,
  `operations.py`, `utils.py` (move `add_business_days` / business-day helpers
  somewhere neutral first — scheduling imports them)
- `app/trello/sync.py`, `api.py`, `card_creation.py`, `list_mapper.py`
- unregister `trello_bp` in `app/__init__.py`; drop the webhook route
- remove Trello config keys (`app/config.py`): `TRELLO_*`, `FAB_ORDER_FIELD_ID`,
  list-id keys, `INSTALLER_TEAMS` (once teams live in `installer_teams`)
- frontend: remove the "Open in Trello" buttons (`PMBoardCardModal.jsx`,
  `JobDetailsModal.jsx`) and Trello badges in `EventsList.jsx` / `History.jsx`
- the `Releases.trello_*` columns can be dropped last, via migration, once
  nothing reads them.

### Phase 6 — Confirm shared infra is untouched
Verify `OutboxService`, `JobEventService`, `SyncLockManager`, `ReleaseEvents`,
and `source_of_update` still function for Procore after the Trello code is gone.

## Notes
- `app/trello/utils.py::add_business_days` is imported by the scheduling
  calculator — relocate it (e.g. to a `scheduling/` util) before deleting the
  Trello package, or Phase 5 will break `comp_eta`.
- Each phase is independently reversible by flipping its flag back on until the
  corresponding code is actually deleted in Phase 5.
