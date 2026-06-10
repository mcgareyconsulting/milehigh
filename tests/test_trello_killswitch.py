"""TRELLO_MOCK is a complete outbound kill switch.

When TRELLO_MOCK is on, no outbound write reaches the real Trello board — the
direct API writes short-circuit before any HTTP call, and card creation returns
a non-success skip. This lets the internal PM board / timeline be exercised
without moving cards on the physical Trello board.
"""
from unittest.mock import patch

from app.trello import api as trello_api
from app.trello.card_creation import create_trello_card_core


def test_writes_disabled_flag_follows_config(app):
    with app.app_context():
        app.config['TRELLO_MOCK'] = True
        assert trello_api._trello_writes_disabled() is True
        app.config['TRELLO_MOCK'] = False
        assert trello_api._trello_writes_disabled() is False


def test_update_trello_card_makes_no_http_call_under_mock(app):
    with app.app_context():
        app.config['TRELLO_MOCK'] = True
        with patch.object(trello_api, 'requests') as mock_requests:
            result = trello_api.update_trello_card('card-1', new_due_date=None, clear_due_date=True)
        assert result is None
        mock_requests.put.assert_not_called()
        mock_requests.post.assert_not_called()


def test_move_mirror_card_no_op_under_mock(app):
    with app.app_context():
        app.config['TRELLO_MOCK'] = True
        # Returns before reading attachments / issuing any request.
        with patch.object(trello_api, 'get_card_attachments_by_card_id') as mock_attach:
            result = trello_api.move_mirror_card('card-1', 'list-1')
        assert result is None
        mock_attach.assert_not_called()


def test_card_creation_skipped_under_mock(app):
    with app.app_context():
        app.config['TRELLO_MOCK'] = True
        with patch.object(trello_api, 'requests') as mock_requests:
            result = create_trello_card_core('Job 1-A', 'desc', 'list-1')
        assert result['success'] is False
        assert result.get('skipped') is True
        mock_requests.post.assert_not_called()
