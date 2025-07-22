from app.trello.utils import extract_card_name, extract_identifier
from app.onedrive.utils import find_excel_row
from app.sheets import get_excel_dataframe


def sync_from_trello(data):
    """Sync data from Trello to OneDrive based on the webhook payload."""
    print(data)
    # card name
    card_name = extract_card_name(data)
    print(f"Syncing card: {card_name}")

    # Get unique id
    identifier = extract_identifier(card_name)
    print(f"Extracted identifier: {identifier}")

    # get the latest Excel data
    df = get_excel_dataframe()  # This function should be defined to load the Excel data

    # return the row where the identifier matches
    row = find_excel_row(df, identifier)
    if row is not None:
        print(f"Row found for identifier {identifier}: {row}")
    else:
        print(f"No row found for identifier {identifier}")
