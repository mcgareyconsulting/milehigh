import openpyxl
from app.trello.utils import extract_card_name, extract_identifier
from app.onedrive.utils import find_excel_row
from app.sheets import get_excel_dataframe

stage_column_map = {
    "Fit Up Complete.": "Fitup comp",
    "Paint complete": "Paint Comp",
}


def extract_stage_info(data):
    """Extract stage information from Trello webhook data"""
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

    # The Excel row should be the DataFrame index + 2 (1 for header, 1 for 0-based to 1-based conversion)
    # But if your actual row is 152 when we calculate 36, there might be a different offset
    excel_row_num = row_index + 4

    # Find target column index
    if column_name not in df.columns:
        print(f"Target column '{column_name}' not found in DataFrame")
        return None

    col_index = df.columns.get_loc(column_name)
    excel_col_letter = openpyxl.utils.get_column_letter(col_index + 1)

    cell_address = f"{excel_col_letter}{excel_row_num}"
    print(f"DataFrame index: {row_index}, Calculated Excel row: {excel_row_num}")
    print(f"Found cell address: {cell_address} for identifier {identifier}")

    return cell_address


def sync_from_trello(data):
    """Sync data from Trello to OneDrive based on the webhook payload."""
    # print(data)

    # Extract stage information from webhook
    old_stage, new_stage = extract_stage_info(data)

    # card name
    card_name = extract_card_name(data)
    print(f"Syncing card: {card_name}")

    # Get unique id
    identifier = extract_identifier(card_name)
    print(f"Extracted identifier: {identifier}")

    # get the latest Excel data
    df = get_excel_dataframe()

    # return the row where the identifier matches
    row = find_excel_row(df, identifier)
    if row is not None:
        print(f"Row found for identifier {identifier}: {row}")

        # Update Excel if this is a stage transition we care about
        if old_stage and new_stage and old_stage != new_stage:
            print(f"Processing stage change: {old_stage} → {new_stage}")
        else:
            print("No stage change detected or not a list movement")

        column = stage_column_map.get(new_stage)
        if not column:
            print(
                f"Stage '{new_stage}' not found in stage_column_map. Skipping update."
            )
            return

        if column not in df.columns:
            print(f"Column '{column}' not found in Excel row. Skipping update.")
            return

        # Get Excel cell address
        cell_address = get_excel_cell_address_by_identifier(df, identifier, column)
        if not cell_address:
            print(f"Could not determine Excel cell address for identifier {identifier}")
            return

        print(f"Updating Excel cell {cell_address} for identifier {identifier}")

    else:
        print(f"No row found for identifier {identifier}")
