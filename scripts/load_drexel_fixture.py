"""Land a saved supplier order .eml as a RawSourceRecord and ingest it.

Lets you test the material-order pipeline end-to-end (raw record -> parser ->
MaterialOrder -> release modal) without the live Graph poll. Defaults to the
580-659 Drexel decking fixture bundled in tests/.

Usage:
    python scripts/load_drexel_fixture.py
    python scripts/load_drexel_fixture.py --eml /path/to/order.eml
"""
import argparse
import hashlib
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

DEFAULT_EML = os.path.join(
    ROOT_DIR, "tests", "material_orders", "fixtures", "drexel_580-659_decking_order.eml"
)


def main(eml_path):
    from app import create_app
    from app.models import RawSourceRecord, Releases, db
    from app.brain.material_orders.eml_adapter import eml_to_payload
    from app.brain.material_orders import service

    app = create_app()
    with app.app_context():
        payload = eml_to_payload(eml_path)
        external_id = payload["external_id"]
        content_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        record = RawSourceRecord.query.filter_by(
            source="m365_mail", external_id=external_id
        ).first()
        if record is None:
            record = RawSourceRecord(
                source="m365_mail",
                record_type="email",
                source_account="bb@mhmw.com",
                external_id=external_id,
                content_hash=content_hash,
                payload=payload,
                external_pointer={"mailbox": "bb@mhmw.com", "fixture": eml_path},
            )
            db.session.add(record)
            db.session.commit()
            print(f"✓ Landed RawSourceRecord id={record.id} ({payload['subject']!r})")
        else:
            print(f"• RawSourceRecord already present id={record.id}")

        orders = service.ingest_record(record)
        if not orders:
            print("✗ No order lines parsed from this email.")
            return 1

        print(f"✓ {len(orders)} material order line(s):")
        for o in orders:
            print(
                f"    job {o.job}-{o.release} | {o.supplier} | PO {o.po_number} | "
                f"qty {o.quantity:g} {o.description} | {o.status}"
            )

        # Is there a matching release to tag?
        first = orders[0]
        rel = Releases.query.filter_by(job=first.job, release=first.release).first()
        if rel:
            print(f"✓ Linked release exists: {rel.job}-{rel.release} {rel.job_name!r}")
        else:
            print(
                f"⚠ No releases row for {first.job}-{first.release} yet — the order is "
                "still stored and will show on that release's modal once it exists."
            )
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load a supplier order .eml and ingest it.")
    parser.add_argument("--eml", default=DEFAULT_EML, help="Path to the .eml file.")
    args = parser.parse_args()
    sys.exit(main(args.eml))
