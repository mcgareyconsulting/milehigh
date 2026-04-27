"""Probe sync_operations / sync_logs / system_logs / procore_outbox / webhook_receipts
to see what historical data we can mine for submittal context."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
conn = psycopg2.connect(url, sslmode="require")
cur = conn.cursor()


def q(sql, args=()):
    cur.execute(sql, args)
    return cur.fetchall()


print("=" * 70)
print("sync_operations")
print("=" * 70)
cur.execute("SELECT count(*), min(started_at), max(started_at) FROM sync_operations")
print("count, min, max:", cur.fetchone())

cur.execute(
    "SELECT operation_type, source_system, count(*) FROM sync_operations "
    "GROUP BY operation_type, source_system ORDER BY count(*) DESC LIMIT 30"
)
print("\nbreakdown by type, source:")
for row in cur.fetchall():
    print(" ", row)

# Any procore / submittal related operations?
cur.execute(
    "SELECT operation_type, source_system, count(*) FROM sync_operations "
    "WHERE operation_type ILIKE '%procore%' OR operation_type ILIKE '%submittal%' "
    "OR source_system ILIKE '%procore%' GROUP BY operation_type, source_system"
)
print("\nprocore/submittal-related rows:", cur.fetchall())

print("\n" + "=" * 70)
print("sync_logs")
print("=" * 70)
cur.execute("SELECT count(*), min(timestamp), max(timestamp) FROM sync_logs")
print("count, min, max:", cur.fetchone())

cur.execute(
    "SELECT count(*) FROM sync_logs WHERE message ILIKE '%submittal%' "
    "OR message ILIKE '%procore%' OR message ILIKE '%ball_in_court%' "
    "OR message ILIKE '%bic%'"
)
print("logs mentioning submittal/procore/BIC:", cur.fetchone())

print("\n" + "=" * 70)
print("system_logs")
print("=" * 70)
cur.execute("SELECT count(*), min(timestamp), max(timestamp) FROM system_logs")
print("count, min, max:", cur.fetchone())

cur.execute(
    "SELECT category, operation, count(*) FROM system_logs "
    "GROUP BY category, operation ORDER BY count(*) DESC LIMIT 30"
)
print("\nbreakdown:")
for row in cur.fetchall():
    print(" ", row)

print("\n" + "=" * 70)
print("procore_outbox")
print("=" * 70)
cur.execute("SELECT count(*), min(created_at), max(created_at) FROM procore_outbox")
print("count, min, max:", cur.fetchone())

cur.execute(
    "SELECT action, status, count(*) FROM procore_outbox "
    "GROUP BY action, status ORDER BY count(*) DESC"
)
print("\nbreakdown:")
for row in cur.fetchall():
    print(" ", row)

print("\n" + "=" * 70)
print("webhook_receipts")
print("=" * 70)
cur.execute("SELECT count(*), min(received_at), max(received_at) FROM webhook_receipts")
print("count, min, max:", cur.fetchone())

cur.execute(
    "SELECT provider, count(*) FROM webhook_receipts GROUP BY provider"
)
print("by provider:", cur.fetchall())

print("\n" + "=" * 70)
print("submittals.created_at distribution (older history we can mine)")
print("=" * 70)
cur.execute(
    "SELECT date_trunc('month', created_at) AS m, count(*) FROM submittals "
    "GROUP BY m ORDER BY m"
)
for row in cur.fetchall():
    print(" ", row)

cur.execute(
    "SELECT count(*) FROM submittals WHERE status='Closed' AND created_at < '2026-03-13'"
)
print("\nclosed submittals created BEFORE event tracking started:", cur.fetchone())

cur.execute(
    "SELECT count(*) FROM submittals WHERE status='Closed' AND created_at >= '2026-03-13'"
)
print("closed submittals created AFTER event tracking started:", cur.fetchone())

# release_events table — older job log audit
print("\n" + "=" * 70)
print("release_events (job log audit — for DWL job/release work)")
print("=" * 70)
cur.execute("SELECT count(*), min(created_at), max(created_at) FROM release_events")
print("count, min, max:", cur.fetchone())

cur.execute(
    "SELECT action, source, count(*) FROM release_events "
    "GROUP BY action, source ORDER BY count(*) DESC LIMIT 20"
)
print("\nbreakdown:")
for row in cur.fetchall():
    print(" ", row)

conn.close()
