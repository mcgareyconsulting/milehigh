"""Integration tests for the /banana-boy/voice/chat endpoint."""
import base64
import io
from unittest.mock import patch

from app.banana_boy.client import BananaBoyAPIError, BananaBoyConfigError
from app.banana_boy.voice_client import clean_for_speech
from app.models import ChatMessage


def test_clean_for_speech_strips_markdown_tables():
    md = (
        "**380 — Open Submittals** (4 items waiting)\n"
        "\n"
        "| Title | Type | Ball in Court | Status |\n"
        "|-------|------|---------------|--------|\n"
        "| South/SE Balconies | Drafting Release Review | Colton Arendt | Open |\n"
        "| Garage - Roof Canopy | Submittal for GC Approval | Gary Almeida | Open |\n"
        "\n"
        "That's **7 open submittals** total. Most are with Colton."
    )
    cleaned = clean_for_speech(md)
    assert "|" not in cleaned
    assert "South/SE Balconies" not in cleaned
    assert "Colton Arendt" not in cleaned
    assert cleaned.startswith("380 — Open Submittals (4 items waiting)")
    assert "7 open submittals" in cleaned
    assert "**" not in cleaned


def test_clean_for_speech_strips_numbered_and_bullet_lists():
    md = (
        "Got 5 urgent submittals on Colton's plate, sorted hottest first:\n"
        "\n"
        "1. **Building C Structural Steel** (Alta Metro Center, 560)\n"
        "   - Status: Open | Type: Submittal for GC Approval\n"
        "   - Order: 0.5 | Due: Mar 19, 2026 | Drafting: STARTED\n"
        "   - Manager: Gary Almeida\n"
        "2. **Building B Structural Steel** (Alta Metro Center, 560)\n"
        "   - Status: Open | Type: Submittal for GC Approval\n"
        "   - Order: 0.6 | Manager: Gary Almeida\n"
        "\n"
        "The top two are the hottest — both at 0.5 and 0.6. What do you need to do?"
    )
    cleaned = clean_for_speech(md)
    assert "Building C Structural Steel" not in cleaned
    assert "Gary Almeida" not in cleaned
    assert "Order:" not in cleaned
    assert cleaned.startswith("Got 5 urgent submittals on Colton's plate")
    assert cleaned.rstrip().endswith("What do you need to do?")
    # Sanity: the synthesis prose is what's left.
    assert "hottest" in cleaned


def test_clean_for_speech_strips_headings_and_code():
    assert clean_for_speech("# Hello\n`code` world") == "Hello\ncode world"


def test_clean_for_speech_handles_pure_table_response():
    md = "| a | b |\n|---|---|\n| 1 | 2 |"
    assert clean_for_speech(md) == ""


def test_clean_for_speech_handles_pure_list_response():
    md = "1. one\n2. two\n3. three"
    assert clean_for_speech(md) == ""


def _post_audio(client, blob=b"\x00\x01\x02fake-audio", filename="voice.webm",
                mime="audio/webm"):
    return client.post(
        "/banana-boy/voice/chat",
        data={"audio": (io.BytesIO(blob), filename, mime)},
        content_type="multipart/form-data",
    )


def test_voice_requires_auth(client):
    resp = _post_audio(client)
    assert resp.status_code == 401


def test_voice_rejects_missing_audio(client, logged_in_user):
    resp = client.post("/banana-boy/voice/chat", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_voice_rejects_empty_audio(client, logged_in_user):
    resp = _post_audio(client, blob=b"")
    assert resp.status_code == 400


def test_voice_happy_path_persists_turns_and_returns_audio(app, client, logged_in_user, mock_haiku_reply):
    fake_mp3 = b"ID3-fake-mp3-bytes"
    with patch("app.banana_boy.routes.transcribe", return_value="what is in my court"), \
         patch("app.banana_boy.routes.synthesize", return_value=fake_mp3) as syn_mock:
        resp = _post_audio(client)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["transcript"] == "what is in my court"
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "Sure thing — here's a banana fact."
    assert body["audio_mime"] == "audio/mpeg"
    assert base64.b64decode(body["audio_b64"]) == fake_mp3

    # The agent was invoked with the transcribed text as the latest user turn.
    mock_haiku_reply.assert_called_once()
    history_arg = mock_haiku_reply.call_args.args[0]
    assert history_arg == [{"role": "user", "content": "what is in my court"}]

    # TTS was given the assistant reply.
    syn_mock.assert_called_once()
    assert syn_mock.call_args.args[0] == "Sure thing — here's a banana fact."

    with app.app_context():
        rows = ChatMessage.query.order_by(ChatMessage.id.asc()).all()
        assert [(r.role, r.content) for r in rows] == [
            ("user", "what is in my court"),
            ("assistant", "Sure thing — here's a banana fact."),
        ]


def test_voice_silent_audio_returns_422(app, client, logged_in_user, mock_haiku_reply):
    with patch("app.banana_boy.routes.transcribe", return_value="   "):
        resp = _post_audio(client)
    assert resp.status_code == 422

    # No turns persisted, model never called.
    mock_haiku_reply.assert_not_called()
    with app.app_context():
        assert ChatMessage.query.count() == 0


def test_voice_returns_503_when_openai_not_configured(app, client, logged_in_user):
    with patch("app.banana_boy.routes.transcribe", side_effect=BananaBoyConfigError("no key")):
        resp = _post_audio(client)
    assert resp.status_code == 503

    with app.app_context():
        assert ChatMessage.query.count() == 0


def test_voice_returns_502_on_transcription_failure(app, client, logged_in_user):
    with patch("app.banana_boy.routes.transcribe", side_effect=BananaBoyAPIError("whisper down")):
        resp = _post_audio(client)
    assert resp.status_code == 502

    with app.app_context():
        assert ChatMessage.query.count() == 0


def test_voice_degrades_to_text_when_tts_fails(app, client, logged_in_user, mock_haiku_reply):
    """If TTS fails after the reply is saved, we still return the assistant text (audio null)."""
    with patch("app.banana_boy.routes.transcribe", return_value="hello"), \
         patch("app.banana_boy.routes.synthesize", side_effect=BananaBoyAPIError("tts down")):
        resp = _post_audio(client)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["transcript"] == "hello"
    assert body["message"]["content"] == "Sure thing — here's a banana fact."
    assert body["audio_b64"] is None
    assert body["audio_mime"] is None

    # User+assistant rows are persisted regardless.
    with app.app_context():
        assert ChatMessage.query.count() == 2


def test_voice_propagates_chat_502_after_user_row_persisted(app, client, logged_in_user):
    with patch("app.banana_boy.routes.transcribe", return_value="hello"), \
         patch("app.banana_boy.routes.generate_reply", side_effect=BananaBoyAPIError("claude down")):
        resp = _post_audio(client)

    assert resp.status_code == 502
    # Same partial-failure semantics as the text endpoint: user row exists, no assistant row.
    with app.app_context():
        rows = ChatMessage.query.all()
        assert len(rows) == 1
        assert rows[0].role == "user"
        assert rows[0].content == "hello"
