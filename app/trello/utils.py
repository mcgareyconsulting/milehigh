def extract_card_text(data):
    try:
        return data["action"]["display"]["entities"]["card"]["text"]
    except (KeyError, TypeError):
        return None
