"""Dump job-log data: releases, release_events, job_change_logs."""
import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
conn = psycopg2.connect(url, sslmode="require")

print("releases...")
releases = pd.read_sql(
    "SELECT id, job, release, job_name, description, fab_hrs, install_hrs, "
    "pm, \"by\", released, fab_order, stage, stage_group, banana_color, "
    "start_install, comp_eta, job_comp, invoiced, "
    "trello_card_id, trello_list_name, last_updated_at, source_of_update, "
    "is_active, is_archived FROM releases",
    conn,
)
print(f"  {len(releases)} rows")

print("release_events...")
revents = pd.read_sql(
    "SELECT id, job, release, action, payload, source, "
    "internal_user_id, external_user_id, is_system_echo, created_at "
    "FROM release_events ORDER BY created_at",
    conn,
)
print(f"  {len(revents)} rows")

print("job_change_logs...")
jcl = pd.read_sql(
    "SELECT id, job, release, change_type, from_value, to_value, field_name, "
    "changed_at, source, triggered_by, operation_id "
    "FROM job_change_logs ORDER BY changed_at",
    conn,
)
print(f"  {len(jcl)} rows")

# Pull sync_logs of interest for trello/onedrive: only ones with structured 'old/new' or 'from/to' data
print("sync_logs (trello/onedrive with stage info)...")
sync_jobs = pd.read_sql(
    """
    SELECT sl.timestamp, so.operation_type, sl.message, sl.data,
           sl.job_id, sl.trello_card_id, sl.excel_identifier
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type IN ('trello_webhook','onedrive_poll')
      AND sl.data IS NOT NULL
      AND (sl.message ILIKE '%list move%'
           OR sl.message ILIKE '%stage%'
           OR sl.message ILIKE '%fab order%'
           OR sl.message ILIKE '%DB field update%'
           OR sl.message ILIKE '%cell updated%')
    ORDER BY sl.timestamp
    """,
    conn,
)
print(f"  {len(sync_jobs)} rows")

releases.to_pickle("analysis/releases.pkl")
revents.to_pickle("analysis/release_events.pkl")
jcl.to_pickle("analysis/job_change_logs.pkl")
sync_jobs.to_pickle("analysis/sync_jobs.pkl")
print("saved analysis/{releases,release_events,job_change_logs,sync_jobs}.pkl")

conn.close()
