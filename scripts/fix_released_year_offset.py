"""
One-off data fix: correct 22 releases whose `released` date landed one year too late.

These rows came in through the original bulk seed, where a bare `M/D` release date
(e.g. "11/18") was year-defaulted to the *import* year (2026) instead of its true year
(2025). The result is a release date in the future on rows that are already at Install
Start / Install Complete / Ship Complete — you can't install something you haven't
released yet.

Evidence the +1yr diagnosis is right (all four agree):
  - Every affected row is already past install, with job_comp 90%/X and often invoiced.
  - Across the whole table, all 120 rows with `released > start_install` are fixed by
    subtracting exactly one year; none need any other adjustment.
  - `id` is monotonic in `released` (the seed inserted in release-date order), and each
    bad row sits between neighbours dated exactly one year earlier — e.g. id 348 stores
    2026-12-02 while ids 347 and 349 both store 2025-12-02.
  - `release_events` has no `update_released` action at all, and none of these rows has
    a `created` event, so nothing in the app has ever touched `released` since import.

This script writes through the same path as the Job Log row-edit route
(`PATCH /brain/jobs/<job>/<release>`, app/brain/job_log/routes.py): it sets the column
and emits an `updated` ReleaseEvents row so the correction is auditable and undoable,
rather than a raw SQL UPDATE that would leave no trail.

It deliberately does NOT queue a Trello outbox item. `released` is in the outbox's
DESCRIPTION_FIELDS, so the normal edit path would rewrite each card's "**Released:**"
line; that is skipped here by choice. The event is created and closed immediately (the
same thing the route does for a release with no linked card). Consequence: the 22 Trello
cards keep showing the old, wrong release date until something else regenerates their
descriptions.

Scope is a hardcoded (id, job, release, expected_current_value) list, not a
`released >= today` query. A row is skipped unless its stored date still equals the
expected wrong value, which makes the script idempotent (a second run is a no-op) and
stops it from sweeping up releases legitimately dated in the future that are created
between now and when it runs.

NOT covered here: 67 archived rows with the same defect, plus 12 more whose bad date has
already slipped into the past (ids 5, 12, 152, 656 are non-archived). Those are a
separate pass.

Usage:
    .venv/bin/python -m scripts.fix_released_year_offset           # dry-run, prints the diff
    .venv/bin/python -m scripts.fix_released_year_offset --apply   # writes + queues Trello sync
"""

import argparse
import sys
from datetime import date, datetime

from app import create_app
from app.models import Releases, db
from app.services.job_event_service import JobEventService

# (id, job, release, expected current `released`). The corrected value is always
# expected minus one year — computed, never hardcoded, so the two can't drift apart.
TARGETS = [
    (20,  410, "698", date(2026, 8, 12)),
    (22,  410, "697", date(2026, 8, 11)),
    (23,  410, "699", date(2026, 8, 21)),
    (40,  170, "827", date(2026, 10, 8)),
    (261, 450, "900", date(2026, 11, 3)),
    (305, 410, "136", date(2026, 11, 14)),
    (306, 410, "137", date(2026, 11, 14)),
    (307, 410, "138", date(2026, 11, 14)),
    (313, 410, "129", date(2026, 11, 18)),
    (314, 410, "130", date(2026, 11, 18)),
    (315, 410, "131", date(2026, 11, 18)),
    (316, 410, "133", date(2026, 11, 18)),
    (317, 410, "134", date(2026, 11, 18)),
    (318, 410, "135", date(2026, 11, 18)),
    (319, 410, "132", date(2026, 11, 18)),
    (336, 340, "164", date(2026, 11, 26)),
    (350, 340, "147", date(2026, 12, 2)),
    (352, 340, "157", date(2026, 12, 2)),
    (383, 410, "190", date(2026, 12, 10)),
    (390, 410, "126", date(2026, 12, 15)),
    (391, 410, "127", date(2026, 12, 15)),
    (409, 370, "216", date(2026, 12, 18)),
]


def shift_back_one_year(d):
    """Return d with the year decremented. Feb 29 -> Feb 28 (no target hits this)."""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the changes. Without it the script only prints what it would do.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        planned, skipped, missing = [], [], []

        for row_id, job, release, expected in TARGETS:
            rec = db.session.get(Releases, row_id)
            if rec is None:
                missing.append((row_id, job, release, "row not found"))
                continue
            if rec.job != job or rec.release != release:
                missing.append(
                    (row_id, job, release, f"identity moved to {rec.job}-{rec.release}")
                )
                continue
            if rec.released != expected:
                skipped.append((row_id, job, release, rec.released, expected))
                continue
            planned.append((rec, expected, shift_back_one_year(expected)))

        print(f"{'APPLY' if args.apply else 'DRY RUN'}: {len(planned)} of {len(TARGETS)} rows to update\n")
        print(f"  {'id':>4}  {'job-rel':<10} {'job name':<24} {'from':<12} {'to':<12} {'start_install':<13} stage")
        print(f"  {'-'*4}  {'-'*10} {'-'*24} {'-'*12} {'-'*12} {'-'*13} {'-'*18}")
        for rec, old, new in planned:
            print(
                f"  {rec.id:>4}  {f'{rec.job}-{rec.release}':<10} {(rec.job_name or '')[:24]:<24} "
                f"{old.isoformat():<12} {new.isoformat():<12} "
                f"{(rec.start_install.isoformat() if rec.start_install else '—'):<13} {rec.stage or '—'}"
            )

        if skipped:
            print(f"\n  SKIPPED ({len(skipped)}) — stored date no longer matches expected "
                  f"(already fixed, or edited since):")
            for row_id, job, release, actual, expected in skipped:
                print(f"    id {row_id} ({job}-{release}): stored {actual}, expected {expected}")

        if missing:
            print(f"\n  MISSING ({len(missing)}):")
            for row_id, job, release, why in missing:
                print(f"    id {row_id} ({job}-{release}): {why}")

        if not args.apply:
            print("\nDry run — nothing written. Re-run with --apply to commit.")
            return 0

        if not planned:
            print("\nNothing to do.")
            return 0

        no_event = 0
        for rec, old, new in planned:
            rec.released = new
            rec.last_updated_at = datetime.utcnow()
            rec.source_of_update = "System"

            event = JobEventService.create(
                job=rec.job,
                release=rec.release,
                action="updated",
                source="Brain",
                payload={
                    "released": {
                        "old_value": old.isoformat(),
                        "new_value": new.isoformat(),
                    }
                },
            )
            if not event:
                # Dedup collision — the column still gets corrected, there is just
                # no event row for this one.
                no_event += 1
                continue

            # Closed immediately: no Trello outbox item by design, so the event has
            # nothing to wait on.
            JobEventService.close(event.id)

        db.session.commit()
        print(f"\nCommitted {len(planned)} rows. No Trello sync queued (by design); "
              f"cards still show the old date. {no_event} rows got no event (dedup).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
