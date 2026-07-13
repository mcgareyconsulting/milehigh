"""Copy ONE release (by job + release) from production into sandbox.

A scoped version of copy_releases_to_sandbox.py for seeding a single job into sandbox
for testing (e.g. 590-674 for the BB PDF-review work). Reuses that script's connection
strings and column list so credentials live in one place. Upserts by the (job, release)
unique constraint — safe to re-run. Trello-owned columns are intentionally NOT copied.

Reads prod (SELECT only); writes sandbox. Dry-run by default — pass --apply to write.

Usage:
    python scripts/copy_release_to_sandbox.py --job 590 --release 674            # preview
    python scripts/copy_release_to_sandbox.py --job 590 --release 674 --apply    # write

Note: PDF drawings are stored on each server's local disk (not the DB), and prod has
no drawing versions for 590-674, so this copies only the release row. To exercise the
BB review in sandbox, upload the FC PDF through the sandbox app afterward.
"""
import argparse
import sys

import psycopg2
import psycopg2.extras

from scripts.copy_releases_to_sandbox import PROD_URL, SANDBOX_URL, COLUMNS, UPDATE_COLS


def _mask(url: str) -> str:
    """host/db only — never print credentials."""
    tail = url.split("@")[-1] if "@" in url else url
    return tail.split("/")[-1] if "/" in tail else tail


def copy_one(job: int, release: str, apply: bool) -> bool:
    prod = psycopg2.connect(PROD_URL)
    sandbox = psycopg2.connect(SANDBOX_URL)
    try:
        col_list = ", ".join(f'"{c}"' for c in COLUMNS)
        with prod.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(f'SELECT {col_list} FROM releases WHERE job = %s AND release = %s',
                        (job, release))
            row = cur.fetchone()

        if not row:
            print(f"✗ prod has no release {job}-{release} (db={_mask(PROD_URL)}); nothing to copy.")
            return False

        print(f"Source (prod {_mask(PROD_URL)}): {job}-{release} "
              f"job_name={row['job_name']!r} stage={row['stage']!r} pm={row['pm']!r}")

        # Show whether sandbox already has it (insert vs update).
        with sandbox.cursor() as cur:
            cur.execute("SELECT id FROM releases WHERE job = %s AND release = %s", (job, release))
            existing = cur.fetchone()
        verb = "UPDATE existing" if existing else "INSERT new"
        print(f"Target (sandbox {_mask(SANDBOX_URL)}): would {verb} row.")

        if not apply:
            print("\nDRY RUN — no write. Re-run with --apply to copy into sandbox.")
            return True

        placeholders = ", ".join(["%s"] * len(COLUMNS))
        update_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in UPDATE_COLS)
        upsert = (f"INSERT INTO releases ({col_list}) VALUES ({placeholders}) "
                  f"ON CONFLICT (job, release) DO UPDATE SET {update_clause}")
        with sandbox.cursor() as cur:
            cur.execute(upsert, [row[c] for c in COLUMNS])
            sandbox.commit()
        print(f"✓ Upserted {job}-{release} into sandbox.")
        return True
    finally:
        prod.close()
        sandbox.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Copy one release from prod to sandbox.")
    p.add_argument("--job", type=int, required=True)
    p.add_argument("--release", required=True)
    p.add_argument("--apply", action="store_true", help="Write to sandbox (default: dry run).")
    args = p.parse_args()
    sys.exit(0 if copy_one(args.job, args.release, args.apply) else 1)
