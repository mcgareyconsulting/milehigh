"""Outbound Trello mutations must be suppressed when sync is paused
(TRELLO_SYNC_PAUSED or TRELLO_MOCK), while reads stay live."""
from unittest.mock import patch

from app.trello import api as trello_api


def test_update_trello_card_skips_when_paused(app):
    with app.app_context():
        app.config["TRELLO_SYNC_PAUSED"] = True
        with patch.object(trello_api, "_real_put") as real_put:
            out = trello_api.update_trello_card("card-1", new_due_date=None, clear_due_date=True)
        real_put.assert_not_called()
        assert out == {}  # paused stand-in response


def test_update_trello_card_hits_api_when_not_paused(app):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    with app.app_context():
        app.config["TRELLO_SYNC_PAUSED"] = False
        app.config["TRELLO_MOCK"] = False
        with patch.object(trello_api, "_real_put", return_value=FakeResp()) as real_put:
            trello_api.update_trello_card("card-1", new_list_id="list-9")
        real_put.assert_called_once()


def test_trello_mock_also_pauses_direct_calls(app):
    """A board where TRELLO_MOCK=1 should no longer leak direct due-date pushes."""
    with app.app_context():
        app.config["TRELLO_SYNC_PAUSED"] = False
        app.config["TRELLO_MOCK"] = True
        with patch.object(trello_api, "_real_put") as real_put:
            trello_api.update_trello_card("card-2", new_list_id="list-1")
        real_put.assert_not_called()
