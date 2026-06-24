"""
One-off backfill: populate ordered_by / ordered_by_email / ordered_at on existing
material_orders rows by re-parsing their source emails.

Existing rows were ingested before the parser learned to read the innermost
forwarded "From:" block, so they hold the forwarder + forward time instead of the
real orderer + placement date. This re-runs parse_order_email() on each row's linked
RawSourceRecord payload and updates the three fields when newly parsed values are
present. Idempotent — safe to re-run.

Run the schema migration first:
    python migrations/add_orderer_to_material_orders.py

Usage:
    .venv/bin/python -m scripts.backfill_material_order_orderers           # dry-run, prints planned changes
    .venv/bin/python -m scripts.backfill_material_order_orderers --apply   # writes updates
"""

import argparse
import sys

from app import create_app
from app.models import MaterialOrder, RawSourceRecord, db
from app.brain.material_orders.parser import parse_order_email


def backfill(apply: bool) -> int:
    """Update orderer/date on existing rows. Returns the number of rows changed."""
    rows = (
        MaterialOrder.query
        .filter(MaterialOrder.source_record_id.isnot(None))
        .order_by(MaterialOrder.id)
        .all()
    )
    changed = 0
    for o in rows:
        rec = RawSourceRecord.query.filter_by(id=o.source_record_id).first()
        if rec is None:
            print(f"  ! order {o.id}: source_record {o.source_record_id} missing, skipping")
            continue
        parsed = parse_order_email(rec.payload or {})
        if not parsed:
            print(f"  ! order {o.id}: source no longer parses as an order, skipping")
            continue

        updates = {}
        # Only overwrite with a freshly parsed, non-null value.
        if parsed.get("ordered_by") and parsed["ordered_by"] != o.ordered_by:
            updates["ordered_by"] = parsed["ordered_by"]
        if parsed.get("ordered_by_email") and parsed["ordered_by_email"] != o.ordered_by_email:
            updates["ordered_by_email"] = parsed["ordered_by_email"]
        if parsed.get("ordered_at") and parsed["ordered_at"] != o.ordered_at:
            updates["ordered_at"] = parsed["ordered_at"]

        if not updates:
            continue

        changed += 1
        desc = ", ".join(f"{k}: {getattr(o, k)!r} -> {v!r}" for k, v in updates.items())
        print(f"  order {o.id} (PO {o.po_number}): {desc}")
        if apply:
            for k, v in updates.items():
                setattr(o, k, v)

    if apply and changed:
        db.session.commit()
        print(f"\n✓ Applied updates to {changed} row(s).")
    elif changed:
        print(f"\n(dry-run) {changed} row(s) would change. Re-run with --apply to write.")
    else:
        print("\nNothing to backfill — all rows already current.")
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill orderer/date on existing material_orders rows from their source emails."
    )
    parser.add_argument("--apply", action="store_true", help="Write updates (default is dry-run).")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        backfill(args.apply)
    sys.exit(0)
