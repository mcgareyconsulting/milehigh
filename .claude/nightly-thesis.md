# Nightly Thesis — MHMW Brain

Last updated: 2026-05-03 (third nightly run)

## Direction

**What the Brain does.** MHMW Brain is a Flask + React 19 app that mirrors three external systems (Trello, Procore submittals, OneDrive Excel) into one normalized job log so drafters and PMs can sequence fabrication, paint, and shipping for steel-fab releases. The hot paths are: (1) Trello card webhooks → in-process queue → ThreadPoolExecutor workers writing to `Releases` and `ReleaseEvents`; (2) Procore submittal webhooks → `Submittals`/`SubmittalEvents` with 15s burst dedup and outbound updates back to Procore; (3) APScheduler hourly Excel poll converting OneDrive rows to Trello cards; (4) the `outbox_retry_worker` daemon thread that drains `TrelloOutbox`/`ProcoreOutbox` with exponential backoff. The Job Log frontend reads `Releases` through `app/brain/job_log/routes.py` and applies a per-stage-group `fab_order` ordering scheme (fixed tiers 1–2, dynamic ≥3).

**Where this should head.** Smooth, fast, accurate Brain means: (a) one source of truth for stage→group mapping (`STAGE_TO_GROUP` in `app/api/helpers.py`) — every consumer must derive groups from `stage`, never trust a stale `stage_group` column; (b) the `active_releases_filter()` helper in `app/api/helpers.py` (landed in #169) is the canonical active-release clause — still ~4 remaining hand-rolled `is_active/is_archived` clauses in `routes.py` that need a sweep, but NULL semantics for `is_archived` differ from the helper (see Open questions); (c) the `app/brain/job_log/features/` layout (one folder per bounded behavior) is the right shape — Job Log routes should keep delegating rather than re-inlining; (d) inline imports inside function bodies imply "I couldn't import this at the top for a reason" — if there's no circular-import justification, promote to module-level (#177, #178 cleared the `clear_hard_date_cascade` cases; #180 cleared `JobEventService`). This pattern should now be fully resolved in routes.py; (e) the Job Log page component is still the next big frontend simplification target — modal markup should move into per-feature components.

## What's working

- #180 — Promote JobEventService to module-level import in routes.py. Seven inline imports → one. Same class as #177/#178.
- #179 — Simplify `sortByStageThenFabOrder` comparator. Remove dead empty if-branch and redundant variable aliases.
- #178 — Break circular import between start_install/command and routes. Redirect `update_trello_card` to its canonical source in `app.trello.api`.
- #177 — Promote `clear_hard_date_cascade` to module-level imports in stage/command.py and routes.py (two sites).
- #175 — Red-date auto-clear cascade. Hard `start_install` date clears when stage=Complete/job_comp=X/invoiced=X. Well-structured: dedicated cascade helper, three trigger sites, full test coverage (12 tests across all trigger paths + idempotency).
- #174 — Paint subset now sorts by fab_order ASC (not last_updated_at) so renumbering a release reorders it inside its stage band correctly.
- #172 — Remove dead `app/brain/job-log/utils.py`. Clean deletion confirmed by grep + test suite.
- #171 — Update CLAUDE.md: fix Projects model, document command pattern and undo.
- #170 — Migrate `Model.query.get()` → `db.session.get()`. 147 → 14 warnings.
- #169 — Extract `active_releases_filter()` helper. First step toward single active-clause source of truth.
- #168 — CLAUDE.md update + first nightly thesis seed.
- #167 — Renumber FABRICATION fab_orders. Baseline shape for new Job Log behaviors.
- #166 — Bug-tracker comment box auto-grows. High-frequency UX win.
- #165 — DWL geofence reads `geofence_geojson` column; drops `geometry`.
- #164 — Paint-department filter sorts by stage priority + `last_updated_at` ascending.

## What didn't work

- #173 (duplicate/closed) — Opened a `.query.get()` migration PR against a branch whose changes were already absorbed by #170. Happened because I branched from a point before #170 landed on main. Fix: always `git fetch origin main` and check `git log origin/main` for overlap before committing a refactor.

## Open questions

1. **Should `active_releases_filter()` replace the remaining hand-rolled `is_active/is_archived` clauses in `routes.py`?** Four call sites (lines ~355+358, ~612+616, ~2885–2886, ~2997–2998) still hand-roll the clause. The semantic difference is real: the hand-rolled versions use `db.or_(Releases.is_archived == False, Releases.is_archived == None)` while the helper uses only `Releases.is_archived == False`. If `is_archived` can be NULL in production data, using the helper would change behavior. Confirmation needed: are there any rows with `is_archived IS NULL`, and should they be treated as non-archived?
2. **Should `geofence_geojson` ever be NULL?** Python fallback iterates all `is_active=True` Projects regardless. If NULL = "not a real project," the fallback should add `is not None`; if it's "uses lat/lng+radius circle," the fallback should fall back further.
