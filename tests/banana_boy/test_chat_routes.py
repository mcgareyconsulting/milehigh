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


def test_chat_response_includes_usage_summary(app, client, logged_in_user, mock_haiku_reply):
    """Chat reply must surface a per-turn usage summary so the UI can render
    cost/duration under the assistant bubble."""
    from app.banana_boy import routes as bb_routes

    def fake_reply(history, *, extra_system_context="", tool_context=None,
                   usage_sink=None, voice_mode=False):
        if usage_sink is not None:
            usage_sink.append({
                "provider": "anthropic", "operation": "chat",
                "model": "claude-haiku-4-5-20251001", "iteration": 0,
                "duration_ms": 420,
                "input_tokens": 1200, "output_tokens": 80,
                "cache_read_tokens": 0, "cache_creation_tokens": 0,
                "cost_usd": 0.0016,
            })
        return "ok"

    mock_haiku_reply.side_effect = fake_reply

    resp = client.post("/banana-boy/chat", json={"message": "hi"})
    assert resp.status_code == 200
    body = resp.get_json()

    assert "usage" in body
    usage = body["usage"]
    assert usage["total_duration_ms"] == 420
    assert abs(usage["total_cost_usd"] - 0.0016) < 1e-9
    assert len(usage["calls"]) == 1
    call = usage["calls"][0]
    assert call["operation"] == "chat"
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert call["input_tokens"] == 1200
    assert call["output_tokens"] == 80


def test_chat_response_aggregates_compliance_scan_usage(app, client, logged_in_user, mock_haiku_reply):
    """When a compliance scan runs as a tool call, its Sonnet usage shows up
    alongside the Haiku chat usage in the same response."""
    def fake_reply(history, *, extra_system_context="", tool_context=None,
                   usage_sink=None, voice_mode=False):
        if usage_sink is not None:
            usage_sink.append({
                "provider": "anthropic", "operation": "chat",
                "model": "claude-haiku-4-5-20251001", "iteration": 0,
                "duration_ms": 200, "input_tokens": 300, "output_tokens": 50,
                "cost_usd": 0.0006,
            })
            usage_sink.append({
                "provider": "anthropic", "operation": "compliance_scan",
                "model": "claude-sonnet-4-6", "iteration": None,
                "duration_ms": 8500, "input_tokens": 30000, "output_tokens": 500,
                "cache_creation_tokens": 3000, "cost_usd": 0.111,
            })
        return "scan complete"

    mock_haiku_reply.side_effect = fake_reply

    resp = client.post("/banana-boy/chat", json={"message": "compliance on 480-299"})
    body = resp.get_json()
    usage = body["usage"]
    assert usage["total_duration_ms"] == 8700
    assert abs(usage["total_cost_usd"] - 0.1116) < 1e-9
    ops = [c["operation"] for c in usage["calls"]]
    assert ops == ["chat", "compliance_scan"]


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
