from app.trello.api import get_trello_cards_from_subset
from app.trello.utils import extract_identifier
from app.onedrive.api import get_excel_dataframe

from collections import defaultdict
from typing import List, Dict, Tuple


def list_duplicate_trello_identifiers() -> Tuple[List[str], Dict[str, List[dict]]]:
    """
    Returns:
      - dup_identifiers: identifiers that appear on more than one Trello card (first-seen order)
      - duplicates: dict of identifier -> list[Trello card dict] for those duplicates
    """
    cards = get_trello_cards_from_subset()
    by_identifier: Dict[str, List[dict]] = defaultdict(list)
    dup_identifiers: List[str] = []

    for card in cards:
        name = (card.get("name") or "").strip()
        if not name:
            continue
        ident = extract_identifier(name)
        if not ident:
            continue
        by_identifier[ident].append(card)
        if len(by_identifier[ident]) == 2:
            dup_identifiers.append(ident)

    duplicates = {k: v for k, v in by_identifier.items() if len(v) > 1}
    return dup_identifiers, duplicates


def get_identifier_to_trello_card_map_and_list():
    """
    Returns:
      - id_map: dict mapping valid identifier -> Trello card data (first seen)
      - identifiers: list of unique valid identifiers (first-seen order)
    """
    cards = get_trello_cards_from_subset()
    id_map = {}
    identifiers = []
    seen = set()

    for card in cards:
        name = (card.get("name") or "").strip()
        if not name:
            continue
        identifier = extract_identifier(name)
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        id_map[identifier] = card
        identifiers.append(identifier)

    return id_map, identifiers


def get_excel_data_by_identifier(df, identifiers):
    """
    Returns a dict mapping identifier -> Excel row data for given identifiers.
    """
    excel_map = {}
    df["identifier"] = df["Job #"].astype(str) + "-" + df["Release #"].astype(str)
    filtered = df[df["identifier"].isin(identifiers)]
    for _, row in filtered.iterrows():
        excel_map[row["identifier"]] = row.to_dict()
    return excel_map


def combine_trello_excel_data():
    """
    Combines Trello and Excel data for cards with valid identifiers.
    Returns a list of dicts with combined data.
    """
    trello_map, identifiers = get_identifier_to_trello_card_map_and_list()
    df = get_excel_dataframe()
    excel_map = get_excel_data_by_identifier(df, identifiers)

    combined = []
    for identifier in identifiers:
        combined.append(
            {
                "identifier": identifier,
                "trello": trello_map.get(identifier),
                "excel": excel_map.get(identifier),
            }
        )
    return combined


# Example usage:
# identifiers, dups = list_duplicate_trello_identifiers()
# print(f"Found {len(identifiers)} identifiers in Trello.")
# print(f"Found {len(dups)} duplicate identifiers in Trello.")
# print(identifiers)

# combined_data = combine_trello_excel_data()
# for item in combined_data:
#     print(item)

# count = sum(
#     1
#     for item in combined_data
#     if item["identifier"] and item["excel"] is not None and item["trello"] is not None
# )
# print(f"Count of sources with identifier, excel, and trello not None: {count}")
