"""
Copy non-Trello fields from production releases table to sandbox releases table.
Upserts by (job, release) unique constraint.
"""
import os
import sys

import psycopg2
import psycopg2.extras

try:  # allow both `python -m scripts.copy_releases_to_sandbox` and direct execution
    from scripts._db_urls import mask, prod_url, sandbox_url
except ImportError:  # pragma: no cover - path fixup for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts._db_urls import mask, prod_url, sandbox_url

# Non-Trello columns to copy (excludes: trello_card_id, trello_card_name, trello_list_id,
# trello_list_name, trello_card_description, trello_card_date, viewer_url)
COLUMNS = [
    "job", "release", "job_name", "description", "fab_hrs", "install_hrs",
    "paint_color", "pm", "by", "released", "fab_order", "stage", "stage_group",
    "start_install", "start_install_formula", "start_install_formulaTF",
    "comp_eta", "job_comp", "invoiced", "notes", "last_updated_at", "source_of_update",
    "is_active", "is_archived",
]

# Columns to update on conflict (everything except the unique key)
UPDATE_COLS = [c for c in COLUMNS if c not in ("job", "release")]


def main():
    prod, sandbox = prod_url(), sandbox_url()
    print(f"source: {mask(prod)}  ->  target: {mask(sandbox)}")

    # Read from production
    prod_conn = psycopg2.connect(prod)
    sandbox_conn = psycopg2.connect(sandbox)

    try:
        with prod_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            col_list = ", ".join(f'"{c}"' for c in COLUMNS)
            cur.execute(f'SELECT {col_list} FROM releases')
            rows = cur.fetchall()
            print(f"Read {len(rows)} rows from production releases table")

        # Upsert into sandbox
        col_list = ", ".join(f'"{c}"' for c in COLUMNS)
        placeholders = ", ".join(["%s"] * len(COLUMNS))
        update_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in UPDATE_COLS)

        upsert_sql = f"""
            INSERT INTO releases ({col_list})
            VALUES ({placeholders})
            ON CONFLICT (job, release) DO UPDATE SET {update_clause}
        """

        with sandbox_conn.cursor() as cur:
            count = 0
            for row in rows:
                values = [row[c] for c in COLUMNS]
                cur.execute(upsert_sql, values)
                count += 1

            sandbox_conn.commit()
            print(f"Upserted {count} rows into sandbox releases table")

    finally:
        prod_conn.close()
        sandbox_conn.close()


if __name__ == "__main__":
    main()
