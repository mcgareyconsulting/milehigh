"""Recall.ai client — dispatch a notetaker bot to a meeting URL and PULL the
transcript back down post-meeting.

Short-term posture (no webhook / data-lake yet): we dispatch a bot, then poll the
bot on demand and walk bot → recording → transcript artifact → download_url to get
the transcript, which we feed into the existing `extract_into_meeting` pipeline.

Mirrors how `extract.py` wraps raw `requests`: thin functions, structured logging,
and a clear RecallError so callers can surface a useful message. Unlike the LLM
extractor there is no offline stub — a real bot needs a real API call — so these
raise on misconfiguration/failure rather than silently degrading.

API shape (async transcription, pull model):
    POST   /bot/                      dispatch; body sets recallai_streaming transcript
    GET    /bot/{id}/                 status + recording id
    GET    /recording/{id}/           transcript artifact (id, status, download_url)
    GET    /transcript/{id}/          -> data.download_url (S3 JSON, no auth)
Auth header is the raw API key: `Authorization: <RECALL_API_KEY>`.
"""
import requests

from app.config import Config as cfg
from app.logging_config import get_logger

logger = get_logger(__name__)

# Terminal "the recording is finished" bot states (latest status code).
DONE_STATES = {"done", "call_ended", "analysis_done"}
FAILED_STATES = {"fatal", "media_expired"}


class RecallError(RuntimeError):
    """Recall is misconfigured or returned an error / not-ready response."""


def _headers():
    key = cfg.RECALL_API_KEY
    if not key:
        raise RecallError("RECALL_API_KEY is not set")
    return {"Authorization": key, "content-type": "application/json"}


def _url(path):
    return f"{cfg.RECALL_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def _get(path):
    resp = requests.get(_url(path), headers=_headers(), timeout=60)
    resp.raise_for_status()
    return resp.json()


def dispatch_bot(meeting_url, *, bot_name="BB", join_at=None):
    """Send a bot to `meeting_url` with async transcription enabled. Returns bot_id.

    `join_at` (a naive-UTC datetime) schedules the bot to join at that time instead
    of immediately — used by the calendar poller so a bot invited to a future Teams
    meeting shows up when the meeting actually starts. Recall holds the bot until
    `join_at`, so we can dispatch as soon as the event appears on the calendar.
    """
    if not meeting_url or not str(meeting_url).strip():
        raise RecallError("meeting_url is required")
    body = {
        "meeting_url": str(meeting_url).strip(),
        "bot_name": (bot_name or "BB")[:100],
        # `transcript.provider` takes exactly one provider. recallai_streaming is
        # Recall's first-party transcription (most reliable on Teams). We don't wire
        # realtime_endpoints — the finished transcript still lands on the recording
        # and we PULL it post-meeting. Swap to {"meeting_captions": {}} for the free,
        # platform-captions path if transcription cost matters more than reliability.
        "recording_config": {"transcript": {"provider": {"recallai_streaming": {}}}},
    }
    if join_at is not None:
        # Recall expects ISO-8601 UTC; our datetimes are naive UTC, so append Z.
        body["join_at"] = join_at.replace(microsecond=0).isoformat() + "Z"
    resp = requests.post(_url("/bot/"), headers=_headers(), json=body, timeout=60)
    if resp.status_code >= 400:
        logger.warning("recall_dispatch_failed", status=resp.status_code, body=resp.text[:500])
        raise RecallError(f"Recall dispatch failed ({resp.status_code}): {resp.text[:200]}")
    bot_id = resp.json().get("id")
    if not bot_id:
        raise RecallError("Recall response missing bot id")
    logger.info("recall_bot_dispatched", bot_id=bot_id)
    return bot_id


def get_bot(bot_id):
    """Raw bot object — status, recording references, etc."""
    return _get(f"/bot/{bot_id}/")


def bot_status_code(bot):
    """Latest status code for a bot dict, tolerant of both response shapes."""
    changes = bot.get("status_changes") or []
    if changes:
        return (changes[-1] or {}).get("code")
    status = bot.get("status")
    return status.get("code") if isinstance(status, dict) else status


def _first_recording_id(bot):
    """Pull the recording id out of a bot, tolerant of `recordings` vs `recording`."""
    recs = bot.get("recordings")
    if isinstance(recs, list) and recs:
        return (recs[0] or {}).get("id")
    rec = bot.get("recording")
    if isinstance(rec, dict):
        return rec.get("id")
    return rec or None


def _transcript_download_url(bot_id):
    """Walk bot -> recording -> transcript artifact and return its download_url,
    or None if the transcript isn't ready yet. Defensive about response shape."""
    bot = get_bot(bot_id)
    rec_id = _first_recording_id(bot)
    if not rec_id:
        return None
    recording = _get(f"/recording/{rec_id}/")

    # Newer API exposes the artifact inline under media_shortcuts.transcript.
    shortcut = (recording.get("media_shortcuts") or {}).get("transcript")
    artifact = shortcut or recording.get("transcript")
    if not artifact:
        transcripts = recording.get("transcripts") or []
        artifact = transcripts[0] if transcripts else None
    if not artifact:
        return None

    # The artifact may carry the URL inline, or only an id we resolve separately.
    data = artifact.get("data") or {}
    if data.get("download_url"):
        return data["download_url"]
    tid = artifact.get("id")
    if not tid:
        return None
    return ((_get(f"/transcript/{tid}/").get("data")) or {}).get("download_url")


def _flatten(segments):
    """Recall transcript JSON -> speaker-labelled plain text for the extractor."""
    lines = []
    for seg in segments or []:
        name = ((seg.get("participant") or {}).get("name") or "Speaker").strip()
        text = " ".join(w.get("text", "") for w in (seg.get("words") or [])).strip()
        if text:
            lines.append(f"{name}: {text}")
    return "\n".join(lines)


def fetch_transcript_text(bot_id):
    """Pull the finished transcript for a bot as speaker-labelled text.

    Returns the transcript string, or None if it isn't ready yet (caller can retry).
    Raises RecallError on a hard failure (bad key, bot errored).
    """
    url = _transcript_download_url(bot_id)
    if not url:
        return None
    # download_url is a pre-signed S3 link — no auth header.
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    text = _flatten(resp.json())
    logger.info("recall_transcript_pulled", bot_id=bot_id, chars=len(text))
    return text or None
