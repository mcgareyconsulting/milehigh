"""Tests for set_mirror_date_range — same-board push vs cross-board rejection.

The mirror is resolved via the primary's "Linked card" attachment. ShortLinks are
global across Trello, so a stray/legacy link could point at another board. We reject
that using the idBoard that already rides along in the card fetch (no extra API call).
"""
from datetime import date
from unittest.mock import patch

from app.trello import api as trello_api


def _attachments_ok():
    return {"success": True, "attachments": [{"name": "Linked card", "fileName": "mShort"}]}


def test_same_board_pushes_range():
    with patch.object(trello_api.cfg, "TRELLO_BOARD_ID", "board-OURS"), \
         patch.object(trello_api, "get_card_attachments_by_card_id", return_value=_attachments_ok()), \
         patch.object(trello_api, "get_trello_card_by_id",
                      return_value={"id": "mirror-1", "idBoard": "board-OURS"}), \
         patch.object(trello_api, "update_card_date_range", return_value={"success": True}) as mock_push:
        result = trello_api.set_mirror_date_range("primary-1", date(2026, 6, 15), date(2026, 6, 17))

    assert result["success"] is True
    assert result["mirror_card_id"] == "mirror-1"
    mock_push.assert_called_once_with("mShort", date(2026, 6, 15), date(2026, 6, 17))


def test_cross_board_is_rejected_without_push():
    with patch.object(trello_api.cfg, "TRELLO_BOARD_ID", "board-OURS"), \
         patch.object(trello_api, "get_card_attachments_by_card_id", return_value=_attachments_ok()), \
         patch.object(trello_api, "get_trello_card_by_id",
                      return_value={"id": "mirror-X", "idBoard": "board-OTHER"}), \
         patch.object(trello_api, "update_card_date_range") as mock_push:
        result = trello_api.set_mirror_date_range("primary-1", date(2026, 6, 15), date(2026, 6, 17))

    assert result["success"] is False
    assert "different board" in result["error"]
    mock_push.assert_not_called()
