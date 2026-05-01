# Nightly Thesis

## Direction

The MHMW Brain is the coordination layer between three external systems (Trello, Procore, OneDrive/Excel) and an internal job log. Its hot paths are: (1) inbound Trello webhook → stage/fab_order update → outbox → Trello sync; (2) inbound Procore submittal webhook → SubmittalEvents write; (3) DWL location lookup for on-site filtering. "Smooth" means webhook events never drop and outbox retries converge. "Efficient" means the scheduling recalc (`recalculate_all_jobs_scheduling`) runs as few times as possible per user action — the `defer_cascade=True` pattern on commands exists for this reason. "Accurate" means the event audit trail is complete and the dedup logic prevents phantom double-updates.

**Architectural direction:**
- The command-pattern feature modules (`app/brain/job_log/features/*/command.py`) are the right shape for mutable field operations. Each command is self-contained: DB write + event + outbox + cascade. Keep new mutable-field features in this pattern.
- SQLAlchemy 2.0 compliance: migrate away from the legacy `.query.get()` API toward `db.session.get()`. The codebase has 5 remaining sites; each deprecation warning in tests is noise that masks real failures.
- Dead code should be removed promptly. `app/brain/job-log/utils.py` (hyphen directory, `imported_by: []`) is a clear example — it's been superseded by `app/brain/job_log/utils.py` and left as a ghost.
- CLAUDE.md must accurately reflect models. The `Projects` / `ProjectManager` models were mislabeled as `Jobs` / `job_sites` — future agents using that stale info would generate wrong queries.

## What's working

- First night, no prior PRs to track.

## What didn't work

- First night, no prior failures to track.

## Open questions

- The `renumber_fabrication_fab_orders` feature uses `STAGE_TO_GROUP` to derive FABRICATION membership at runtime rather than trusting the `stage_group` column (which can be stale). Is there a plan to backfill/enforce `stage_group` so both sources stay in sync, or is the runtime derivation intentionally the source of truth?
