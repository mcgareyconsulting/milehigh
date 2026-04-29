"""OpenAI Whisper (ASR) + TTS wrappers for Banana Boy voice mode."""
import io
import re
import time

from flask import current_app

from app.banana_boy.client import BananaBoyAPIError, BananaBoyConfigError
from app.banana_boy.pricing import tts_cost, whisper_cost
from app.logging_config import get_logger

logger = get_logger(__name__)

WHISPER_MODEL = "whisper-1"
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "ash"  # grounded, casual masculine timbre — fits a fab-shop voice
TTS_INSTRUCTIONS = (
    "Speak quick and rugged — like a foreman cutting through shop noise. "
    "Brisk, punchy pace, slight grit and rasp in the voice. Terse delivery, "
    "no drag on syllables. Casual American working-class cadence. Natural "
    "contractions ('that's', 'we're', 'gonna'). No corporate softness, no "
    "throat-clearing. Get in, say it, get out."
)
TTS_MAX_INPUT_CHARS = 4000

_CLIENT_KEY = "_banana_boy_openai_client"

_TABLE_LINE_RE = re.compile(r'^\s*\|.*\|\s*$')
_NUMBERED_LIST_RE = re.compile(r'^\s*\d+[.)]\s')
_BULLET_LIST_RE = re.compile(r'^\s*[-*+•]\s')
_SPOKEN_BLOCK_RE = re.compile(r'<spoken>(.*?)</spoken>', re.DOTALL | re.IGNORECASE)


def extract_spoken_block(text: str) -> tuple[str, str | None]:
    """Split a reply into (chat_text, spoken_text).

    The model emits a trailing <spoken>...</spoken> block in voice mode (see
    VOICE_ADDENDUM in client.py). The block is stripped from the chat text so
    users don't see the scaffolding; the inner text is what gets read aloud.

    Returns the original text + None if no block is found.
    """
    if not text:
        return text, None
    match = _SPOKEN_BLOCK_RE.search(text)
    if not match:
        return text, None
    spoken = match.group(1).strip() or None
    chat = (text[:match.start()] + text[match.end():]).strip()
    return chat, spoken


def clean_for_speech(text: str) -> str:
    """Strip data dumps so TTS reads only the synthesis prose.

    Drops markdown tables, numbered lists, and bullet lists (with their nested
    sub-bullets) — keeps the framing/summary lines around them. Also strips
    bold/italic markers, heading marks, and inline code so they don't clutter
    delivery. The TTS goal is the meta-summary, not the raw data — that's what
    the chat window is for.
    """
    if not text:
        return text

    out = []
    in_block = False  # collapses contiguous list/table rows + their trailing blank line
    for line in text.splitlines():
        if (_TABLE_LINE_RE.match(line)
                or _NUMBERED_LIST_RE.match(line)
                or _BULLET_LIST_RE.match(line)):
            in_block = True
            continue
        if in_block and not line.strip():
            in_block = False
            continue
        in_block = False
        out.append(line)

    cleaned = "\n".join(out)
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)   # bold
    cleaned = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)", r"\1", cleaned)  # italic
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)  # headings
    cleaned = re.sub(r"`([^`\n]+)`", r"\1", cleaned)     # inline code
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _get_client():
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key:
        raise BananaBoyConfigError("OPENAI_API_KEY is not configured")

    cache = current_app.extensions.setdefault(_CLIENT_KEY, {})
    client = cache.get(api_key)
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        cache.clear()
        cache[api_key] = client
    return client


def transcribe(audio_bytes: bytes, *, filename: str = "voice.webm",
               mime_type: str = "audio/webm",
               usage_sink: list | None = None) -> str:
    """Transcribe audio bytes via OpenAI Whisper. Returns the recognized text.

    If `usage_sink` is provided, appends a usage dict (model, audio_seconds,
    audio_bytes, duration_ms, cost_usd, payload).
    """
    client = _get_client()
    file_tuple = (filename, io.BytesIO(audio_bytes), mime_type)
    t0 = time.monotonic()
    try:
        # verbose_json includes audio duration so we can price the call exactly.
        result = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=file_tuple,
            response_format="verbose_json",
        )
    except Exception as exc:
        logger.error("OpenAI transcription failed", error=str(exc), exc_info=True)
        raise BananaBoyAPIError(str(exc)) from exc
    duration_ms = int((time.monotonic() - t0) * 1000)

    if isinstance(result, str):
        text = result.strip()
        audio_seconds = None
    else:
        text = (getattr(result, "text", "") or "").strip()
        audio_seconds = getattr(result, "duration", None)

    if usage_sink is not None:
        usage_sink.append({
            "provider": "openai",
            "operation": "transcription",
            "model": WHISPER_MODEL,
            "duration_ms": duration_ms,
            "audio_bytes": len(audio_bytes),
            "audio_seconds": audio_seconds,
            "cost_usd": whisper_cost(WHISPER_MODEL, audio_seconds),
            "payload": {
                "filename": filename,
                "mime_type": mime_type,
                "transcript": text,
            },
        })
    return text


def synthesize(text: str, *, usage_sink: list | None = None,
               already_clean: bool = False) -> bytes:
    """Synthesize speech from text via OpenAI TTS. Returns mp3 bytes.

    If `already_clean=True`, skip the markdown-stripping pass — used when the
    caller already extracted a model-authored <spoken> block.
    If `usage_sink` is provided, appends a usage dict (model, input_chars,
    output_bytes, duration_ms, cost_usd, payload).
    """
    if not text:
        raise BananaBoyAPIError("synthesize() called with empty text")

    payload = text.strip() if already_clean else clean_for_speech(text)
    if not payload:
        # If cleanup removed everything (response was pure data), fall back so we
        # don't return silent audio — the full reply is still in the chat window.
        payload = "Done. Check the chat for the details."

    client = _get_client()
    if len(payload) > TTS_MAX_INPUT_CHARS:
        logger.warning(
            "tts_input_truncated",
            original_chars=len(payload),
            kept_chars=TTS_MAX_INPUT_CHARS,
        )
        payload = payload[:TTS_MAX_INPUT_CHARS]

    t0 = time.monotonic()
    try:
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=payload,
            instructions=TTS_INSTRUCTIONS,
            response_format="mp3",
        )
    except Exception as exc:
        logger.error("OpenAI TTS failed", error=str(exc), exc_info=True)
        raise BananaBoyAPIError(str(exc)) from exc
    duration_ms = int((time.monotonic() - t0) * 1000)

    read = getattr(response, "read", None)
    if callable(read):
        audio = read()
    else:
        content = getattr(response, "content", None)
        if isinstance(content, (bytes, bytearray)):
            audio = bytes(content)
        else:
            raise BananaBoyAPIError("unexpected TTS response shape")

    if usage_sink is not None:
        usage_sink.append({
            "provider": "openai",
            "operation": "speech",
            "model": TTS_MODEL,
            "duration_ms": duration_ms,
            "input_chars": len(payload),
            "output_bytes": len(audio),
            "cost_usd": tts_cost(TTS_MODEL, len(payload)),
            "payload": {"voice": TTS_VOICE, "text": payload},
        })
    return audio
