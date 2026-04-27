"""Re-pull Trello list-move history with the sync_operation source_id (=card_id)
so we can link to releases. Also pull DB field updates (Excel-side stage cell changes)."""
import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
conn = psycopg2.connect(url, sslmode="require")

# Trello list-move events (5 months)
print("Trello list_move events ...")
list_moves = pd.read_sql(
    """
    SELECT sl.timestamp AS ts,
           so.source_id AS card_id,
           sl.data       AS data
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type = 'trello_webhook'
      AND sl.message LIKE 'List move detected%'
    ORDER BY sl.timestamp
    """,
    conn,
)
print(f"  {len(list_moves)} rows")

# Excel-side DB field updates with old/new
print("Excel DB field updates ...")
db_updates = pd.read_sql(
    """
    SELECT sl.timestamp AS ts,
           so.source_id AS source_id,
           sl.data       AS data,
           sl.excel_identifier
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type = 'onedrive_poll'
      AND sl.message LIKE 'DB field update%'
    ORDER BY sl.timestamp
    """,
    conn,
)
print(f"  {len(db_updates)} rows")

list_moves.to_pickle("analysis/list_moves.pkl")
db_updates.to_pickle("analysis/db_updates.pkl")
print("saved analysis/{list_moves,db_updates}.pkl")

# Also pull onedrive sync_logs with row counts (to track when the team was active)
poll_summary = pd.read_sql(
    """
    SELECT sl.timestamp AS ts, sl.data
    FROM sync_logs sl
    JOIN sync_operations so ON sl.operation_id = so.operation_id
    WHERE so.operation_type = 'onedrive_poll'
      AND sl.message = 'Processing OneDrive data'
    ORDER BY sl.timestamp
    """,
    conn,
)
print(f"  poll_summary rows: {len(poll_summary)}")
poll_summary.to_pickle("analysis/onedrive_polls.pkl")

conn.close()
