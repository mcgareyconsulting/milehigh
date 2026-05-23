"""Probe context JSON shape on procore sync_operations."""
import os
import json
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
conn = psycopg2.connect(url, sslmode="require")
cur = conn.cursor()

for op_type in [
    "procore_ball_in_court",
    "procore_submittal_status",
    "procore_submittal_create",
    "procore_submittal_title",
    "procore_submittal_manager",
]:
    print("=" * 70)
    print(op_type)
    print("=" * 70)
    cur.execute(
        "SELECT context, source_id, started_at FROM sync_operations "
        "WHERE operation_type=%s ORDER BY started_at LIMIT 5",
        (op_type,),
    )
    for ctx, sid, ts in cur.fetchall():
        print(f" {ts}  source_id={sid}")
        print(f"   {json.dumps(ctx, default=str)[:400]}")

    # Also a recent one
    cur.execute(
        "SELECT context, source_id, started_at FROM sync_operations "
        "WHERE operation_type=%s ORDER BY started_at DESC LIMIT 3",
        (op_type,),
    )
    print(" -- recent --")
    for ctx, sid, ts in cur.fetchall():
        print(f" {ts}  source_id={sid}")
        print(f"   {json.dumps(ctx, default=str)[:400]}")
    print()

conn.close()
