"""Dump SubmittalEvents + Submittals + Users from prod DB to local pickled DataFrames for analysis."""
import os
import sys
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    print("No DATABASE_URL", file=sys.stderr)
    sys.exit(1)

conn = psycopg2.connect(url, sslmode="require", connect_timeout=10)

print("Pulling submittal_events...")
events = pd.read_sql(
    "SELECT id, submittal_id, action, payload, payload_hash, source, "
    "internal_user_id, external_user_id, is_system_echo, created_at, applied_at "
    "FROM submittal_events ORDER BY created_at",
    conn,
)
print(f"  {len(events)} rows")

print("Pulling submittals...")
subs = pd.read_sql(
    "SELECT id, submittal_id, procore_project_id, project_number, project_name, "
    "title, status, type, ball_in_court, submittal_manager, order_number, "
    "submittal_drafting_status, due_date, was_multiple_assignees, last_updated, "
    "created_at, last_bic_update FROM submittals",
    conn,
)
print(f"  {len(subs)} rows")

print("Pulling users...")
users = pd.read_sql(
    "SELECT id, username, first_name, last_name, is_admin, is_drafter, is_active, "
    "procore_id FROM users",
    conn,
)
print(f"  {len(users)} rows")

conn.close()

events.to_pickle("analysis/events.pkl")
subs.to_pickle("analysis/submittals.pkl")
users.to_pickle("analysis/users.pkl")
print("Saved analysis/{events,submittals,users}.pkl")
