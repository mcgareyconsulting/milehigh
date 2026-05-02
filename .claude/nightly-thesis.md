# Nightly Thesis — MHMW Brain

Last updated: 2026-05-02 (second nightly run)

## Direction

**What the Brain does.** MHMW Brain is a Flask + React 19 app that mirrors three external systems (Trello, Procore submittals, OneDrive Excel) into one normalized job log so drafters and PMs can sequence fabrication, paint, and shipping for steel-fab releases. The hot paths are: (1) Trello card webhooks → in-process queue → ThreadPoolExecutor workers writing to `Releases` and `ReleaseEvents`; (2) Procore submittal webhooks → `Submittals`/`SubmittalEvents` with 15s burst dedup and outbound updates back to Procore; (3) APScheduler hourly Excel poll converting OneDrive rows to Trello cards; (4) the `outbox_retry_worker` daemon thread that drains `TrelloOutbox`/`ProcoreOutbox` with exponential backoff. The Job Log frontend reads `Releases` through `app/brain/job_log/routes.py` and applies a per-stage-group `fab_order` ordering scheme (fixed tiers 1–2, dynamic ≥3).

**Where this should head.** Smooth, fast, accurate Brain means: (a) one source of truth for stage→group mapping (`STAGE_TO_GROUP` in `app/api/helpers.py`) — every consumer must derive groups from `stage`, never trust a stale `stage_group` column; (b) the `active_releases_filter()` helper in `app/api/helpers.py` (landed in #169) is the canonical active-release clause — still ~4 remaining hand-rolled `is_active/is_archived` clauses in `routes.py` that should be swept next; (c) the `app/brain/job_log/features/` layout (one folder per bounded behavior) is the right shape — Job Log routes should keep delegating rather than re-inlining; (d) inline `from ... import` inside conditionals (introduced in #175's cascade calls in routes.py and command.py) is a pattern to avoid — prefer top-level imports where there's no circular risk; (e) the Job Log page component is still the next big frontend simplification target — modal markup should move into per-feature components.

## What's working

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

1. **Should `active_releases_filter()` replace the remaining hand-rolled `is_active/is_archived` clauses in `routes.py`?** Four call sites at roughly lines 350–356, 607–614, 2892–2893, 3004–3005 still hand-roll the clause. Semantics vary slightly (some have an archived-toggle path that short-circuits the is_active check). Worth a sweep — need confirmation that the archived path should be unchanged.
2. **Should `geofence_geojson` ever be NULL?** Python fallback iterates all `is_active=True` Projects regardless. If NULL = "not a real project," the fallback should add `is not None`; if it's "uses lat/lng+radius circle," the fallback should fall back further.
3. **Inline imports in cascade calls** — `app/brain/job_log/features/stage/command.py` and two `routes.py` sites import `clear_hard_date_cascade` inside conditionals. Is there a circular import reason for this, or can they move to module-level imports?
