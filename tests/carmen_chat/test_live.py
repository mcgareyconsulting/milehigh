"""Live (realtime) Carmen: session brokering, the tool bridge, and transcript filing.

The WebSocket itself lives in the browser, so there is nothing server-side to test about
the audio. What the server owns — and what these tests cover — is the three things that
could go wrong badly: handing out a token, executing tools as the right user, and not
losing the conversation.
"""
from unittest.mock import patch

import pytest

from app.brain.carmen_chat import live, tools
from app.config import Config
from app.models import CarmenChatConversation, CarmenChatMessage


@pytest.fixture
def live_on(monkeypatch):
    monkeypatch.setattr(Config, "CARMEN_VOICE_ENABLED", True)
    monkeypatch.setattr(Config, "CARMEN_LIVE_ENABLED", True)
    monkeypatch.setattr(Config, "XAI_API_KEY", "xai-test-key")
    return Config


# --- tool schema conversion -----------------------------------------------------------

def test_realtime_tools_mirror_the_anthropic_definitions(live_on):
    """One tool list, two APIs — a tool added to tools.py is reachable by voice for free."""
    converted = live.realtime_tools()
    # Every database tool, plus the write_to_chat channel.
    assert len(converted) == len(tools.TOOL_DEFINITIONS) + 1
    assert {t["name"] for t in converted} == (
        {t["name"] for t in tools.TOOL_DEFINITIONS} | {live.TOOL_WRITE_TO_CHAT}
    )
    for t in converted:
        assert t["type"] == "function"
        assert t["description"]
        assert t["parameters"]["type"] == "object"
    # `input_schema` is Anthropic's name for it; xAI wants `parameters`.
    by_name = {t["name"]: t for t in converted}
    source = {t["name"]: t for t in tools.TOOL_DEFINITIONS}
    probe = tools.TOOL_SEARCH_BY_ID
    assert by_name[probe]["parameters"] == source[probe]["input_schema"]
    assert "input_schema" not in by_name[probe]


def test_write_to_chat_is_a_channel_not_a_database_tool(live_on):
    """It must not be dispatchable server-side — the browser answers it locally."""
    assert live.TOOL_WRITE_TO_CHAT not in tools.TOOL_EXECUTORS
    assert live.TOOL_WRITE_TO_CHAT in live.CLIENT_SIDE_TOOLS
    definition = next(t for t in live.realtime_tools() if t["name"] == live.TOOL_WRITE_TO_CHAT)
    assert "markdown" in definition["parameters"]["properties"]
    assert definition["parameters"]["required"] == ["markdown"]


def test_session_config_carries_prompt_tools_and_pcm_rates(live_on, bb_user):
    cfg = live.session_config(bb_user)
    assert cfg["voice"] == Config.CARMEN_VOICE_ID
    assert cfg["turn_detection"]["type"] == "server_vad"
    assert cfg["audio"]["input"]["format"]["rate"] == Config.CARMEN_LIVE_SAMPLE_RATE
    assert cfg["audio"]["output"]["format"]["rate"] == Config.CARMEN_LIVE_SAMPLE_RATE
    assert cfg["audio"]["input"]["transcription"]["enabled"] is True
    assert len(cfg["tools"]) == len(tools.TOOL_DEFINITIONS) + 1
    # The spoken-conversation rules ride along with the written system prompt.
    assert "SPEAKING ALOUD" in cfg["instructions"]
    assert "READ ONLY" in cfg["instructions"]
    assert "write_to_chat" in cfg["instructions"]


def test_session_config_carries_the_latency_and_pacing_settings(live_on):
    cfg = live.session_config(None)
    assert cfg["audio"]["output"]["speed"] == Config.CARMEN_LIVE_SPEED
    # "high" is xAI's default and the main source of dead air before she answers.
    assert cfg["reasoning"]["effort"] == Config.CARMEN_LIVE_REASONING_EFFORT
    assert cfg["turn_detection"]["silence_duration_ms"] == Config.CARMEN_LIVE_SILENCE_MS


def test_live_transcription_gets_the_same_shop_vocabulary_as_clips(app, live_on):
    from app.brain.carmen_chat import voice
    from app.models import User, db
    db.session.add(User(username="saul@mhmw.com", first_name="Saul", last_name="Reyes",
                        password_hash="x"))
    db.session.commit()

    terms = live.session_config(None)["audio"]["input"]["transcription"]["keyterms"]
    assert "submittal" in terms and "fab order" in terms
    # Real people's names ride along too, so "Saul" doesn't transcribe as "Salvo".
    assert "Saul" in terms and "Reyes" in terms
    assert len(terms) <= voice.MAX_KEYTERMS


def test_accent_is_applied_through_the_prompt(live_on, monkeypatch):
    monkeypatch.setattr(Config, "CARMEN_VOICE_ACCENT", "warm Latin American Spanish")
    assert "warm Latin American Spanish" in live.instructions_for(None)
    # ...and is absent entirely when unset, rather than leaving a dangling header.
    monkeypatch.setattr(Config, "CARMEN_VOICE_ACCENT", "")
    assert "ACCENT:" not in live.instructions_for(None)


# --- token minting --------------------------------------------------------------------

@pytest.mark.parametrize("body,expected", [
    ({"value": "tok_a"}, "tok_a"),
    ({"token": "tok_b"}, "tok_b"),
    ({"secret": "tok_c"}, "tok_c"),
    ({"client_secret": {"value": "tok_d"}}, "tok_d"),
    ({"nothing": "useful"}, ""),
    ("not a dict", ""),
])
def test_extract_secret_tolerates_response_shapes(body, expected):
    """The field name isn't pinned in the docs — don't hard-fail on a rename."""
    assert live._extract_secret(body) == expected


def test_mint_requires_configuration(monkeypatch):
    monkeypatch.setattr(Config, "XAI_API_KEY", None)
    with pytest.raises(live.LiveNotConfigured):
        live.mint_client_secret()


def test_mint_raises_live_error_on_unparsable_response(live_on):
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"unexpected": "shape"}
    with patch("app.brain.carmen_chat.live.requests.post", return_value=_Resp()):
        with pytest.raises(live.LiveError):
            live.mint_client_secret()


# --- the broker route -----------------------------------------------------------------

def test_token_route_requires_access(no_access_client):
    assert no_access_client.post("/brain/carmen-chat/voice/live/token").status_code == 403


def test_token_route_503_when_unconfigured(bb_client, monkeypatch):
    monkeypatch.setattr(Config, "XAI_API_KEY", None)
    assert bb_client.post("/brain/carmen-chat/voice/live/token").status_code == 503


def test_token_route_returns_secret_and_session(bb_client, live_on):
    minted = {"token": "ephemeral-abc", "expires_at": None, "ttl_seconds": 300}
    with patch.object(live, "mint_client_secret", return_value=minted):
        resp = bb_client.post("/brain/carmen-chat/voice/live/token")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["token"] == "ephemeral-abc"
    assert data["url"].startswith("wss://api.x.ai/v1/realtime?model=")
    assert data["session"]["tools"]
    assert data["max_session_seconds"] == Config.CARMEN_LIVE_MAX_SESSION_SECONDS


# --- the tool bridge ------------------------------------------------------------------

def test_tool_route_requires_access(no_access_client):
    resp = no_access_client.post("/brain/carmen-chat/voice/live/tool",
                                 json={"name": "search_todos", "arguments": {}})
    assert resp.status_code == 403


def test_tool_route_requires_a_name(bb_client, live_on):
    assert bb_client.post("/brain/carmen-chat/voice/live/tool", json={}).status_code == 400


def test_tool_route_rejects_non_object_arguments(bb_client, live_on):
    resp = bb_client.post("/brain/carmen-chat/voice/live/tool",
                          json={"name": "search_todos", "arguments": "not-an-object"})
    assert resp.status_code == 400


def test_tool_route_runs_as_the_session_user_not_the_body(bb_client, bb_user, live_on):
    """A live caller must not be able to act as someone else by naming them in the body."""
    with patch.object(live, "run_tool", return_value={"ok": True}) as run:
        resp = bb_client.post("/brain/carmen-chat/voice/live/tool", json={
            "name": "get_my_notifications",
            "arguments": {},
            "user_id": 999999,          # ignored
            "context": {"user_id": 999999},  # also ignored
        })
    assert resp.status_code == 200
    run.assert_called_once()
    assert run.call_args.kwargs["user_id"] == bb_user.id


def test_tool_route_only_reaches_the_read_only_executors(bb_client, live_on):
    """An unknown tool name comes back as an error, never as an execution."""
    resp = bb_client.post("/brain/carmen-chat/voice/live/tool",
                          json={"name": "drop_all_releases", "arguments": {}})
    assert resp.status_code == 200
    assert "unknown tool" in resp.get_json()["result"]["error"]


def test_tool_route_returns_a_readable_failure_instead_of_hanging_the_turn(bb_client, live_on):
    with patch.object(live, "run_tool", side_effect=RuntimeError("db exploded")):
        resp = bb_client.post("/brain/carmen-chat/voice/live/tool",
                              json={"name": "search_todos", "arguments": {}})
    # 200 with an error payload: the model needs *something* back or the session stalls.
    assert resp.status_code == 200
    assert resp.get_json()["result"]["error"]


# --- transcript filing ----------------------------------------------------------------

def test_live_turn_creates_and_then_continues_a_conversation(app, bb_client, bb_user, live_on):
    first = bb_client.post("/brain/carmen-chat/voice/live/turn", json={
        "user_text": "where does four ten two seventy one stand",
        "assistant_text": "It's in fabrication.",
    })
    assert first.status_code == 200
    convo_id = first.get_json()["conversation_id"]

    second = bb_client.post("/brain/carmen-chat/voice/live/turn", json={
        "user_text": "when does it ship",
        "assistant_text": "Thursday.",
        "conversation_id": convo_id,
    })
    assert second.get_json()["conversation_id"] == convo_id

    with app.app_context():
        assert CarmenChatConversation.query.filter_by(user_id=bb_user.id).count() == 1
        msgs = CarmenChatMessage.query.filter_by(conversation_id=convo_id).all()
        assert [m.role for m in msgs] == ["user", "assistant", "user", "assistant"]
        assert msgs[3].content == "Thursday."


def test_live_turn_rejects_an_empty_exchange(bb_client, live_on):
    resp = bb_client.post("/brain/carmen-chat/voice/live/turn",
                          json={"user_text": "  ", "assistant_text": ""})
    assert resp.status_code == 400


def test_live_turn_will_not_write_into_someone_elses_conversation(app, bb_client, no_access_user, live_on):
    from app.models import db
    with app.app_context():
        theirs = CarmenChatConversation(user_id=no_access_user.id, title="not yours")
        db.session.add(theirs)
        db.session.commit()
        theirs_id = theirs.id

    resp = bb_client.post("/brain/carmen-chat/voice/live/turn", json={
        "user_text": "hello", "assistant_text": "hi", "conversation_id": theirs_id,
    })
    assert resp.status_code == 404


# --- config surface -------------------------------------------------------------------

def test_voice_config_reports_live_availability(bb_client, live_on):
    body = bb_client.get("/brain/carmen-chat/voice/config").get_json()
    assert body["live"]["configured"] is True
    assert body["live"]["model"] == Config.CARMEN_LIVE_MODEL
    assert body["live"]["sample_rate"] == Config.CARMEN_LIVE_SAMPLE_RATE
