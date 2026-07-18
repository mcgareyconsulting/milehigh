"""Re-scan already-landed lake emails after adding a new deterministic matcher.

`ingest_unprocessed()` only scans records whose `material_order_scanned_at` is NULL,
so an email that landed BEFORE a supplier matcher existed was stamped 'scanned' and is
never retried on redeploy. This one-off clears that marker for the matching records and
re-runs them through the CURRENT extractors — the way to backfill orders we can now
parse but couldn't when the mail first arrived (e.g. AZZ galvanizing).

Targeted on purpose: pass `--match <substr>` (matched against the record's payload, so
'azz.com' finds the AZZ notifications) or `--external-id <graph id>`. It will not touch
records that don't match, so it can't accidentally re-send unrelated mail to the LLM.

Dry-run by default — prints the records that WOULD be re-scanned (also serves as a
"did this email even land in bb@?" check). Pass --apply to actually re-scan.

Usage:
    python scripts/rescan_material_orders.py --match azz.com
    python scripts/rescan_material_orders.py --match azz.com --apply
    python scripts/rescan_material_orders.py --external-id <graph-message-id> --apply
"""
import argparse
import json
import os
import sys
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

EMAIL_RECORD_TYPE = "email"


def _matches(record, match, external_id):
    if external_id:
        return record.external_id == external_id
    haystack = json.dumps(record.payload or {}, default=str).lower()
    return match.lower() in haystack


def main(match, external_id, apply):
    from app import create_app
    from app.models import RawSourceRecord, db
    from app.brain.material_orders import service

    app = create_app()
    with app.app_context():
        # Only the already-scanned records are candidates — a NULL-marker record is
        # already in the poll's queue and needs no reset.
        q = (
            RawSourceRecord.query
            .filter_by(record_type=EMAIL_RECORD_TYPE)
            .filter(RawSourceRecord.material_order_scanned_at.isnot(None))
            .order_by(RawSourceRecord.id.desc())
        )
        candidates = [r for r in q if _matches(r, match, external_id)]

        if not candidates:
            print("No already-scanned email records match — nothing to re-scan.")
            print("(If you expected the AZZ email here, it likely never landed in "
                  "bb@mhmw.com — forward it there and the new code scans it fresh.)")
            return 0

        print(f"{len(candidates)} matching record(s):")
        for r in candidates:
            subj = (r.payload or {}).get("subject")
            print(f"  id={r.id}  scanned_at={r.material_order_scanned_at}  {subj!r}")

        if not apply:
            print("\nDry run — re-run with --apply to clear the marker and re-scan.")
            return 0

        created = 0
        for r in candidates:
            r.material_order_scanned_at = None          # clear so the extractor runs
            orders = service.ingest_record(r)
            r.material_order_scanned_at = datetime.utcnow()  # re-stamp (attempted once)
            created += len(orders)
            for o in orders:
                jr = f"{o.job}-{o.release}" if o.job is not None else "(release-less)"
                print(f"  ✓ id={r.id} → {o.supplier} | {jr} | {o.order_kind} | "
                      f"{o.description} | {o.shipping_status or o.status}")
        db.session.commit()
        print(f"\nDone. {created} material order line(s) created/updated.")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Re-scan landed lake emails with the current matchers.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--match", help="Substring to find in the record payload (e.g. 'azz.com').")
    g.add_argument("--external-id", help="Exact Graph message id of a single record.")
    ap.add_argument("--apply", action="store_true", help="Clear the marker and re-scan (default: dry run).")
    args = ap.parse_args()
    sys.exit(main(args.match, args.external_id, args.apply))
