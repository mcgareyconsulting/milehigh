"""
Drop a submittal and all related rows from the production database.

Usage:
  python scripts/drop_submittal.py                 # dry run (default)
  python scripts/drop_submittal.py --execute       # actually delete

Tables affected (by submittal_id string match):
  - submittals
  - submittal_events
  - procore_outbox
  - notifications (also cascades via FK, deleted explicitly for counting)
"""
import argparse
import os
import sys

import psycopg2
import psycopg2.extras

try:  # allow both `python -m scripts.drop_submittal` and direct execution
    from scripts._db_urls import mask, prod_url
except ImportError:  # pragma: no cover - path fixup for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts._db_urls import mask, prod_url

TARGET_SUBMITTAL_ID = "69656624"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Actually perform deletion (default is dry run)")
    parser.add_argument("--submittal-id", default=TARGET_SUBMITTAL_ID)
    args = parser.parse_args()

    sid = args.submittal_id
    mode = "EXECUTE" if args.execute else "DRY RUN"
    url = prod_url()
    print(f"=== {mode} — dropping submittal_id={sid} from PRODUCTION ===")
    print(f"target: {mask(url)}\n")

    conn = psycopg2.connect(url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Preview main submittal row
            cur.execute(
                'SELECT id, submittal_id, project_number, project_name, title, status, ball_in_court, submittal_drafting_status, created_at, last_updated '
                'FROM submittals WHERE submittal_id = %s',
                (sid,),
            )
            submittal_rows = cur.fetchall()
            print(f"[submittals]         matching rows: {len(submittal_rows)}")
            for row in submittal_rows:
                print(f"  id={row['id']}  project={row['project_number']} ({row['project_name']})")
                print(f"    title: {row['title']}")
                print(f"    status={row['status']}  bic={row['ball_in_court']}  dwl_status={row['submittal_drafting_status']}")
                print(f"    created_at={row['created_at']}  last_updated={row['last_updated']}")

            # Count dependent rows
            cur.execute('SELECT COUNT(*) AS c FROM submittal_events WHERE submittal_id = %s', (sid,))
            events_count = cur.fetchone()['c']
            print(f"[submittal_events]   matching rows: {events_count}")

            cur.execute('SELECT COUNT(*) AS c FROM procore_outbox WHERE submittal_id = %s', (sid,))
            outbox_count = cur.fetchone()['c']
            print(f"[procore_outbox]     matching rows: {outbox_count}")

            cur.execute('SELECT COUNT(*) AS c FROM notifications WHERE submittal_id = %s', (sid,))
            notif_count = cur.fetchone()['c']
            print(f"[notifications]      matching rows: {notif_count}  (would cascade via FK)")

        if not args.execute:
            print("\nDry run complete. No changes made. Re-run with --execute to delete.")
            return

        if not submittal_rows and events_count == 0 and outbox_count == 0 and notif_count == 0:
            print("\nNothing to delete. Aborting.")
            return

        # Perform deletion inside a single transaction
        with conn.cursor() as cur:
            cur.execute('DELETE FROM notifications WHERE submittal_id = %s', (sid,))
            notif_deleted = cur.rowcount
            cur.execute('DELETE FROM procore_outbox WHERE submittal_id = %s', (sid,))
            outbox_deleted = cur.rowcount
            cur.execute('DELETE FROM submittal_events WHERE submittal_id = %s', (sid,))
            events_deleted = cur.rowcount
            cur.execute('DELETE FROM submittals WHERE submittal_id = %s', (sid,))
            submittal_deleted = cur.rowcount

        conn.commit()
        print(
            f"\nDeleted: submittals={submittal_deleted}, submittal_events={events_deleted}, "
            f"procore_outbox={outbox_deleted}, notifications={notif_deleted}"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
