"""
Unit tests for app/procore/helpers.py
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.models import db


class TestIsEmail:
    def test_valid_email(self):
        from app.procore.helpers import is_email
        assert is_email("test@example.com") is True

    def test_invalid_email_plain_name(self):
        from app.procore.helpers import is_email
        assert is_email("John Smith") is False

    def test_invalid_email_empty(self):
        from app.procore.helpers import is_email
        assert is_email("") is False

    def test_invalid_email_none(self):
        from app.procore.helpers import is_email
        assert is_email(None) is False


class TestParseBallInCourtFromSubmittal:
    def test_single_user(self):
        from app.procore.helpers import parse_ball_in_court_from_submittal
        data = {"ball_in_court": [{"user": {"name": "Alice", "login": "alice@x.com"}}]}
        result = parse_ball_in_court_from_submittal(data)
        assert result["ball_in_court"] == "Alice"
        assert result["approvers"] == []

    def test_multiple_users(self):
        from app.procore.helpers import parse_ball_in_court_from_submittal
        data = {
            "ball_in_court": [
                {"user": {"name": "Alice", "login": "alice@x.com"}},
                {"user": {"name": "Bob", "login": "bob@x.com"}},
            ]
        }
        result = parse_ball_in_court_from_submittal(data)
        assert result["ball_in_court"] == "Alice, Bob"

    def test_empty_array(self):
        from app.procore.helpers import parse_ball_in_court_from_submittal
        result = parse_ball_in_court_from_submittal({"ball_in_court": []})
        assert result["ball_in_court"] is None

    def test_missing_key(self):
        from app.procore.helpers import parse_ball_in_court_from_submittal
        result = parse_ball_in_court_from_submittal({})
        assert result["ball_in_court"] is None

    def test_skips_email_names(self):
        from app.procore.helpers import parse_ball_in_court_from_submittal
        # name looks like email — should be skipped; login also email — skip whole entry
        data = {"ball_in_court": [{"user": {"name": "alice@x.com", "login": "alice@x.com"}}]}
        result = parse_ball_in_court_from_submittal(data)
        assert result["ball_in_court"] is None

    def test_falls_back_to_approvers(self):
        from app.procore.helpers import parse_ball_in_court_from_submittal
        data = {
            "approvers": [
                {
                    "response_required": True,
                    "distributed": False,
                    "response": {"considered": "pending", "name": "pending"},
                    "user": {"name": "Carol", "login": "carol@x.com"},
                }
            ]
        }
        result = parse_ball_in_court_from_submittal(data)
        assert result["ball_in_court"] == "Carol"

    def test_non_dict_returns_none(self):
        from app.procore.helpers import parse_ball_in_court_from_submittal
        assert parse_ball_in_court_from_submittal("not a dict") is None


class TestExtractProcoreUserIdFromWebhook:
    def test_user_id_key(self):
        from app.procore.helpers import extract_procore_user_id_from_webhook
        assert extract_procore_user_id_from_webhook({"user_id": 42}) == "42"

    def test_initiator_id_key(self):
        from app.procore.helpers import extract_procore_user_id_from_webhook
        assert extract_procore_user_id_from_webhook({"initiator_id": 99}) == "99"

    def test_missing_returns_none(self):
        from app.procore.helpers import extract_procore_user_id_from_webhook
        assert extract_procore_user_id_from_webhook({}) is None

    def test_non_dict_returns_none(self):
        from app.procore.helpers import extract_procore_user_id_from_webhook
        assert extract_procore_user_id_from_webhook(None) is None


class TestCreateSubmittalPayloadHash:
    def test_deterministic(self):
        from app.procore.helpers import create_submittal_payload_hash
        h1 = create_submittal_payload_hash("updated", "123", {"key": "value"})
        h2 = create_submittal_payload_hash("updated", "123", {"key": "value"})
        assert h1 == h2

    def test_different_payloads_differ(self):
        from app.procore.helpers import create_submittal_payload_hash
        h1 = create_submittal_payload_hash("updated", "123", {"key": "a"})
        h2 = create_submittal_payload_hash("updated", "123", {"key": "b"})
        assert h1 != h2


class TestIsDuplicateWebhook:
    @pytest.fixture
    def app(self):
        app = create_app()
        app.config["TESTING"] = True
        with app.app_context():
            db.create_all()
            yield app
            db.session.remove()
            db.drop_all()

    def test_first_call_returns_false(self, app):
        from app.procore.helpers import is_duplicate_webhook
        result = is_duplicate_webhook(resource_id=1, project_id=100, event_type="created")
        assert result is False

    def test_second_call_returns_true(self, app):
        from app.procore.helpers import is_duplicate_webhook
        # Patch time.time so both calls land in the same dedup bucket
        with patch("app.procore.helpers.time.time", return_value=1000.0):
            first = is_duplicate_webhook(resource_id=2, project_id=200, event_type="updated")
            second = is_duplicate_webhook(resource_id=2, project_id=200, event_type="updated")
        assert first is False
        assert second is True
