"""
One-time script to set fab_order=80.555 for Released releases with NULL fab_order.

Usage:
    python -m app.brain.job_log.features.fab_order.fix_null_fab_orders              # dry-run (default)
    python -m app.brain.job_log.features.fab_order.fix_null_fab_orders --commit     # apply changes
"""

import argparse

from app import create_app
from app.models import Releases, db
from app.api.helpers import DEFAULT_FAB_ORDER, _get_all_variants_for_stages


def fix_null_fab_orders(dry_run=True):
    released_variants = _get_all_variants_for_stages(["Released"])

    from sqlalchemy import or_, func
    # Match stage='Released' or stage is NULL, AND fab_order is NULL or 0, active only
    releases = Releases.query.filter(
        or_(
            Releases.stage.in_(released_variants),
            func.lower(Releases.stage) == 'released',
            Releases.stage.is_(None),              # newly created, no stage set
        ),
        or_(
            Releases.fab_order.is_(None),          # SQL NULL
            Releases.fab_order == 0,                # zero (falsy float)
        ),
        Releases.is_archived != True,              # noqa: E712
    ).all()

    print(f"\nFound {len(releases)} releases with NULL fab_order\n")
    for r in releases:
        print(f"  {r.job}-{r.release}  stage={r.stage!r}  fab_order={r.fab_order!r}")

    if not releases:
        print("Nothing to fix.")
        return

    if dry_run:
        print(f"\nWould set fab_order={DEFAULT_FAB_ORDER}, stage='Released', stage_group='FABRICATION'")
        print("DRY RUN -- no changes made. Use --commit to apply.")
    else:
        for r in releases:
            r.fab_order = DEFAULT_FAB_ORDER
            if r.stage is None:
                r.stage = 'Released'
                r.stage_group = 'FABRICATION'
        db.session.commit()
        print(f"\nUpdated {len(releases)} records: fab_order={DEFAULT_FAB_ORDER}, stage defaults applied")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix NULL fab_orders for Released releases")
    parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        fix_null_fab_orders(dry_run=not args.commit)
