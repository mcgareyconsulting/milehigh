"""
Copy non-Trello fields from production releases table to sandbox releases table.
Upserts by (job, release) unique constraint.
"""
import psycopg2
import psycopg2.extras

PROD_URL = "postgresql://mile_high_metal_works_trello_onedrive_user:G97rTBCFgwUubIokFMf85i7f4hwOCNUR@dpg-d3in27ogjchc73efo2l0-a.oregon-postgres.render.com/mile_high_metal_works_trello_onedrive"
SANDBOX_URL = "postgresql://sandbox_mhmw_db_user:SLnOrx7QQXDrWmXhKgQx9Dm84dqQZEqJ@dpg-d51h1uemcj7s73c31p20-a.oregon-postgres.render.com/sandbox_mhmw_db"

# Non-Trello columns to copy (excludes: trello_card_id, trello_card_name, trello_list_id,
# trello_list_name, trello_card_description, trello_card_date, viewer_url)
COLUMNS = [
    "job", "release", "job_name", "description", "fab_hrs", "install_hrs",
    "paint_color", "pm", "by", "released", "fab_order", "stage", "stage_group",
    "banana_color", "start_install", "start_install_formula", "start_install_formulaTF",
    "comp_eta", "job_comp", "invoiced", "notes", "last_updated_at", "source_of_update",
    "is_active", "is_archived",
]

# Columns to update on conflict (everything except the unique key)
UPDATE_COLS = [c for c in COLUMNS if c not in ("job", "release")]


def main():
    # Read from production
    prod_conn = psycopg2.connect(PROD_URL)
    sandbox_conn = psycopg2.connect(SANDBOX_URL)

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
