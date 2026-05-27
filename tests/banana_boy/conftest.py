"""Banana Boy fixtures: a logged-in user and a generic Anthropic-call patch."""
from unittest.mock import patch

import pytest

from app.auth.utils import hash_password
from tests.conftest import make_user as _make_base_user


@pytest.fixture
def logged_in_user(app, client):
    with app.app_context():
        user = _make_base_user(
            "banana@example.com",
            password_hash=hash_password("pw-1234567"),
            password_set=True,
        )
        user_id = user.id

    resp = client.post(
        "/api/auth/login",
        json={"username": "banana@example.com", "password": "pw-1234567"},
    )
    assert resp.status_code == 200
    return user_id


@pytest.fixture
def mock_haiku_reply():
    """Patch generate_reply at the routes import site."""
    with patch("app.banana_boy.routes.generate_reply") as m:
        m.return_value = "Sure thing — here's a banana fact."
        yield m
