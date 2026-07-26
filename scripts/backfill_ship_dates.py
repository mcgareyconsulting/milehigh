"""
One-off script: backfill Releases.ship_date for releases that have a hard
start_install date but no ship date yet.

Ship date is a plain hard date that should sit one business day before
start_install (ship = install - 1 biz day), the same estimate the install/ship
modal applies when a user edits either field. This fills that estimate in for
rows that predate the Ship Date feature. It does NOT push to Trello and does NOT
touch comp_eta or scheduling — start_install stays the scheduling driver.

Scope (a row is backfilled only if ALL hold):
 - hard date:   start_install_formulaTF IS False AND start_install IS NOT NULL
                (the canonical "hard date" test, mirrors StartInstallEditor.jsx
                and install_schedule/service.py)
 - not set yet: ship_date IS NULL          (never overwrite a user-set ship date)
 - active:      not archived, not soft-deleted

The ship date's color follows start_install_no_color (there is no separate
ship-date color flag), so a release already in the complete zone renders its
backfilled ship date neutral automatically.

No ReleaseEvents rows are written — this is a one-time bulk data fill, not a
user action; emitting hundreds of update_ship_date events would only spam the
audit stream and churn the dedup table.

Run the column migration first (adds ship_date):
    python migrations/add_ship_date_to_releases.py

Usage:
    .venv/bin/python -m scripts.backfill_ship_dates           # dry-run, prints diff
    .venv/bin/python -m scripts.backfill_ship_dates --apply   # commits changes

Idempotent: re-running only fills rows whose ship_date is still NULL.
"""

import argparse

from app import create_app
from app.models import Releases, db
from app.trello.utils import calculate_business_days_before


def run(apply: bool):
    app = create_app()
    with app.app_context():
        # Hard-dated, active releases that have no ship date yet.
        releases = (
            Releases.query.filter(
                Releases.start_install_formulaTF.is_(False),
                Releases.start_install.isnot(None),
                Releases.ship_date.is_(None),
                Releases.is_archived.isnot(True),
                Releases.is_active.isnot(False),
            )
            .order_by(Releases.job, Releases.release)
            .all()
        )

        updates = 0
        for rec in releases:
            ship = calculate_business_days_before(rec.start_install, 1)
            tag = f"{rec.job}-{rec.release}"
            print(
                f"  ship {tag}: install {rec.start_install} -> ship {ship}"
                f"{' (neutral)' if rec.start_install_no_color else ''}"
            )
            rec.ship_date = ship
            updates += 1

        print(f"\nHard-dated releases needing a ship date: {len(releases)} | updates: {updates}")

        if apply:
            db.session.commit()
            print("Committed.")
        else:
            db.session.rollback()
            print("Dry-run — no changes written. Re-run with --apply to commit.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill ship_date (= start_install - 1 business day) for hard-dated releases."
    )
    parser.add_argument("--apply", action="store_true", help="Commit changes (default is dry-run).")
    args = parser.parse_args()
    run(args.apply)
