"""Banana Boy API usage tracking — verifies BananaBoyUsage rows are written
for both the text /chat and voice /voice/chat endpoints with correct
provider/model/tokens/cost fields and prompt payloads.
"""
import io
from types import SimpleNamespace
from unittest.mock import patch

from app.banana_boy.pricing import (
    anthropic_cost,
    tts_cost,
    whisper_cost,
)
from app.models import BananaBoyUsage, ChatMessage


# --- Pricing module unit tests --------------------------------------------------


def test_anthropic_cost_known_model():
    # 1M input tokens -> $1.00 for haiku 4.5
    assert anthropic_cost("claude-haiku-4-5-20251001", input_tokens=1_000_000) == 1.00
    # 1M output tokens -> $5.00
    assert anthropic_cost("claude-haiku-4-5-20251001", output_tokens=1_000_000) == 5.00
    # Cache reads are 1/10th of input price.
    assert anthropic_cost("claude-haiku-4-5-20251001",
                          cache_read_tokens=1_000_000) == 0.10


def test_anthropic_cost_unknown_model_returns_none():
    assert anthropic_cost("claude-opus-99", input_tokens=1000) is None


def test_whisper_cost_per_minute():
    # 60 seconds -> $0.006
    assert whisper_cost("whisper-1", 60.0) == 0.006
    assert whisper_cost("whisper-1", None) is None


def test_tts_cost_per_million_chars():
    # gpt-4o-mini-tts @ $0.60/M chars; 1M chars -> $0.60
    assert tts_cost("gpt-4o-mini-tts", 1_000_000) == 0.60
    assert tts_cost("tts-1", 1_000_000) == 15.0


# --- /chat usage row writes -----------------------------------------------------


def _fake_anthropic_response(input_tokens=120, output_tokens=40, stop_reason="end_turn",
                             text="Sure thing — here's a banana fact."):
    """Build a stand-in for client.messages.create() return value.

    We're patching `client.messages.create` directly (not generate_reply), so we
    need to mimic the SDK's response shape: an object with `.usage`, `.content`
    (list of blocks with .type='text' and .text), and `.stop_reason`.
    """
    text_block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(
        content=[text_block],
        stop_reason=stop_reason,
        usage=usage,
    )


def test_chat_writes_anthropic_usage_row(app, client, logged_in_user):
    fake = _fake_anthropic_response(input_tokens=200, output_tokens=50)
    with patch("app.banana_boy.client._get_client") as gc:
        gc.return_value.messages.create.return_value = fake
        resp = client.post("/banana-boy/chat", json={"message": "hi"})
    assert resp.status_code == 200

    with app.app_context():
        rows = BananaBoyUsage.query.all()
        assert len(rows) == 1
        r = rows[0]
        assert r.provider == "anthropic"
        assert r.operation == "chat"
        assert r.model == "claude-haiku-4-5-20251001"
        assert r.iteration == 0
        assert r.input_tokens == 200
        assert r.output_tokens == 50
        assert r.duration_ms >= 0
        # Cost = (200 * $1 + 50 * $5) / 1M
        assert abs(r.cost_usd - (200 * 1.0 + 50 * 5.0) / 1_000_000) < 1e-9
        # Linked to the assistant ChatMessage row.
        assistant = ChatMessage.query.filter_by(role="assistant").one()
        assert r.chat_message_id == assistant.id
        # Prompt was captured (now a list of system blocks).
        system_blocks = r.payload["system"]
        assert isinstance(system_blocks, list)
        assert system_blocks[0]["text"].startswith("You are Banana Boy")
        assert r.payload["messages"] == [{"role": "user", "content": "hi"}]
        assert r.payload["stop_reason"] == "end_turn"


def test_chat_failure_still_records_usage_with_no_chat_message_id(app, client, logged_in_user):
    """If Anthropic raises, generate_reply re-raises BananaBoyAPIError BEFORE
    recording usage for that failed call. The sink stays empty, so no row.
    But if a *later* iteration fails, prior iterations' usage should still be
    persisted (chat_message_id=None). Here we just verify the empty-sink path."""
    from app.banana_boy.client import BananaBoyAPIError

    with patch("app.banana_boy.routes.generate_reply", side_effect=BananaBoyAPIError("boom")):
        resp = client.post("/banana-boy/chat", json={"message": "hi"})
    assert resp.status_code == 502

    with app.app_context():
        # No usage rows because the patched generate_reply never appended any.
        assert BananaBoyUsage.query.count() == 0


# --- /voice/chat usage rows -----------------------------------------------------


def _post_audio(client, blob=b"\x00\x01\x02fake-audio", filename="voice.webm",
                mime="audio/webm"):
    return client.post(
        "/banana-boy/voice/chat",
        data={"audio": (io.BytesIO(blob), filename, mime)},
        content_type="multipart/form-data",
    )


def test_voice_writes_three_usage_rows(app, client, logged_in_user):
    fake_chat = _fake_anthropic_response(input_tokens=180, output_tokens=30,
                                          text="Banana fact.")
    with patch("app.banana_boy.client._get_client") as anth_client, \
         patch("app.banana_boy.routes.transcribe") as t_mock, \
         patch("app.banana_boy.routes.synthesize") as s_mock:
        anth_client.return_value.messages.create.return_value = fake_chat

        # transcribe: emulate the real one's usage_sink contract
        def _t(audio_bytes, *, filename, mime_type, usage_sink):
            usage_sink.append({
                "provider": "openai",
                "operation": "transcription",
                "model": "whisper-1",
                "duration_ms": 250,
                "audio_bytes": len(audio_bytes),
                "audio_seconds": 4.0,
                "cost_usd": whisper_cost("whisper-1", 4.0),
                "payload": {"filename": filename, "mime_type": mime_type,
                             "transcript": "what is in my court"},
            })
            return "what is in my court"
        t_mock.side_effect = _t

        # synthesize: same pattern
        def _s(text, *, usage_sink, already_clean=False):
            usage_sink.append({
                "provider": "openai",
                "operation": "speech",
                "model": "gpt-4o-mini-tts",
                "duration_ms": 300,
                "input_chars": len(text),
                "output_bytes": 1000,
                "cost_usd": tts_cost("gpt-4o-mini-tts", len(text)),
                "payload": {"voice": "alloy", "text": text},
            })
            return b"ID3-fake-mp3"
        s_mock.side_effect = _s

        resp = _post_audio(client)

    assert resp.status_code == 200

    with app.app_context():
        rows = BananaBoyUsage.query.order_by(BananaBoyUsage.id.asc()).all()
        # Whisper, Anthropic, TTS.
        assert [(r.provider, r.operation) for r in rows] == [
            ("openai", "transcription"),
            ("anthropic", "chat"),
            ("openai", "speech"),
        ]

        whisper, anth, tts = rows

        # Whisper
        assert whisper.model == "whisper-1"
        assert whisper.audio_bytes > 0
        assert whisper.audio_seconds == 4.0
        assert abs(whisper.cost_usd - 4.0 / 60 * 0.006) < 1e-9
        assert whisper.payload["transcript"] == "what is in my court"

        # Anthropic
        assert anth.model == "claude-haiku-4-5-20251001"
        assert anth.input_tokens == 180
        assert anth.output_tokens == 30
        assert anth.payload["messages"] == [
            {"role": "user", "content": "what is in my court"},
        ]

        # TTS
        assert tts.model == "gpt-4o-mini-tts"
        assert tts.input_chars == len("Banana fact.")
        assert tts.output_bytes == 1000

        # All three are linked to the assistant ChatMessage.
        assistant = ChatMessage.query.filter_by(role="assistant").one()
        assert {r.chat_message_id for r in rows} == {assistant.id}


def test_voice_silent_audio_still_records_whisper_usage(app, client, logged_in_user):
    """Even when no speech was detected, the Whisper call cost real money — log it."""
    def _t(audio_bytes, *, filename, mime_type, usage_sink):
        usage_sink.append({
            "provider": "openai",
            "operation": "transcription",
            "model": "whisper-1",
            "duration_ms": 100,
            "audio_bytes": len(audio_bytes),
            "audio_seconds": 1.0,
            "cost_usd": whisper_cost("whisper-1", 1.0),
            "payload": {"filename": filename, "mime_type": mime_type, "transcript": ""},
        })
        return "   "

    with patch("app.banana_boy.routes.transcribe", side_effect=_t):
        resp = _post_audio(client)
    assert resp.status_code == 422

    with app.app_context():
        rows = BananaBoyUsage.query.all()
        assert len(rows) == 1
        assert rows[0].provider == "openai"
        assert rows[0].operation == "transcription"
        assert rows[0].chat_message_id is None  # no assistant turn happened
