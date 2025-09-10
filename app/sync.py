import openpyxl
import pandas as pd
from pandas import Timestamp
from app.trello.utils import (
    extract_card_name,
    extract_identifier,
    parse_trello_datetime,
)
from app.trello.api import (
    get_trello_card_by_id,
    get_list_name_by_id,
    get_list_by_name,
    move_card_to_list,
    set_card_due_date,
)
from app.onedrive.utils import (
    get_excel_row_and_index_by_identifiers,
    parse_excel_datetime,
)
from app.onedrive.api import get_excel_dataframe, update_excel_cell
from app.models import Job, db
from datetime import datetime, date, timezone, time
from zoneinfo import ZoneInfo


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
    Compare external event timestamp with database record timestamp.
    Returns "newer", "older", or None.
    """
    if not event_time:
        print("Invalid event_time (None)")
        return None

    if not source_time:
        print("No DB timestamp — treating event as newer.")
        return "newer"

    if event_time > source_time:
        print("Event is newer than DB record.")
        return "newer"
    else:
        print("Event is older than DB record.")
        return "older"


def as_date(val):
    if pd.isna(val) or val is None:
        return None
    # Handle pd.Timestamp, datetime, string, etc.
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    # Try parsing string
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


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


# Determine Trello list based on Excel/DB status
def determine_trello_list_from_db(rec):
    if (
        rec.fitup_comp == "X"
        and rec.welded == "X"
        and rec.paint_comp == "X"
        and (rec.ship == "O" or rec.ship == "T")
    ):
        return "Paint complete"
    elif (
        rec.fitup_comp == "X"
        and rec.welded == "O"
        and rec.paint_comp == None
        and rec.ship == None
    ):
        return "Fit Up Complete."
    elif (
        rec.fitup_comp == "X"
        and rec.welded == "X"
        and rec.paint_comp == "X"
        and rec.ship == "X"
    ):
        return "Shipping completed"
    else:
        return None  # no matching list


# Helper: detect if start_install is formula-driven
def is_formula_cell(row):
    formula_val = row.get("start_install_formula")
    formulaTF_val = row.get("start_install_formulaTF")
    return bool(formulaTF_val) or (
        isinstance(formula_val, str) and formula_val.startswith("=")
    )


def sync_from_onedrive(data):
    """
    Sync data from OneDrive to Trello based on the polling payload
    TODO: List movement mapping errors, duplicate db records being passed on one change
    """
    if data is None:
        print("No data received from OneDrive polling")
        return

    if "last_modified_time" not in data or "data" not in data:
        print("Invalid OneDrive polling data format")
        return

    # Convert Excel last_modified_time (string) → datetime
    excel_last_updated = parse_excel_datetime(data["last_modified_time"])
    df = data["data"]

    print(f"[SYNC] Processing OneDrive data last modified at {excel_last_updated}")
    print(f"[SYNC] DataFrame {df.shape[0]} rows, {df.shape[1]} columns")

    updated_records = []

    # Fields to check for diffs
    fields_to_check = [
        # ("Excel column name", "DB field name", "type")
        ("Fitup comp", "fitup_comp", "text"),
        ("Welded", "welded", "text"),
        ("Paint Comp", "paint_comp", "text"),
        ("Ship", "ship", "text"),
        ("Start install", "start_install", "date"),
    ]

    for _, row in df.iterrows():
        job = row.get("Job #")
        release = row.get("Release #")
        if pd.isna(job) or pd.isna(release):
            print(f"[SYNC] Skipping row with missing Job # or Release #: {row}")
            continue

        identifier = f"{job}-{release}"
        # print(f"[SYNC] Processing Excel row for identifier {identifier}")

        rec = Job.query.filter_by(job=job, release=release).one_or_none()
        if not rec:
            # print(
            #     f"[SYNC] No DB record found for Job {job}, Release {release}, skipping."
            # )
            continue

        db_last_updated = rec.last_updated_at

        # Only log diffs if Excel is newer
        if excel_last_updated <= db_last_updated:
            print(
                f"[DIFF] Skipping {identifier}: Excel last updated {excel_last_updated} <= DB {db_last_updated}"
            )
            continue

        record_updated = False
        formula_status_for_trello = None  # For Trello update later

        for excel_field, db_field, field_type in fields_to_check:
            excel_val = row.get(excel_field)
            db_val = getattr(rec, db_field, None)

            # Normalize date fields if date
            if field_type == "date":
                excel_val = as_date(excel_val)
                db_val = as_date(db_val)

            # For most fields, treat NaN/None as equivalent
            if (pd.isna(excel_val) or excel_val is None) and db_val is None:
                continue

            # Special handling for 'start_install' to check formula status
            if field_type == "date":
                is_formula = is_formula_cell(row)
                formula_status_for_trello = is_formula  # Track for Trello card update

                if is_formula:
                    # If formula-driven, update DB if value differs, but do not update Trello
                    if excel_val != db_val:
                        print(is_formula, row)
                        print(
                            f"[SYNC] {job}-{release} Updating DB {db_field} (formula-driven): {db_val!r} -> {excel_val!r}"
                        )
                        setattr(rec, db_field, excel_val)
                        setattr(
                            rec,
                            "start_install_formula",
                            row.get("start_install_formula") or "",
                        )
                        setattr(
                            rec,
                            "start_install_formulaTF",
                            bool(row.get("start_install_formulaTF")),
                        )
                        record_updated = True
                else:
                    # Hard-coded: update DB if value differs and clear formula flags
                    if excel_val != db_val:
                        print(
                            f"[SYNC] {job}-{release} Updating DB {db_field} (hard-coded): {db_val!r} -> {excel_val!r}"
                        )
                        setattr(rec, db_field, excel_val)
                        setattr(rec, "start_install_formula", "")
                        setattr(rec, "start_install_formulaTF", False)
                        record_updated = True
                continue  # skip generic update for this field

            # Generic update for non-special fields
            if excel_val != db_val:
                print(
                    f"[SYNC] {job}-{release} Updating DB {db_field}: {db_val!r} -> {excel_val!r}"
                )
                setattr(rec, db_field, excel_val)
                record_updated = True

        if record_updated:
            rec.last_updated_at = excel_last_updated
            rec.source_of_update = "Excel"
            updated_records.append((rec, formula_status_for_trello))

    # Commit all DB updates at once
    if updated_records:
        print(updated_records)
        for rec, _ in updated_records:
            db.session.add(rec)
        db.session.commit()
        print(f"[SYNC] Committed {len(updated_records)} updated records to DB.")

        # Trello update: due dates and list movement
        for rec, is_formula in updated_records:
            print(is_formula)
            if hasattr(rec, "trello_card_id") and rec.trello_card_id:
                try:
                    # Due date update (as before)
                    if is_formula or is_formula is None:
                        print(
                            f"[SYNC] Clearing due date for Trello card {rec.trello_card_id} (formula-driven)."
                        )
                        set_card_due_date(rec.trello_card_id, None)
                    else:
                        print(
                            f"[SYNC] Setting due date for Trello card {rec.trello_card_id} to {rec.start_install}."
                        )
                        set_card_due_date(rec.trello_card_id, rec.start_install)

                    # List movement
                    current_list_id = getattr(rec, "trello_list_id", None)
                    new_list_name = determine_trello_list_from_db(rec)
                    if new_list_name:
                        new_list = get_list_by_name(new_list_name)
                        if new_list and new_list["id"] != current_list_id:
                            print(
                                f"[SYNC] Moving Trello card {rec.trello_card_id} to list '{new_list_name}'"
                            )
                            move_card_to_list(rec.trello_card_id, new_list["id"])
                            # Update DB record with new list info
                            rec.trello_list_id = new_list["id"]
                            rec.trello_list_name = new_list_name
                            rec.last_updated_at = datetime.now(timezone.utc).replace(
                                tzinfo=None
                            )
                            rec.source_of_update = "Excel"
                            db.session.add(rec)
                            db.session.commit()
                except Exception as e:
                    print(
                        f"[SYNC] Error updating Trello card {rec.trello_card_id}: {e}"
                    )
    else:
        print("[SYNC] No records needed updating.")

    print("[SYNC] OneDrive sync complete.")

    #     updated = False

    #     for excel_field, db_field in fields_to_check:
    #         excel_val = row.get(excel_field)
    #         db_val = getattr(rec, db_field, None)

    #         # Skip if both empty
    #         if (pd.isna(excel_val) or excel_val is None) and db_val is None:
    #             continue

    #         # For 'start_install', check the formula flag
    #         if db_field == "start_install":
    #             formula_val = row.get(f"start_install_formula")
    #             formulaTF_val = row.get(f"start_install_formulaTF")
    #             is_formula = (
    #                 formula_val is not None and str(formula_val).startswith("=")
    #             ) or bool(formulaTF_val)

    #             # force to date
    #             excel_date = as_date(excel_val)
    #             db_date = as_date(db_val)

    #             if is_formula:
    #                 print(
    #                     f"[SYNC] Skipping Trello update for {db_field} because it is formula-driven (formula: {formula_val!r})"
    #                 )
    #                 # Optionally update DB with current value only if you want to keep it in sync
    #                 if excel_date != db_date:
    #                     print(
    #                         f"[SYNC] Updating DB {db_field} from Excel (formula-driven): {db_date!r} -> {excel_date!r}"
    #                     )
    #                     setattr(rec, db_field, excel_date)
    #                     updated = True
    #                 continue  # Don't update Trello for formula-driven cells

    #             # If not formula-driven, treat as explicit/hard-coded
    #             print(f"[SYNC] {db_field} is hard-coded (not formula-driven).")
    #             if excel_date != db_date:
    #                 print(
    #                     f"[SYNC] Updating {db_field} from Excel: {db_date!r} -> {excel_date!r}"
    #                 )
    #                 setattr(rec, db_field, excel_date)
    #                 setattr(rec, "start_install_formula", "")  # clear formula flag
    #                 setattr(
    #                     rec, "start_install_formulaTF", False
    #                 )  # clear formulaTF flag
    #                 updated = True
    #             # If you want to trigger Trello update, do so here (outside this loop)
    #             continue

    #         # # For all other fields
    #         # if excel_val != db_val:
    #         #     # diff = compare_timestamps(excel_last_updated, rec.last_updated_at)
    #         #     # if diff == "newer":
    #         #     print(
    #         #         f"[SYNC] Updating {db_field} from Excel: {db_val!r} -> {excel_val!r}"
    #         #     )
    #         #     setattr(rec, db_field, excel_val)
    #         #     updated = True
    #         #     # else:
    #         #     #     print(
    #         #     #         f"[SYNC] SKIP {db_field} (Excel older than DB): Excel={excel_val!r} | DB={db_val!r}"
    #         #     #     )

    #     if updated:
    #         # Update DB timestamp
    #         rec.last_updated_at = excel_last_updated
    #         updated_records.append(rec)

    # # Commit all updates at once
    # if updated_records:
    #     for rec in updated_records:
    #         db.session.add(rec)
    #     db.session.commit()
    #     print(f"[SYNC] Committed {len(updated_records)} updated records to DB.")

    #     # Move Trello cards for updated records
    #     for rec in updated_records:
    #         if hasattr(rec, "trello_card_id") and rec.trello_card_id:
    #             print(rec)
    #             try:
    #                 # if formula is true, set empty due date
    #                 if is_formula:
    #                     print(
    #                         f"[SYNC] Clearing due date for Trello card {rec.trello_card_id} because it is formula-driven."
    #                     )
    #                     set_card_due_date(rec.trello_card_id, "")
    #                 else:
    #                     print(
    #                         f"[SYNC] Setting due date for Trello card {rec.trello_card_id} to {rec.start_install}."
    #                     )
    #                     set_card_due_date(rec.trello_card_id, rec.start_install)

    #                 # Update db with new info
    #                 rec.trello_card_date = rec.start_install
    #                 rec.last_updated_at = datetime.now(timezone.utc).replace(
    #                     tzinfo=None
    #                 )
    #                 rec.source_of_update = "Excel"
    #                 db.session.add(rec)
    #                 db.session.commit()
    #             except Exception as e:
    #                 print(
    #                     f"[SYNC] Error setting due date for Trello card {rec.trello_card_id}: {e}"
    #                 )
    #             #     current_list_id = rec.trello_list_id
    #             #     new_list_name = determine_trello_list_from_db(rec)
    #             #     if new_list_name:
    #             #         new_list = get_list_by_name(new_list_name)
    #             #         if new_list and new_list["id"] != current_list_id:
    #             #             print(
    #             #                 f"[SYNC] Moving Trello card {rec.trello_card_id} to list '{new_list_name}'"
    #             #             )
    #             #             move_card_to_list(rec.trello_card_id, new_list["id"])
    #             #             # Update DB record with new list info
    #             #             rec.trello_list_id = new_list["id"]
    #             #             rec.trello_list_name = new_list_name
    #             #             rec.last_updated_at = datetime.now(timezone.utc).replace(
    #             #                 tzinfo=None
    #             #             )
    #             #             rec.source_of_update = "Excel"
    #             #             db.session.add(rec)
    #             #             db.session.commit()
    #             # except Exception as e:
    #             #     print(f"[SYNC] Error moving Trello card {rec.trello_card_id}: {e}")
    # else:
    #     print("[SYNC] No records needed updating.")

    # print("[SYNC] OneDrive sync complete.")
