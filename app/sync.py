import openpyxl
import pandas as pd
from app.trello.utils import (
    extract_card_name,
    extract_identifier,
    parse_trello_datetime,
)
from app.trello.api import get_trello_card_by_id, get_list_name_by_id
from app.onedrive.utils import get_excel_row_and_index_by_identifiers
from app.onedrive.api import get_excel_dataframe, update_excel_cell
from app.models import Job, db
from datetime import timezone, datetime

# # Stage mapping for Trello list names to Excel columns
# stage_column_map = {
#     "Fit Up Complete.": "Fitup comp",
#     "Paint complete": "Paint Comp",
#     "Shipping completed": "Ship",
# }


def rectify_db_on_trello_move(job, new_trello_list):
    print(new_trello_list)
    if new_trello_list == "Paint complete":
        job.fitup_comp = "X"
        job.welded = "X"
        job.paint_comp = "X"
        job.ship = "O"
    elif new_trello_list == "Fit Up Complete.":
        job.fitup_comp = "X"
        job.welded = "O"
        job.paint_comp = ""
        job.ship = ""
    elif new_trello_list == "Shipping completed":
        job.fitup_comp = "X"
        job.welded = "X"
        job.paint_comp = "X"
        job.ship = "X"
    # update last_updated_at, source_of_update, etc.


def compare_timestamps(event_time, source_time):
    """
    Compare Trello event timestamp with database record timestamp
    """
    print(event_time)
    if not event_time or not source_time:
        print(f"Invalid time event {event_time} or source {source_time}")
        return None

    if event_time > source_time:
        print("Trello event is newer than DB record.")
        return "newer"
    else:
        print("Trello event is older than DB record.")
        return "older"


def sync_from_trello(event_info):
    """
    Sync data from Trello to OneDrive based on the webhook payload
    """
    if event_info is None or not event_info.get("handled"):
        print("No actionable event info received from Trello webhook")
        return

    card_id = event_info["card_id"]
    event_time = parse_trello_datetime(event_info.get("time"))
    print(f"[SYNC] Processing Trello card ID: {card_id} at {event_time}")
    card_data = get_trello_card_by_id(card_id)
    if not card_data:
        print(f"[SYNC] Card {card_id} not found in Trello API")
        return

    rec = Job.query.filter_by(trello_card_id=card_id).one_or_none()

    # Prepare debug comparison before upsert/update
    debug_fields = [
        (
            "Trello name",
            card_data.get("name"),
            "DB name",
            getattr(rec, "trello_card_name", None),
        ),
        (
            "Trello desc",
            card_data.get("desc"),
            "DB desc",
            getattr(rec, "trello_card_description", None),
        ),
        (
            "Trello list id",
            card_data.get("idList"),
            "DB list id",
            getattr(rec, "trello_list_id", None),
        ),
        (
            "Trello list name",
            get_list_name_by_id(card_data.get("idList")),
            "DB list name",
            getattr(rec, "trello_list_name", None),
        ),
        (
            "Trello due",
            card_data.get("due"),
            "DB due",
            getattr(rec, "trello_card_date", None),
        ),
        (
            "Trello event time",
            event_time,
            "DB last updated",
            getattr(rec, "last_updated_at", None),
        ),
    ]

    if rec:
        print(
            f"[SYNC] Comparing Trello card ({card_id}) to DB record (Job id: {rec.id})"
        )
        for t_label, t_value, db_label, db_value in debug_fields:
            if t_value != db_value:
                print(
                    f"  DIFF: {db_label} != {t_label}: Trello={t_value!r} | DB={db_value!r}"
                )
            else:
                print(f"  MATCH: {db_label} == {t_label}: {t_value!r}")
    else:
        print(f"[SYNC] No DB record found for card {card_id}. Trello card:")
        for t_label, t_value, _, _ in debug_fields:
            print(f"  {t_label}: {t_value!r}")

    # if newer, update DB
    diff = compare_timestamps(event_time, rec.last_updated_at if rec else None)
    if diff == "newer":
        print(f"[SYNC] Updating DB record for card {card_id} from Trello data...")
        if not rec:
            print(f"[SYNC] No existing DB record for card {card_id}, creating new one.")
            rec = Job(
                job=0,  # Placeholder, should be set properly
                release=0,  # Placeholder, should be set properly
                job_name=card_data.get("name", "Unnamed Job"),
                source_of_update="Trello",
                last_updated_at=event_time,
            )
            # Note: You should ideally link this to an existing Job based on your logic
            # For now, we create a new record with placeholders

        # Update trello information
        rec.trello_card_name = card_data.get("name")
        rec.trello_card_description = card_data.get("desc")
        rec.trello_list_id = card_data.get("idList")
        rec.trello_list_name = get_list_name_by_id(card_data.get("idList"))
        if card_data.get("due"):
            rec.trello_card_date = parse_trello_datetime(card_data["due"])
        else:
            rec.trello_card_date = None

        rec.last_updated_at = event_time
        rec.source_of_update = "Trello"

        # Use mapping to update excel side of db row
        if event_info["event"] == "card_moved":
            print(
                f"[SYNC] Card move detected, updating DB fields accordingly. {rec.fitup_comp}, {rec.paint_comp}, {rec.ship}"
            )
            rectify_db_on_trello_move(rec, get_list_name_by_id(card_data.get("idList")))
            print(
                f"[SYNC] DB fields {rec.fitup_comp}, {rec.paint_comp}, {rec.ship} updated for card {card_id}."
            )

        db.session.add(rec)
        db.session.commit()
        print(f"[SYNC] DB record for card {card_id} updated.")
    else:
        print(f"[SYNC] No update needed for card {card_id}.")

    # Pass changes to excel
    if rec and event_info["event"] == "card_moved":
        # filter down known excel column letters
        column_updates = {
            "M": rec.fitup_comp,
            "N": rec.welded,
            "O": rec.paint_comp,
            "P": rec.ship,
        }  # fitup, welded, paint, ship

        # lookup on job and release #
        index, row = get_excel_row_and_index_by_identifiers(rec.job, rec.release)
        print(
            f"[SYNC] Found Excel row for Job {rec.job}, Release {rec.release}: {index} {row}"
        )
        # push to excel
        for col, val in column_updates.items():
            cell_address = col + str(index)
            update_excel_cell(cell_address, val)


# def sync_from_onedrive(data):
#     """
#     Sync data from OneDrive to Trello based on the webhook payload
#     """
#     if data is None:
#         print("No data received from OneDrive webhook")
#         return

#     if "resource" not in data or "changeType" not in data:
#         print("Invalid OneDrive webhook data format")
#         return

#     resource = data["resource"]
#     change_type = data["changeType"]

#     print(f"Received OneDrive webhook: Resource={resource}, ChangeType={change_type}")

#     # if change type is 'updated', we can assume a file was modified
#     if change_type == "updated":
#         # download file from OneDrive
#         df = get_excel_dataframe()

#         # load cached (previously synced) data
#         try:
#             cached_df = pd.read_excel("excel_snapshot.xlsx")
#         except FileNotFoundError:
#             print("No cached snapshot found, will save current state.")
#             cached_df = None

#         # Comparison
#         if cached_df is not None:
#             changes = compare_excel_snapshots(df, cached_df)
#             for identifier, column, old_val, new_val in changes:
#                 print(
#                     f"Changed: {identifier} column '{column}' from '{old_val}' to '{new_val}'"
#                 )
#         else:
#             print("No cached snapshot found, will save current state.")

#         # Save the current state for future comparisons
#         save_excel_snapshot(df, filename="excel_snapshot.xlsx")
