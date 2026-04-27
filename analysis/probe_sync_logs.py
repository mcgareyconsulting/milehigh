"""Probe sync_logs for procore-related entries with old/new info."""
import os
import json
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
conn = psycopg2.connect(url, sslmode="require")
cur = conn.cursor()

# What operation_ids in sync_logs link to procore sync_operations?
cur.execute("""
    SELECT count(*) FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type LIKE 'procore%'
""")
print("sync_logs joined to procore sync_operations:", cur.fetchone())

# Sample procore sync_log entries
print("\nSample procore log entries (with data):")
cur.execute("""
    SELECT sl.timestamp, so.operation_type, so.source_id, sl.level, sl.message, sl.data
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type LIKE 'procore%'
      AND sl.data IS NOT NULL
    ORDER BY sl.timestamp
    LIMIT 15
""")
for row in cur.fetchall():
    ts, otype, sid, lvl, msg, data = row
    dstr = json.dumps(data, default=str)[:300] if data else "null"
    print(f" {ts} {otype} sid={sid} {lvl}")
    print(f"   msg: {(msg or '')[:200]}")
    print(f"   data: {dstr}")

# Also check entries where message contains BIC detail
print("\nLogs with old/new in message (first 10):")
cur.execute("""
    SELECT sl.timestamp, so.operation_type, so.source_id, sl.message, sl.data
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type = 'procore_ball_in_court'
    ORDER BY sl.timestamp
    LIMIT 20
""")
for row in cur.fetchall():
    ts, otype, sid, msg, data = row
    print(f" {ts} sid={sid}")
    print(f"   msg: {(msg or '')[:240]}")
    if data:
        print(f"   data: {json.dumps(data, default=str)[:240]}")

# Status changes
print("\n\nLogs for procore_submittal_status (first 15):")
cur.execute("""
    SELECT sl.timestamp, so.source_id, sl.message, sl.data
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type = 'procore_submittal_status'
    ORDER BY sl.timestamp
    LIMIT 15
""")
for row in cur.fetchall():
    ts, sid, msg, data = row
    print(f" {ts} sid={sid}")
    print(f"   msg: {(msg or '')[:240]}")
    if data:
        print(f"   data: {json.dumps(data, default=str)[:240]}")

conn.close()
