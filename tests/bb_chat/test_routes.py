"""HTTP route tests: access gating, persistence, ownership, and the admin access toggle."""
from unittest.mock import patch

from app.models import BBChatConversation, BBChatMessage, User, db


_CANNED = {
    "configured": True,
    "answer": "There are 3 releases in FABRICATION.",
    "metrics": {
        "model": "claude-sonnet-5", "input_tokens": 250, "output_tokens": 30,
        "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0012,
        "duration_ms": 1400, "tool_calls": 1, "request_ids": ["req_abc"],
    },
}


def test_send_requires_access(no_access_client):
    resp = no_access_client.post("/brain/bb-chat", json={"message": "hi"})
    assert resp.status_code == 403


def test_send_empty_message_400(bb_client):
    resp = bb_client.post("/brain/bb-chat", json={"message": "   "})
    assert resp.status_code == 400


def test_send_persists_turn_and_returns_metrics(app, bb_client, bb_user):
    with patch("app.brain.bb_chat.agent.run_chat", return_value=_CANNED):
        resp = bb_client.post("/brain/bb-chat", json={"message": "how many in fabrication?"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["conversation_id"]
    assert data["assistant_message"]["content"] == _CANNED["answer"]
    assert data["assistant_message"]["metrics"]["cost_usd"] == 0.0012
    assert data["assistant_message"]["metrics"]["request_id"] == "req_abc"

    with app.app_context():
        convos = BBChatConversation.query.filter_by(user_id=bb_user.id).all()
        assert len(convos) == 1
        msgs = BBChatMessage.query.filter_by(conversation_id=convos[0].id).all()
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[1].anthropic_request_id == "req_abc"
        assert msgs[1].cost_usd == 0.0012


def test_conversation_ownership_enforced(app, bb_client, bb_user):
    # A conversation owned by a DIFFERENT user must 404 for bb_user.
    with app.app_context():
        other = User(username="other@mhmw.com", password_hash="x", password_set=True)
        db.session.add(other)
        db.session.commit()
        convo = BBChatConversation(user_id=other.id, title="theirs")
        db.session.add(convo)
        db.session.commit()
        other_convo_id = convo.id

    resp = bb_client.get(f"/brain/bb-chat/conversations/{other_convo_id}")
    assert resp.status_code == 404


def test_list_conversations(app, bb_client, bb_user):
    with patch("app.brain.bb_chat.agent.run_chat", return_value=_CANNED):
        bb_client.post("/brain/bb-chat", json={"message": "q1"})
    resp = bb_client.get("/brain/bb-chat/conversations")
    assert resp.status_code == 200
    assert len(resp.get_json()["conversations"]) == 1


# --- Admin toggle -------------------------------------------------------------------

def test_admin_users_requires_admin(bb_client):
    # bb_user is a non-admin with chat access — still not allowed at the admin endpoint.
    assert bb_client.get("/brain/bb-chat/admin/users").status_code == 403


def test_admin_can_toggle_access(app, bb_admin_client):
    with app.app_context():
        target = User(username="grantme@mhmw.com", password_hash="x", password_set=True)
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    resp = bb_admin_client.post(f"/brain/bb-chat/admin/users/{target_id}/access",
                                json={"is_bb_chat": True})
    assert resp.status_code == 200
    assert resp.get_json()["is_bb_chat"] is True

    with app.app_context():
        assert db.session.get(User, target_id).is_bb_chat is True

    # Revoke.
    resp = bb_admin_client.post(f"/brain/bb-chat/admin/users/{target_id}/access",
                                json={"is_bb_chat": False})
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(User, target_id).is_bb_chat is False
