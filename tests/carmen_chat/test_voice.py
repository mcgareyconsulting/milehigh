"""Carmen voice-to-voice: speech shaping, upload labelling, and the turn route.

The xAI calls themselves are always mocked — these tests prove the wiring around them:
the spoken turn runs the same read-only agent as the typed chat, persists the same rows,
and degrades to a written answer when the voice service is unavailable.
"""
import io
from unittest.mock import patch

import pytest

from app.brain.carmen_chat import voice
from app.config import Config
from app.models import CarmenChatConversation, CarmenChatMessage


_CANNED = {
    "configured": True,
    "answer": "Release 290-153 is in FABRICATION.",
    "metrics": {
        "model": "claude-sonnet-5", "input_tokens": 200, "output_tokens": 25,
        "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.001,
        "duration_ms": 900, "tool_calls": 1, "request_ids": ["req_v1"],
    },
    "artifacts": [],
}

_SPOKEN = {
    "audio": b"ID3fake-mp3-bytes",
    "mime": "audio/mpeg",
    "duration_seconds": 3.2,
    "voice_id": "eve",
    "chars": 34,
    "spoken_text": _CANNED["answer"],
    "truncated": False,
}


@pytest.fixture
def voice_on(monkeypatch):
    monkeypatch.setattr(Config, "CARMEN_VOICE_ENABLED", True)
    monkeypatch.setattr(Config, "XAI_API_KEY", "xai-test-key")
    return Config


def _clip():
    return {"audio": (io.BytesIO(b"fake-audio"), "clip.webm", "audio/webm")}


# --- speech shaping -------------------------------------------------------------------

def test_speech_text_strips_markdown_scaffolding():
    out = voice.speech_text(
        "## Status\n- **290-153** is in `FABRICATION`\n- Ship date [see PDF](https://x/y.pdf)\n"
    )
    assert "#" not in out and "*" not in out and "`" not in out
    assert "https://" not in out
    assert "290-153 is in FABRICATION" in out
    assert "see PDF" in out


def test_speech_text_truncates_at_a_sentence_boundary():
    body = "Sentence one is here. " * 40  # well past the cap
    out = voice.speech_text(body, max_chars=200)
    assert len(out) < len(body)
    assert "That's the short version" in out
    # The cut lands after a sentence, not mid-word.
    assert out.split(" That's the short version")[0].endswith(".")


def test_speech_text_leaves_short_plain_text_alone():
    assert voice.speech_text("Three releases are in fabrication.") == "Three releases are in fabrication."


def test_extension_for_maps_browser_containers():
    assert voice.extension_for("audio/webm;codecs=opus") == "webm"
    assert voice.extension_for("audio/mp4") == "mp4"
    assert voice.extension_for("audio/ogg;codecs=opus") == "ogg"
    assert voice.extension_for("", "recording.wav") == "wav"
    assert voice.extension_for("application/octet-stream") == "webm"


# --- configuration gate ---------------------------------------------------------------

def test_config_reports_unconfigured_without_a_key(bb_client, monkeypatch):
    monkeypatch.setattr(Config, "XAI_API_KEY", None)
    body = bb_client.get("/brain/carmen-chat/voice/config").get_json()
    assert body["configured"] is False


def test_config_reports_configured_with_a_key(bb_client, voice_on):
    body = bb_client.get("/brain/carmen-chat/voice/config").get_json()
    assert body["configured"] is True
    assert body["voice_id"] == Config.CARMEN_VOICE_ID


def test_voice_turn_requires_access(no_access_client):
    resp = no_access_client.post("/brain/carmen-chat/voice", data=_clip(),
                                 content_type="multipart/form-data")
    assert resp.status_code == 403


def test_voice_turn_503_when_not_configured(bb_client, monkeypatch):
    monkeypatch.setattr(Config, "XAI_API_KEY", None)
    resp = bb_client.post("/brain/carmen-chat/voice", data=_clip(),
                          content_type="multipart/form-data")
    assert resp.status_code == 503


def test_voice_turn_requires_an_audio_file(bb_client, voice_on):
    resp = bb_client.post("/brain/carmen-chat/voice", data={},
                          content_type="multipart/form-data")
    assert resp.status_code == 400


# --- the turn -------------------------------------------------------------------------

def test_voice_turn_transcribes_answers_and_speaks(app, bb_client, bb_user, voice_on):
    with patch.object(voice, "transcribe", return_value={"text": "what's up with 290-153", "language": "en", "duration_seconds": 2.0}), \
         patch.object(voice, "synthesize", return_value=dict(_SPOKEN)), \
         patch("app.brain.carmen_chat.agent.run_chat", return_value=_CANNED):
        resp = bb_client.post("/brain/carmen-chat/voice", data=_clip(),
                              content_type="multipart/form-data")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["transcript"] == "what's up with 290-153"
    assert data["assistant_message"]["content"] == _CANNED["answer"]
    assert data["audio"]["mime"] == "audio/mpeg"
    assert data["audio"]["data_base64"]  # base64 of the mp3 bytes
    assert set(data["voice_timings"]) == {"stt_ms", "agent_ms", "tts_ms"}

    # The spoken turn lands in the same conversation history as a typed one.
    with app.app_context():
        convos = CarmenChatConversation.query.filter_by(user_id=bb_user.id).all()
        assert len(convos) == 1
        msgs = CarmenChatMessage.query.filter_by(conversation_id=convos[0].id).all()
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[0].content == "what's up with 290-153"


def test_voice_turn_continues_an_existing_conversation(app, bb_client, bb_user, voice_on):
    with patch.object(voice, "transcribe", return_value={"text": "first question", "language": "en", "duration_seconds": 1.0}), \
         patch.object(voice, "synthesize", return_value=dict(_SPOKEN)), \
         patch("app.brain.carmen_chat.agent.run_chat", return_value=_CANNED):
        first = bb_client.post("/brain/carmen-chat/voice", data=_clip(),
                               content_type="multipart/form-data").get_json()

        data = dict(_clip())
        data["conversation_id"] = str(first["conversation_id"])
        second = bb_client.post("/brain/carmen-chat/voice", data=data,
                                content_type="multipart/form-data").get_json()

    assert second["conversation_id"] == first["conversation_id"]
    with app.app_context():
        assert CarmenChatConversation.query.filter_by(user_id=bb_user.id).count() == 1


def test_voice_turn_422_on_silence(bb_client, voice_on):
    with patch.object(voice, "transcribe", return_value={"text": "  ", "language": "en", "duration_seconds": 0.4}), \
         patch("app.brain.carmen_chat.agent.run_chat", return_value=_CANNED) as agent:
        resp = bb_client.post("/brain/carmen-chat/voice", data=_clip(),
                              content_type="multipart/form-data")
    assert resp.status_code == 422
    agent.assert_not_called()  # nothing is asked of Carmen when nothing was heard


def test_voice_turn_falls_back_to_text_when_tts_fails(app, bb_client, bb_user, voice_on):
    """A synthesis failure must not lose the answer — it is already written and saved."""
    with patch.object(voice, "transcribe", return_value={"text": "status of 290-153", "language": "en", "duration_seconds": 1.5}), \
         patch.object(voice, "synthesize", side_effect=voice.VoiceError("voice service down")), \
         patch("app.brain.carmen_chat.agent.run_chat", return_value=_CANNED):
        resp = bb_client.post("/brain/carmen-chat/voice", data=_clip(),
                              content_type="multipart/form-data")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["audio"] is None
    assert data["voice_error"] == "voice service down"
    assert data["assistant_message"]["content"] == _CANNED["answer"]
    with app.app_context():
        assert CarmenChatMessage.query.count() == 2


def test_voice_turn_502_when_transcription_fails(bb_client, voice_on):
    with patch.object(voice, "transcribe", side_effect=voice.VoiceError("stt down")):
        resp = bb_client.post("/brain/carmen-chat/voice", data=_clip(),
                              content_type="multipart/form-data")
    assert resp.status_code == 502


# --- speak-only -----------------------------------------------------------------------

def test_speak_returns_an_audio_envelope(bb_client, voice_on):
    with patch.object(voice, "synthesize", return_value=dict(_SPOKEN)):
        resp = bb_client.post("/brain/carmen-chat/voice/speak", json={"text": "hello there"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["mime"] == "audio/mpeg"
    assert body["voice_id"] == "eve"


def test_speak_requires_text(bb_client, voice_on):
    assert bb_client.post("/brain/carmen-chat/voice/speak", json={"text": " "}).status_code == 400


def test_voices_roster_rejects_non_admins(bb_client, voice_on):
    assert bb_client.get("/brain/carmen-chat/voice/voices").status_code == 403


def test_voices_roster_returns_the_live_list_for_admins(bb_admin_client, voice_on):
    with patch.object(voice, "list_voices", return_value=[{"voice_id": "eve"}]):
        resp = bb_admin_client.get("/brain/carmen-chat/voice/voices")
    assert resp.status_code == 200
    assert resp.get_json()["voices"] == [{"voice_id": "eve"}]
    assert resp.get_json()["current"] == Config.CARMEN_VOICE_ID
