def extract_fab_order(card, fab_order_field_id: str):
    """Return the Fab Order value as a float, or None."""
    for field_item in card.get("customFieldItems", []):
        if field_item.get("idCustomField") == fab_order_field_id:
            val = field_item.get("value", {}).get("number")
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None
    return None

def calculate_new_positions(sorted_cards):
    """Assign new Trello positions."""
    position_updates = []
    if len(sorted_cards) == 1:
        position_updates.append({
            "card_id": sorted_cards[0]["card_id"],
            "new_pos": "top"
        })
    else:
        base_pos = 16384
        for idx, card in enumerate(sorted_cards):
            position_updates.append({
                "card_id": card["card_id"],
                "new_pos": base_pos + (idx * 16384),
                "fab_order": card["fab_order"]
            })
    return position_updates
    
def sort_cards_by_fab_order(cards, fab_order_field_id: str):
    """Attach fab_order to cards and sort them."""
    card_data = []
    for card in cards:
        fab_order = extract_fab_order(card, fab_order_field_id)
        card_data.append({
            "card_id": card["id"],
            "card_name": card.get("name", "Unknown"),
            "fab_order": fab_order,
            "current_pos": card.get("pos")
        })
    # Sort: None values go last
    card_data.sort(key=lambda x: (x["fab_order"] is None, x["fab_order"] or 0))
    return card_data