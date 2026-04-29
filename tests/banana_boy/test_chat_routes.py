"""Integration tests for the /banana-boy endpoints."""
from unittest.mock import patch

from app.banana_boy.client import BananaBoyAPIError, BananaBoyConfigError
from app.models import ChatMessage


def test_messages_requires_auth(client):
    resp = client.get("/banana-boy/messages")
    assert resp.status_code == 401


def test_chat_requires_auth(client):
    resp = client.post("/banana-boy/chat", json={"message": "hi"})
    assert resp.status_code == 401


def test_messages_empty_for_new_user(client, logged_in_user):
    resp = client.get("/banana-boy/messages")
    assert resp.status_code == 200
    assert resp.get_json() == {"messages": []}


def test_chat_persists_user_and_assistant_turns(app, client, logged_in_user, mock_haiku_reply):
    resp = client.post("/banana-boy/chat", json={"message": "Hello"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "Sure thing — here's a banana fact."

    mock_haiku_reply.assert_called_once()
    history_arg = mock_haiku_reply.call_args.args[0]
    assert history_arg == [{"role": "user", "content": "Hello"}]

    with app.app_context():
        rows = ChatMessage.query.order_by(ChatMessage.id.asc()).all()
        assert [(r.role, r.content) for r in rows] == [
            ("user", "Hello"),
            ("assistant", "Sure thing — here's a banana fact."),
        ]


def test_chat_includes_prior_history(app, client, logged_in_user, mock_haiku_reply):
    client.post("/banana-boy/chat", json={"message": "first"})
    mock_haiku_reply.return_value = "second reply"
    client.post("/banana-boy/chat", json={"message": "second"})

    last_history = mock_haiku_reply.call_args.args[0]
    assert last_history == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "Sure thing — here's a banana fact."},
        {"role": "user", "content": "second"},
    ]

    with app.app_context():
        assert ChatMessage.query.count() == 4


def test_chat_rejects_empty_message(client, logged_in_user):
    resp = client.post("/banana-boy/chat", json={"message": "   "})
    assert resp.status_code == 400


def test_chat_rejects_oversized_message(client, logged_in_user):
    resp = client.post("/banana-boy/chat", json={"message": "x" * 8001})
    assert resp.status_code == 400


def test_chat_returns_503_when_not_configured(app, client, logged_in_user):
    with patch("app.banana_boy.routes.generate_reply", side_effect=BananaBoyConfigError("no key")):
        resp = client.post("/banana-boy/chat", json={"message": "hi"})
    assert resp.status_code == 503

    with app.app_context():
        rows = ChatMessage.query.all()
        assert len(rows) == 1
        assert rows[0].role == "user"


def test_chat_returns_502_on_upstream_error(app, client, logged_in_user):
    with patch("app.banana_boy.routes.generate_reply", side_effect=BananaBoyAPIError("boom")):
        resp = client.post("/banana-boy/chat", json={"message": "hi"})
    assert resp.status_code == 502

    with app.app_context():
        rows = ChatMessage.query.all()
        assert len(rows) == 1
        assert rows[0].role == "user"


def test_clear_messages(app, client, logged_in_user, mock_haiku_reply):
    client.post("/banana-boy/chat", json={"message": "hi"})

    resp = client.delete("/banana-boy/messages")
    assert resp.status_code == 204

    with app.app_context():
        assert ChatMessage.query.count() == 0


def test_users_only_see_their_own_history(app, client, logged_in_user, mock_haiku_reply):
    client.post("/banana-boy/chat", json={"message": "from user A"})

    # Switch sessions: log out, create + log in as another user
    client.post("/api/auth/logout")

    from app.auth.utils import hash_password
    from tests.conftest import make_user

    with app.app_context():
        make_user(
            "other@example.com",
            password_hash=hash_password("pw-1234567"),
            password_set=True,
        )

    client.post(
        "/api/auth/login",
        json={"username": "other@example.com", "password": "pw-1234567"},
    )

    resp = client.get("/banana-boy/messages")
    assert resp.status_code == 200
    assert resp.get_json() == {"messages": []}
