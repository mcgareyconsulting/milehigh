"""
Update Releases.pm for a single job/release row in production.

Usage:
  python scripts/fix_release_pm.py                                 # dry run, prod (default)
  python scripts/fix_release_pm.py --execute                       # apply, prod
  python scripts/fix_release_pm.py --env sandbox                   # dry run, sandbox
  python scripts/fix_release_pm.py --env sandbox --execute         # apply, sandbox
"""
import argparse
import os
import sys

import psycopg2
import psycopg2.extras

try:  # allow both `python -m scripts.fix_release_pm` and direct execution
    from scripts._db_urls import mask, prod_url, sandbox_url
except ImportError:  # pragma: no cover - path fixup for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts._db_urls import mask, prod_url, sandbox_url

TARGET_JOB = 999
TARGET_RELEASE = "598"
EXPECTED_PM = "BO"
NEW_PM = "WO"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Actually perform update (default is dry run)")
    parser.add_argument("--env", choices=["prod", "sandbox"], default="prod", help="Target database (default: prod)")
    args = parser.parse_args()

    db_url = prod_url() if args.env == "prod" else sandbox_url()
    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"=== {mode} [{args.env.upper()}] — updating releases.pm for job={TARGET_JOB} release={TARGET_RELEASE} ===")
    print(f"target: {mask(db_url)}\n")

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                'SELECT id, job, release, job_name, pm FROM releases WHERE job = %s AND release = %s',
                (TARGET_JOB, TARGET_RELEASE),
            )
            rows = cur.fetchall()
            print(f"matching rows: {len(rows)}")
            for row in rows:
                print(f"  id={row['id']}  job={row['job']}-{row['release']}  name={row['job_name']!r}  pm={row['pm']!r}")

            if len(rows) != 1:
                print(f"\nExpected exactly 1 row, found {len(rows)}. Aborting.")
                return

            current_pm = rows[0]["pm"]
            if current_pm != EXPECTED_PM:
                print(f"\nCurrent pm={current_pm!r} does not match expected {EXPECTED_PM!r}. Aborting to be safe.")
                return

        if not args.execute:
            print(f"\nDry run complete. Would set pm={NEW_PM!r}. Re-run with --execute to apply.")
            return

        with conn.cursor() as cur:
            cur.execute(
                'UPDATE releases SET pm = %s WHERE job = %s AND release = %s AND pm = %s',
                (NEW_PM, TARGET_JOB, TARGET_RELEASE, EXPECTED_PM),
            )
            updated = cur.rowcount

        conn.commit()
        print(f"\nUpdated rows: {updated}  (pm: {EXPECTED_PM!r} -> {NEW_PM!r})")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
