"""Probe the job-log side: jobs, releases, release_events, job_change_logs,
and sync_logs for trello/onedrive operations."""
import os
import json
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
conn = psycopg2.connect(url, sslmode="require")
cur = conn.cursor()

print("=" * 70)
print("releases table (newer model with stage)")
print("=" * 70)
cur.execute("SELECT count(*) FROM releases")
print("count:", cur.fetchone())
cur.execute("SELECT count(*) FROM releases WHERE is_active=true")
print("active:", cur.fetchone())
cur.execute("SELECT count(*) FROM releases WHERE is_archived=true")
print("archived:", cur.fetchone())
cur.execute("SELECT stage, count(*) FROM releases GROUP BY stage ORDER BY count(*) DESC")
print("\nstages:")
for row in cur.fetchall():
    print(" ", row)
cur.execute("SELECT stage_group, count(*) FROM releases GROUP BY stage_group ORDER BY count(*) DESC")
print("\nstage groups:")
for row in cur.fetchall():
    print(" ", row)
cur.execute("SELECT pm, count(*) FROM releases GROUP BY pm ORDER BY count(*) DESC LIMIT 15")
print("\ntop pm values:")
for row in cur.fetchall():
    print(" ", row)
cur.execute("SELECT \"by\", count(*) FROM releases GROUP BY \"by\" ORDER BY count(*) DESC LIMIT 15")
print("\ntop 'by' (drafter) values:")
for row in cur.fetchall():
    print(" ", row)

print("\n" + "=" * 70)
print("release_events")
print("=" * 70)
cur.execute("SELECT count(*), min(created_at), max(created_at) FROM release_events")
print("count, min, max:", cur.fetchone())
cur.execute("SELECT action, source, count(*) FROM release_events GROUP BY action, source ORDER BY count(*) DESC")
print("\nbreakdown:")
for row in cur.fetchall():
    print(" ", row)

# Sample payloads
print("\nsample release_events payloads (one per action/source pair):")
cur.execute("""
    WITH ranked AS (
      SELECT action, source, payload, created_at,
             row_number() OVER (PARTITION BY action, source ORDER BY created_at) AS rn
      FROM release_events
    )
    SELECT action, source, payload, created_at FROM ranked WHERE rn = 1 ORDER BY action
""")
for action, source, payload, ts in cur.fetchall():
    print(f"  [{action} / {source}] {ts}")
    print(f"    {json.dumps(payload, default=str)[:300]}")

print("\n" + "=" * 70)
print("job_change_logs")
print("=" * 70)
cur.execute("SELECT count(*), min(changed_at), max(changed_at) FROM job_change_logs")
print("count, min, max:", cur.fetchone())
cur.execute("SELECT change_type, source, count(*) FROM job_change_logs GROUP BY change_type, source ORDER BY count(*) DESC")
print("\nbreakdown:")
for row in cur.fetchall():
    print(" ", row)
cur.execute("SELECT field_name, count(*) FROM job_change_logs GROUP BY field_name ORDER BY count(*) DESC LIMIT 20")
print("\ntop fields tracked:")
for row in cur.fetchall():
    print(" ", row)
print("\nsample state_change rows:")
cur.execute("""
    SELECT job, release, field_name, from_value, to_value, source, changed_at
    FROM job_change_logs
    WHERE change_type='state_change'
    ORDER BY changed_at DESC LIMIT 10
""")
for row in cur.fetchall():
    print(" ", row)

print("\n" + "=" * 70)
print("sync_operations: trello and onedrive")
print("=" * 70)
cur.execute("""
    SELECT operation_type, source_system, count(*),
           min(started_at), max(started_at)
    FROM sync_operations
    WHERE operation_type IN ('trello_webhook', 'onedrive_poll')
    GROUP BY operation_type, source_system
""")
for row in cur.fetchall():
    print(" ", row)

print("\nsync_logs for trello/onedrive with structured data — sample:")
cur.execute("""
    SELECT sl.timestamp, so.operation_type, sl.message, sl.data, sl.job_id, sl.trello_card_id, sl.excel_identifier
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type IN ('trello_webhook', 'onedrive_poll')
      AND sl.data IS NOT NULL
      AND sl.message NOT LIKE '%SyncOperation%'
    ORDER BY sl.timestamp
    LIMIT 20
""")
for row in cur.fetchall():
    ts, otype, msg, data, jid, tcid, excel_id = row
    print(f" {ts} {otype} job_id={jid} card={tcid} excel={excel_id}")
    print(f"   msg: {(msg or '')[:200]}")
    print(f"   data: {json.dumps(data, default=str)[:240]}")

# What patterns exist in messages?
print("\nmessage prefix counts (trello_webhook):")
cur.execute("""
    SELECT substring(message from 1 for 60) AS prefix, count(*) AS n
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type = 'trello_webhook'
      AND sl.message NOT LIKE '%SyncOperation%'
    GROUP BY prefix
    ORDER BY n DESC LIMIT 25
""")
for row in cur.fetchall():
    print(" ", row)

print("\nmessage prefix counts (onedrive_poll):")
cur.execute("""
    SELECT substring(message from 1 for 60) AS prefix, count(*) AS n
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type = 'onedrive_poll'
      AND sl.message NOT LIKE '%SyncOperation%'
    GROUP BY prefix
    ORDER BY n DESC LIMIT 25
""")
for row in cur.fetchall():
    print(" ", row)

# Releases creation distribution
print("\nreleases.released distribution by month (when items were released):")
cur.execute("""
    SELECT date_trunc('month', released::timestamp) AS m, count(*) FROM releases
    WHERE released IS NOT NULL
    GROUP BY m ORDER BY m
""")
for row in cur.fetchall():
    print(" ", row)

conn.close()
