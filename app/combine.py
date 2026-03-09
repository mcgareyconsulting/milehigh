from app.trello.api import get_trello_cards_from_subset
from app.trello.utils import extract_identifier


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


def combine_trello_excel_data():
    """
    Returns a list of dicts with Trello card data keyed by identifier.
    Excel data is no longer included (Excel functionality removed).
    """
    trello_map, identifiers = get_identifier_to_trello_card_map_and_list()

    return [
        {
            "identifier": identifier,
            "trello": trello_map.get(identifier),
            "excel": None,
        }
        for identifier in identifiers
    ]
