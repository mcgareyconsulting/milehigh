# Nightly Thesis — MHMW Brain

Last updated: 2026-04-30 (first nightly run)

## Direction

**What the Brain does.** MHMW Brain is a Flask + React 19 app that mirrors three external systems (Trello, Procore submittals, OneDrive Excel) into one normalized job log so drafters and PMs can sequence fabrication, paint, and shipping for steel-fab releases. The hot paths are: (1) Trello card webhooks → in-process queue → ThreadPoolExecutor workers writing to `Releases` and `ReleaseEvents`; (2) Procore submittal webhooks → `Submittals`/`SubmittalEvents` with 15s burst dedup and outbound updates back to Procore; (3) APScheduler hourly Excel poll converting OneDrive rows to Trello cards; (4) the `outbox_retry_worker` daemon thread that drains `TrelloOutbox`/`ProcoreOutbox` with exponential backoff. The Job Log frontend reads `Releases` through `app/brain/job_log/routes.py` and applies a per-stage-group `fab_order` ordering scheme (fixed tiers 1–2, dynamic ≥3).

**Where this should head.** Smooth, fast, accurate Brain means: (a) one source of truth for stage→group mapping (`STAGE_TO_GROUP` in `app/api/helpers.py`) — every consumer must derive groups from `stage`, never trust a stale `stage_group` column; (b) the duplicated `is_active`/`is_archived` filter that recurs across at least four call sites should collapse into one helper so a future change in semantics doesn't drift; (c) the new `app/brain/job_log/features/` layout (one folder per bounded behavior) is the right shape — Job Log routes should keep delegating rather than re-inlining; (d) the Job Log page component (1620 lines) is the next big simplification target — modal markup should move into per-feature components.

## What's working

- #167 — Renumber FABRICATION fab_orders. New admin button + dry-run preview + idempotent compress-to-3..N. Good shape: dedicated feature folder, full test file, sentinel-based tie handling. Baseline of how new Job Log behaviors should land.
- #166 — Bug-tracker comment box now multiline + auto-grows. Tiny change, high-frequency improvement.
- #165 — DWL "is this point inside a project?" lookup now reads `geofence_geojson` instead of the old `geometry` column. Includes migration to drop `geometry` and a Python-fallback test for the SQLite path.
- #164 — Improved paint-department filter sort uses stage priority + `last_updated_at` ascending so the oldest waiting items surface first across Ready-to-Ship and Paint subsets.

## What didn't work

(First nightly run — no rejected/reverted moves to record yet.)

## Open questions

1. **Should `geofence_geojson` ever be NULL?** PR #165 added an `IS NOT NULL` guard to the PostGIS query but the Python fallback iterates all `is_active=True` Projects regardless. If NULL is "not a real project yet," the fallback could match that with an `is not None` check; if it's "uses lat/lng+radius circle," the fallback should fall back further. Need a one-line product call.
2. **Should `_normalize_stage`/`_get_all_variants_for_stages` be the only path into stage filtering?** `app/brain/job_log/routes.py` still hand-rolls `Releases.stage.in_(...)` lists in places where `_get_all_variants_for_stages` would handle the spelling drift. Worth a sweep, but only after I confirm nobody is intentionally filtering one variant.
3. **`Job` (legacy) vs `Releases`** — is the `Job` model dead enough to remove? It's still referenced in `app/trello/scripts/trello_cleanup.py` and `app/models.py` keeps the table. If yes, that's a meaningful simplification; if no, the docstring should be louder.
