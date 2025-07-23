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

        if column not in row.index:
            print(f"Column '{column}' not found in Excel row. Skipping update.")
            return

        cell = row[column]
        print(f"Updating cell {cell} for identifier {identifier}")

        print(f"Updating cell {cell} for identifier {identifier}")

    else:
        print(f"No row found for identifier {identifier}")
