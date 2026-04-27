"""Dump sync_logs entries that carry old/new value pairs for procore BIC/status/title/manager
operations — a 5-month historical view that predates submittal_events tracking."""
import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
conn = psycopg2.connect(url, sslmode="require")

# Pull only the meaningful rows (with data containing old_value/new_value)
sql = """
SELECT
    sl.timestamp        AS ts,
    so.operation_type   AS op_type,
    so.source_id        AS submittal_id,
    sl.message          AS message,
    sl.data             AS data
FROM sync_logs sl
JOIN sync_operations so ON sl.operation_id = so.operation_id
WHERE so.operation_type LIKE 'procore%'
  AND sl.message LIKE '%updated via webhook%'
ORDER BY sl.timestamp
"""
df = pd.read_sql(sql, conn)
print(f"pulled {len(df)} sync_log rows with old/new values")

# Flatten old/new fields
df["old_value"] = df["data"].apply(lambda d: d.get("old_value") if isinstance(d, dict) else None)
df["new_value"] = df["data"].apply(lambda d: d.get("new_value") if isinstance(d, dict) else None)
df["title"] = df["data"].apply(lambda d: d.get("submittal_title") if isinstance(d, dict) else None)
df["project_id"] = df["data"].apply(lambda d: d.get("project_id") if isinstance(d, dict) else None)

print("\nbreakdown:")
print(df["op_type"].value_counts())
print(f"\ndate range: {df['ts'].min()} -> {df['ts'].max()}")
print(f"unique submittals: {df['submittal_id'].nunique()}")

df.to_pickle("analysis/sync_log_events.pkl")
print("saved analysis/sync_log_events.pkl")

# Also pull the full procore submittal create operations to know creation timestamps
# (procore_submittal_create logs may not have old/new but tell us when submittal hit our system)
sql_create = """
SELECT so.source_id AS submittal_id, so.started_at AS created_ts, sl.data
FROM sync_operations so
LEFT JOIN sync_logs sl ON sl.operation_id = so.operation_id
WHERE so.operation_type = 'procore_submittal_create'
  AND sl.message LIKE '%created via webhook%'
ORDER BY so.started_at
"""
creates = pd.read_sql(sql_create, conn)
print(f"\npulled {len(creates)} procore_submittal_create log rows")
print(f"date range: {creates['created_ts'].min()} -> {creates['created_ts'].max()}")
creates.to_pickle("analysis/sync_log_creates.pkl")
print("saved analysis/sync_log_creates.pkl")

conn.close()
