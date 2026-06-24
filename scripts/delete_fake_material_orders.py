"""
One-off cleanup: delete material_orders for a given PO/release (e.g. fake test data).

Removes the MaterialOrder rows AND — unless --keep-source — the lake
RawSourceRecord(s) they were parsed from, once no other order still references them.
Deleting the source record matters: the BB mailbox poll calls ingest_unprocessed()
every 15 min, which re-parses any lake email that has no material order yet, so a
source record left behind would RE-CREATE the orders on the next poll.

Scoped by --po or --release so it can't touch anything you didn't name. Dry-run by
default; pass --apply to actually delete.

Usage:
    .venv/bin/python -m scripts.delete_fake_material_orders --po 170-181            # dry-run
    .venv/bin/python -m scripts.delete_fake_material_orders --po 170-181 --apply    # delete orders + source email
    .venv/bin/python -m scripts.delete_fake_material_orders --po 170-181 --apply --keep-source
"""

import argparse
import sys

from app import create_app
from app.models import MaterialOrder, RawSourceRecord, db


def cleanup(po=None, release=None, apply=False, keep_source=False) -> int:
    if not po and not release:
        print("✗ Refusing to run without a target: pass --po or --release.")
        return 1

    q = MaterialOrder.query
    if po:
        q = q.filter(MaterialOrder.po_number == po)
    if release:
        q = q.filter(MaterialOrder.release == str(release))
    orders = q.order_by(MaterialOrder.id).all()

    if not orders:
        print(f"Nothing to delete — no material_orders match po={po!r} release={release!r}.")
        return 0

    print(f"Material orders to delete (po={po!r} release={release!r}):")
    src_ids = set()
    for o in orders:
        print(f"  order id={o.id} job={o.job} release={o.release} po={o.po_number!r} "
              f"line={o.line_index} desc={o.description!r} src_rec_id={o.source_record_id}")
        if o.source_record_id is not None:
            src_ids.add(o.source_record_id)

    # A source record is safe to drop only if every order referencing it is in this
    # delete set (otherwise we'd orphan a real order or strip a shared email).
    deletable_src = set()
    if not keep_source:
        delete_ids = {o.id for o in orders}
        for sid in src_ids:
            referencing = {r.id for r in MaterialOrder.query.filter_by(source_record_id=sid).all()}
            if referencing <= delete_ids:
                deletable_src.add(sid)
            else:
                print(f"  ! source record {sid} also feeds orders {referencing - delete_ids} "
                      f"— keeping it.")

    if deletable_src:
        print("Source lake records to delete (prevents re-ingestion):")
        for sid in sorted(deletable_src):
            r = RawSourceRecord.query.filter_by(id=sid).first()
            subj = (r.payload or {}).get("subject") if r else None
            print(f"  raw_source_record id={sid} subject={subj!r}")
    elif keep_source:
        print("(--keep-source) leaving lake records in place — orders may re-ingest on the "
              "next BB mail poll.")

    if not apply:
        print(f"\n(dry-run) Would delete {len(orders)} order(s) and {len(deletable_src)} "
              f"source record(s). Re-run with --apply to delete.")
        return 0

    for o in orders:
        db.session.delete(o)
    for sid in deletable_src:
        r = RawSourceRecord.query.filter_by(id=sid).first()
        if r:
            db.session.delete(r)
    db.session.commit()
    print(f"\n✓ Deleted {len(orders)} order(s) and {len(deletable_src)} source record(s).")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete material_orders (and their orphaned lake source records) by PO/release."
    )
    parser.add_argument("--po", help="PO number to target, e.g. 170-181")
    parser.add_argument("--release", help="Release value to target, e.g. 181")
    parser.add_argument("--apply", action="store_true", help="Actually delete (default is dry-run).")
    parser.add_argument("--keep-source", action="store_true",
                        help="Keep the lake RawSourceRecord(s) (orders may re-ingest on next poll).")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        code = cleanup(po=args.po, release=args.release, apply=args.apply, keep_source=args.keep_source)
    sys.exit(code)
