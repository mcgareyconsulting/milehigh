import openpyxl
import pandas as pd
from app.trello.utils import extract_card_name, extract_identifier
from app.onedrive.utils import find_excel_row, save_excel_snapshot
from app.onedrive.api import get_excel_dataframe, update_excel_cell
from app.models import Job

# Stage mapping for Trello list names to Excel columns
stage_column_map = {
    "Fit Up Complete.": "Fitup comp",
    "Paint complete": "Paint Comp",
    "Shipping completed": "Ship",
}


def extract_stage_info(data):
    """
    Extract stage information from Trello webhook data
    """
    movement = data.get("action", {}).get("data", {})
    if "listBefore" in movement and "listAfter" in movement:
        old_stage = movement["listBefore"]["name"]
        new_stage = movement["listAfter"]["name"]
        card_name = movement["card"]["name"]
        print(f"[Sync] Card '{card_name}' moved from '{old_stage}' to '{new_stage}'.")
        return old_stage, new_stage
    return None, None


def get_excel_cell_address_by_identifier(df, identifier, column_name):
    """Get Excel cell address using identifier to find the row"""
    if not identifier:
        return None

    # Use the existing find_excel_row function to locate the row
    row_data = find_excel_row(df, identifier)

    if row_data is None:
        print(f"No matching row found for identifier {identifier}")
        return None

    # Find the original row index in the DataFrame by creating the same combined identifier
    combined = df["Job #"].astype(str) + "-" + df["Release #"].astype(str)
    matching_rows = df[combined == identifier]

    if matching_rows.empty:
        print(f"Could not find original row index for identifier: {identifier}")
        return None

    # Get the row index (using first match if multiple)
    row_index = matching_rows.index[0]

    # Debug: Let's see what we're working with
    print(f"DataFrame row index: {row_index}")
    print(f"Expected Excel row (index + 2): {row_index + 2}")

    # adjust based upon header rows in file
    excel_row_num = row_index + 4

    # Find target column index
    if column_name not in df.columns:
        print(f"Target column '{column_name}' not found in DataFrame")
        return None

    col_index = df.columns.get_loc(column_name)
    excel_col_letter = openpyxl.utils.get_column_letter(col_index + 1)

    # build cell address
    cell_address = f"{excel_col_letter}{excel_row_num}"
    print(f"DataFrame index: {row_index}, Calculated Excel row: {excel_row_num}")
    print(f"Found cell address: {cell_address} for identifier {identifier}")

    return cell_address


def sync_from_trello(data):
    print(data)

    # parsing data
    action = data["action"]
    action_type = action.get("type")
    action_data = action.get("data", {})
    card_info = action_data.get("card", {})
    card_id = card_info.get("id")

    rec = Job.query.filter_by(trello_card_id=card_id).one_or_none()
    if not rec:
        # Optionally create a new row, or skip if unknown
        print(f"No DB record found for card {card_id}")
        return "", 200

    new_desc = action_data["card"].get("desc")  # from webhook
    db_desc = rec.trello_card_description  # your DB field

    if new_desc != db_desc:
        print(f"Description mismatch! Trello: {new_desc} | DB: {db_desc}")
        # Decide: update DB, update Trello, log for review, etc.
    else:
        print("Description matches.")


# def sync_from_trello(data):
#     """
#     Sync data from Trello to OneDrive based on the webhook payload
#     """
#     # Extract stage information from webhook
#     old_stage, new_stage = extract_stage_info(data)

#     # card name
#     card_name = extract_card_name(data)
#     print(f"Syncing card: {card_name}")

#     # Get unique id
#     identifier = extract_identifier(card_name)
#     print(f"Extracted identifier: {identifier}")

#     # get the latest Excel data
#     df = get_excel_dataframe()

#     # return the row where the identifier matches
#     row = find_excel_row(df, identifier)
#     if row is not None:
#         print(f"Row found for identifier {identifier}: {row}")

#         # Update Excel if this is a stage transition we care about
#         if old_stage and new_stage and old_stage != new_stage:
#             print(f"Processing stage change: {old_stage} → {new_stage}")
#         else:
#             print("No stage change detected or not a list movement")

#         # Get correct column name from mapping
#         column = stage_column_map.get(new_stage)
#         if not column:
#             print(
#                 f"Stage '{new_stage}' not found in stage_column_map. Skipping update."
#             )
#             return

#         if column not in df.columns:
#             print(f"Column '{column}' not found in Excel row. Skipping update.")
#             return

#         # Get Excel cell address
#         cell_address = get_excel_cell_address_by_identifier(df, identifier, column)
#         if not cell_address:
#             print(f"Could not determine Excel cell address for identifier {identifier}")
#             return

#         print(f"Updating Excel cell {cell_address} for identifier {identifier}")

#         # TODO: Dynamically allocate state
#         # Update via Microsoft Graph API using your existing sheets.py function
#         success = update_excel_cell(cell_address, "X")

#         if success:
#             print(f"Excel update completed for {identifier}")
#         else:
#             print(f"Excel update failed for {identifier}")

#     else:
#         print(f"No row found for identifier {identifier}")


def sync_from_onedrive(data):
    """
    Sync data from OneDrive to Trello based on the webhook payload
    """
    if data is None:
        print("No data received from OneDrive webhook")
        return

    if "resource" not in data or "changeType" not in data:
        print("Invalid OneDrive webhook data format")
        return

    resource = data["resource"]
    change_type = data["changeType"]

    print(f"Received OneDrive webhook: Resource={resource}, ChangeType={change_type}")

    # if change type is 'updated', we can assume a file was modified
    if change_type == "updated":
        # download file from OneDrive
        df = get_excel_dataframe()

        # load cached (previously synced) data
        try:
            cached_df = pd.read_excel("excel_snapshot.xlsx")
        except FileNotFoundError:
            print("No cached snapshot found, will save current state.")
            cached_df = None

        # Comparison
        if cached_df is not None:
            changes = compare_excel_snapshots(df, cached_df)
            for identifier, column, old_val, new_val in changes:
                print(
                    f"Changed: {identifier} column '{column}' from '{old_val}' to '{new_val}'"
                )
        else:
            print("No cached snapshot found, will save current state.")

        # Save the current state for future comparisons
        save_excel_snapshot(df, filename="excel_snapshot.xlsx")


"""
Comparison service for comparing database and Excel data
"""
from app.models import query_job_releases
from app.onedrive.api import get_excel_dataframe
import pandas as pd


def normalize_percentage_field(value):
    """
    Normalize percentage fields to handle different formats:
    - 0.9 -> 0.9
    - 90% -> 0.9
    - "90%" -> 0.9
    - Empty/None -> None
    """
    if pd.isna(value) or value == "" or value is None:
        return None

    # Convert to string for processing
    str_value = str(value).strip()

    # Handle empty strings
    if not str_value:
        return None

    # If it ends with %, remove % and divide by 100
    if str_value.endswith("%"):
        try:
            return float(str_value[:-1]) / 100
        except ValueError:
            return None

    # Try to convert to float directly
    try:
        return float(str_value)
    except ValueError:
        return None


def normalize_dataframe_percentages(df, percentage_columns):
    """
    Normalize percentage columns in a dataframe
    """
    df_normalized = df.copy()

    for col in percentage_columns:
        if col in df_normalized.columns:
            df_normalized[col] = df_normalized[col].apply(normalize_percentage_field)

    return df_normalized


def debug_percentage_comparison(df_db, df_excel, percentage_cols):
    """
    Helper function to debug percentage field comparisons
    """
    debug_info = {}

    for col in percentage_cols:
        if col in df_db.columns and col in df_excel.columns:
            debug_info[col] = {
                "db_original": df_db[col].tolist(),
                "excel_original": df_excel[col].tolist(),
                "db_normalized": [
                    normalize_percentage_field(val) for val in df_db[col]
                ],
                "excel_normalized": [
                    normalize_percentage_field(val) for val in df_excel[col]
                ],
            }

    return debug_info


def run_comparison():
    """
    Compare database data with Excel data and return differences
    Returns: List of differences found
    """
    print("Running comparison...")
    print("Collecting from db...")
    df_db = query_job_releases()
    print("Collecting from Excel...")
    df_excel = get_excel_dataframe()

    # Normalize columns/types
    common_cols = [col for col in df_db.columns if col in df_excel.columns]
    df_db = df_db[common_cols].fillna("")
    df_excel = df_excel[common_cols].fillna("")

    # Define percentage columns that need normalization
    percentage_cols = [
        col
        for col in common_cols
        if col.lower() in ["invoiced", "job comp", "jobcomp", "job_comp"]
    ]

    # Normalize percentage fields
    if percentage_cols:
        df_db = normalize_dataframe_percentages(df_db, percentage_cols)
        df_excel = normalize_dataframe_percentages(df_excel, percentage_cols)

        # Fill NaN values in percentage columns with empty string for comparison
        for col in percentage_cols:
            if col in df_db.columns:
                df_db[col] = df_db[col].fillna("")
            if col in df_excel.columns:
                df_excel[col] = df_excel[col].fillna("")

    # Handle date columns
    date_cols = [
        col
        for col in common_cols
        if "date" in col.lower() or col.lower() in ["released", "comp. eta"]
    ]
    for col in date_cols:
        if col in df_db.columns:
            df_db[col] = df_db[col].astype(str)
        if col in df_excel.columns:
            df_excel[col] = df_excel[col].astype(str)

    # Add source column for tracking
    df_db["source"] = "db"
    df_excel["source"] = "excel"

    # Concatenate and find differences
    combined = pd.concat([df_db, df_excel], ignore_index=True)

    # Find duplicates based on all columns except 'source'
    subset_cols = [col for col in common_cols if col != "source"]
    diff = combined.drop_duplicates(subset=subset_cols, keep=False)

    # For each differing row, show which columns differ
    differences = []
    processed_identifiers = set()

    for _, row in diff.iterrows():
        identifier = {col: row[col] for col in ["Job #", "Release #"] if col in row}
        identifier_key = tuple(sorted(identifier.items()))

        # Skip if we've already processed this identifier
        if identifier_key in processed_identifiers:
            continue
        processed_identifiers.add(identifier_key)

        source = row["source"]

        # Find matching row in the other source
        other_source = "excel" if source == "db" else "db"
        other_row = combined[
            (combined["source"] == other_source)
            & (combined["Job #"] == row.get("Job #"))
            & (combined["Release #"] == row.get("Release #"))
        ]

        diff_cols = []
        column_differences = {}

        if not other_row.empty:
            for col in subset_cols:
                current_val = row[col]
                other_val = other_row.iloc[0][col]

                # Determine which is db and which is excel
                if source == "db":
                    db_val, excel_val = current_val, other_val
                else:
                    db_val, excel_val = other_val, current_val

                # Special handling for percentage columns
                if col in percentage_cols:
                    # Both values should already be normalized
                    if pd.isna(current_val) and pd.isna(other_val):
                        continue  # Both are NaN, consider equal
                    elif pd.isna(current_val) or pd.isna(other_val):
                        diff_cols.append(col)  # One is NaN, other isn't
                        column_differences[col] = {"db": db_val, "excel": excel_val}
                    elif abs(float(current_val or 0) - float(other_val or 0)) > 0.001:
                        diff_cols.append(col)  # Different values (with tolerance)
                        column_differences[col] = {"db": db_val, "excel": excel_val}
                else:
                    # Regular comparison for non-percentage columns
                    if current_val != other_val:
                        diff_cols.append(col)
                        column_differences[col] = {"db": db_val, "excel": excel_val}
        else:
            diff_cols = subset_cols  # All columns differ if no match found
            # Set values appropriately when no match found
            if source == "db":
                for col in subset_cols:
                    column_differences[col] = {"db": row[col], "excel": None}
            else:
                for col in subset_cols:
                    column_differences[col] = {"db": None, "excel": row[col]}

        if diff_cols:  # Only add if there are actual differences
            differences.append(
                {
                    "identifier": identifier,
                    "diff_columns": diff_cols,
                    "column_differences": column_differences,
                }
            )

    print(f"Comparison complete. Found {len(differences)} differences.")
    return differences
