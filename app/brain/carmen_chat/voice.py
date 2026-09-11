"""xAI (Grok) audio client — Carmen's ears and mouth.

Carmen's *brain* stays Anthropic: the read-only tool-agent in `agent.py` is the only
thing that touches the database. This module bolts speech onto either end of it:

    mic clip --> POST /v1/stt (Grok) --> agent.run_chat --> POST /v1/tts (Grok) --> mp3

That ordering is deliberate. xAI also ships a realtime speech-to-speech WebSocket
(`wss://api.x.ai/v1/realtime`), but a Grok voice session answers with *Grok's*
knowledge, not Carmen's ~20 read-only DB tools, and Flask/gunicorn here is sync-only
with no WebSocket transport. Turn-based STT → Carmen → TTS keeps every existing tool,
conversation row, and cost metric intact and needs no new infrastructure.

Both endpoints are plain HTTPS + JSON/multipart, so this follows the repo's raw
`requests` idiom (same as `agent.py` and `app/brain/meetings/extract.py`) — no SDK.

Voices are shared across the TTS and realtime APIs. Confirmed against the live roster
(28 voices, 2026-09-11): the nine female ones are `eve` (the default), `ara`, `aurora`,
`carina`, `celeste`, `iris`, `liora`, `luna`, and `ursa`. `list_voices()` re-reads the
roster from the account, which is the authority if xAI adds or renames any.
"""
import re

import requests

from app.config import Config as cfg
from app.logging_config import get_logger

logger = get_logger(__name__)

# xAI accepts up to 100 bias terms of 50 chars each.
MAX_KEYTERMS = 100

# Domain vocabulary biased into the transcriber. Without these, job-shop speech comes back
# as "sub middle" and "fab order" as "fabulous order".
KEYTERMS = (
    "submittal", "submittals", "ball in court", "fab order", "fabrication",
    "drafting work load", "DWL", "release", "job log", "look-ahead", "lookahead",
    "galvanizing", "galvanized", "shop drawing", "field measure", "punch list",
    "install date", "ship date", "job comp", "invoiced", "Procore", "Trello",
    "MHMW", "Mile High Metal Works", "Carmen", "embed", "embeds", "handrail",
    "guardrail", "stair", "stringer", "tread", "riser", "DRR", "RFI",
)

# MediaRecorder containers we may be handed by a browser, mapped to the file extension
# xAI's transcriber keys off. Chrome records WebM/Opus (a Matroska profile — MKV is on
# xAI's supported-container list); Safari records MP4/AAC; Firefox records Ogg/Opus.
_EXT_BY_MIME = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/opus": "opus",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/flac": "flac",
    "video/webm": "webm",  # some browsers label an audio-only WebM this way
    "video/mp4": "mp4",
}


def keyterms() -> list:
    """Shop vocabulary plus the names of real people in this app.

    Names are the worst case for a transcriber with no context — "Saul" comes back as
    "Salvo", "Bill" as "build" — and a misheard name in a note is exactly the kind of
    thing nobody notices until it matters. Pulled live so a new hire is covered without
    a code change. Best-effort: a DB hiccup must never stop someone talking to Carmen.
    """
    terms = list(KEYTERMS)
    try:
        from app.models import User
        seen = {t.lower() for t in terms}
        rows = User.query.with_entities(User.first_name, User.last_name).all()
        for first, last in rows:
            for name in (first, last):
                name = (name or "").strip()
                if not name or len(name) > 50 or name.lower() in seen:
                    continue
                seen.add(name.lower())
                terms.append(name)
                if len(terms) >= MAX_KEYTERMS:
                    return terms[:MAX_KEYTERMS]
    except Exception as exc:  # noqa: BLE001 — bias terms are a nicety, not a dependency
        logger.warning("carmen_voice_keyterms_people_failed",
                       error=str(exc), error_type=type(exc).__name__)
    return terms[:MAX_KEYTERMS]


class VoiceError(RuntimeError):
    """An xAI audio call failed. Carries a user-safe message; details go to the log."""


class VoiceNotConfigured(VoiceError):
    """No xAI key / voice disabled — the UI should hide the mic rather than error."""


def is_configured() -> bool:
    return bool(cfg.CARMEN_VOICE_ENABLED and cfg.XAI_API_KEY)


def config_summary() -> dict:
    """What the client needs to decide whether to show the mic button."""
    return {
        "enabled": bool(cfg.CARMEN_VOICE_ENABLED),
        "configured": is_configured(),
        "voice_id": cfg.CARMEN_VOICE_ID,
        "language": cfg.CARMEN_VOICE_LANGUAGE,
        "max_upload_bytes": cfg.CARMEN_VOICE_MAX_UPLOAD_BYTES,
    }


def _headers() -> dict:
    return {"Authorization": f"Bearer {cfg.XAI_API_KEY}"}


def _require_key():
    if not cfg.CARMEN_VOICE_ENABLED:
        raise VoiceNotConfigured("Carmen's voice is turned off.")
    if not cfg.XAI_API_KEY:
        raise VoiceNotConfigured("Carmen's voice isn't configured yet (no xAI API key on the server).")


def extension_for(mimetype: str, filename: str = "") -> str:
    """Pick the upload extension xAI should see for a browser recording."""
    base = (mimetype or "").split(";")[0].strip().lower()
    if base in _EXT_BY_MIME:
        return _EXT_BY_MIME[base]
    ext = (filename or "").rsplit(".", 1)
    if len(ext) == 2 and 1 <= len(ext[1]) <= 5 and ext[1].isalnum():
        return ext[1].lower()
    return "webm"


# --- Speech-shaping -------------------------------------------------------------------

_CODE_FENCE = re.compile(r"```.*?```", re.S)
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
_URL = re.compile(r"https?://\S+")
_EMPHASIS = re.compile(r"(\*\*|__|\*|`|~~)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)
_BULLET = re.compile(r"^\s*[-*•]\s+", re.M)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{2,}")


def speech_text(text: str, max_chars: int = None) -> str:
    """Turn a written Carmen answer into something worth listening to.

    Markdown scaffolding (headings, bullets, emphasis, tables, URLs) reads as noise
    when spoken, and a long answer is slow and expensive to synthesize — so the text
    is stripped and then trimmed at a sentence boundary.
    """
    limit = max_chars or cfg.CARMEN_VOICE_MAX_CHARS
    t = text or ""
    t = _CODE_FENCE.sub(" ", t)
    t = _TABLE_ROW.sub(lambda m: m.group(0).strip().strip("|").replace("|", ", "), t)
    t = _LINK.sub(r"\1", t)
    t = _URL.sub("", t)
    t = _HEADING.sub("", t)
    t = _BULLET.sub("", t)
    t = _EMPHASIS.sub("", t)
    t = _WS.sub(" ", t)
    t = _BLANKS.sub("\n", t).strip()
    if len(t) <= limit:
        return t
    head = t[:limit]
    cut = max(head.rfind(". "), head.rfind("! "), head.rfind("? "), head.rfind("\n"))
    if cut > limit // 2:
        head = head[: cut + 1]
    return head.rstrip() + " That's the short version — the rest is on screen."


# --- xAI calls ------------------------------------------------------------------------

def transcribe(audio: bytes, *, mimetype: str = "", filename: str = "clip",
               language: str = None) -> dict:
    """Speech → text. Returns {text, language, duration_seconds}."""
    _require_key()
    if not audio:
        raise VoiceError("The recording was empty.")
    if len(audio) > cfg.CARMEN_VOICE_MAX_UPLOAD_BYTES:
        raise VoiceError("That recording is too long. Keep it under a couple of minutes.")

    ext = extension_for(mimetype, filename)
    data = [("format", "true"), ("language", language or cfg.CARMEN_VOICE_LANGUAGE)]
    data += [("keyterm", k) for k in keyterms()]
    try:
        resp = requests.post(
            f"{cfg.XAI_API_BASE}/stt",
            headers=_headers(),
            files={"file": (f"{filename}.{ext}", audio, mimetype or "application/octet-stream")},
            data=data,
            timeout=cfg.CARMEN_VOICE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException as exc:
        logger.error("carmen_voice_stt_failed", error=str(exc), error_type=type(exc).__name__,
                     bytes=len(audio), audio_format=ext, exc_info=True)
        raise VoiceError("Carmen couldn't hear that — the transcription service failed.") from exc

    text = (body.get("text") or "").strip()
    return {
        "text": text,
        "language": body.get("language"),
        "duration_seconds": body.get("duration"),
    }


def synthesize(text: str, *, voice_id: str = None, language: str = None) -> dict:
    """Text → speech. Returns {audio: bytes, mime: str, duration_seconds, voice_id, chars}."""
    _require_key()
    spoken = speech_text(text)
    if not spoken:
        raise VoiceError("There was nothing to say.")

    voice = voice_id or cfg.CARMEN_VOICE_ID
    payload = {
        "text": spoken,
        "voice_id": voice,
        "language": language or cfg.CARMEN_VOICE_LANGUAGE,
        "speed": cfg.CARMEN_VOICE_SPEED,
        "text_normalization": True,
        "output_format": {
            "codec": cfg.CARMEN_VOICE_CODEC,
            "sample_rate": cfg.CARMEN_VOICE_SAMPLE_RATE,
        },
    }
    if cfg.CARMEN_VOICE_CODEC == "mp3":
        payload["output_format"]["bit_rate"] = cfg.CARMEN_VOICE_BIT_RATE

    try:
        resp = requests.post(
            f"{cfg.XAI_API_BASE}/tts",
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=cfg.CARMEN_VOICE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("carmen_voice_tts_failed", error=str(exc), error_type=type(exc).__name__,
                     voice_id=voice, chars=len(spoken), exc_info=True)
        raise VoiceError("Carmen couldn't speak that — the voice service failed.") from exc

    # xAI has shipped both shapes for this endpoint: a JSON envelope carrying base64
    # audio, and raw audio bytes with an audio/* content type. Accept either.
    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type == "application/json":
        import base64
        body = resp.json()
        raw = base64.b64decode(body.get("audio") or "")
        mime = body.get("content_type") or "audio/mpeg"
        duration = body.get("duration")
    else:
        raw = resp.content
        mime = content_type or "audio/mpeg"
        duration = None

    if not raw:
        logger.error("carmen_voice_tts_empty", voice_id=voice, chars=len(spoken),
                     content_type=content_type)
        raise VoiceError("Carmen's voice came back empty.")

    return {
        "audio": raw,
        "mime": mime,
        "duration_seconds": duration,
        "voice_id": voice,
        "chars": len(spoken),
        "spoken_text": spoken,
        "truncated": len(spoken) < len((text or "").strip()),
    }


def list_voices() -> list:
    """The account's live voice roster, for picking/confirming Carmen's voice."""
    _require_key()
    try:
        resp = requests.get(f"{cfg.XAI_API_BASE}/tts/voices", headers=_headers(),
                            timeout=cfg.CARMEN_VOICE_TIMEOUT_SECONDS)
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException as exc:
        logger.error("carmen_voice_list_failed", error=str(exc),
                     error_type=type(exc).__name__, exc_info=True)
        raise VoiceError("Couldn't load the voice list from xAI.") from exc
    if isinstance(body, dict):
        return body.get("voices") or body.get("data") or []
    return body or []
