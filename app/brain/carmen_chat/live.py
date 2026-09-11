"""Live (realtime) Carmen — session brokering for xAI's speech-to-speech WebSocket.

The turn-based path in `voice.py` records a clip, then answers it. This one holds an open
conversation: you talk, she talks back, and either of you can interrupt. Grok's realtime
model does the listening and the speaking *and* the reasoning — but it reasons over
**Carmen's own tools**, so the answers still come from this database.

Flask never sees the WebSocket. That matters: this app is sync gunicorn with no WS
transport, and adding one for a chat widget would be a lot of infrastructure. Instead:

    browser -> POST /voice/live/token   (Flask)  -> xAI mints a short-lived client secret
    browser -> wss://api.x.ai/v1/realtime        -> direct, authenticated with that secret
    browser -> POST /voice/live/tool    (Flask)  -> whenever Grok calls one of Carmen's tools

So the only server work is minting a token and executing read-only tool calls — both plain
HTTP requests, which Flask is perfectly happy with.

**Two channels, screen first.** Speech and text want opposite things: out loud you want one
short sentence, on screen you want the structured answer you'd get from typing. Rather than
pay for a second model call to rewrite it, the session gets a `write_to_chat` tool. She
writes the full answer through it *first*, the browser renders it immediately, and only then
does she speak a short summary over the top of it — so there is something to read while she
talks. It costs only the text tokens she was already producing: no extra audio minutes, no
second Anthropic turn.

**Accent** is prompt-only. Neither xAI voice API exposes an accent parameter, so
`CARMEN_VOICE_ACCENT` is folded into the live session instructions. That means it steers
live mode only — push-to-talk goes through `/v1/tts`, which just reads the text in the
chosen voice. A cloned voice via the Custom Voices API is the route to an accent that holds
in both modes.

**Editing is admin-only and never immediate.** Admins additionally get
`propose_release_changes`, which validates and signs a change set but writes nothing; the
write happens only when a human confirms the card on screen (see `edits.py`). The tool is
not even declared in the session for a non-admin, so a non-admin's Carmen has no vocabulary
for changing anything.

**The tool bridge is why this is safe.** The browser can ask for any tool by name, but
`tools.execute_tool` dispatches only from the fixed read-only `TOOL_EXECUTORS` map — the
same one the typed chat uses — and the acting user is taken from the Flask session, never
from the request body. A live caller can reach exactly what they could reach by typing.
"""
import requests

from app.config import Config as cfg
from app.logging_config import get_logger

from . import edits, tools, voice
from .lifecycle_prompt import build_system_prompt

logger = get_logger(__name__)

# Not a database tool — a channel. Handled entirely in the browser (see useCarmenLive),
# so it costs one tool call's worth of text and zero server round trips.
TOOL_WRITE_TO_CHAT = "write_to_chat"

_WRITE_TO_CHAT_DEF = {
    "type": "function",
    "name": TOOL_WRITE_TO_CHAT,
    "description": (
        "Post the full written answer to the on-screen chat. CALL THIS BEFORE YOU SPEAK, "
        "so the person has something to read while you talk. Required whenever the answer "
        "contains any real content: a release or submittal summary, a lookup result, more "
        "than one fact, any number, date, count, or status. Write it exactly as you would "
        "type it in a chat window — headings, bullets, bold identifiers, full precision on "
        "numbers and dates, nothing rounded or abbreviated. Then speak a one or two "
        "sentence summary of it. Skip this only for greetings and one-line replies that "
        "contain no data."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "markdown": {
                "type": "string",
                "description": "The full written answer in markdown. Complete and precise, unlike the spoken version.",
            },
        },
        "required": ["markdown"],
    },
}

# Tools the browser answers locally and does not follow with `response.create`.
CLIENT_SIDE_TOOLS = (TOOL_WRITE_TO_CHAT,)

# Spoken conversation has different rules than a chat bubble. The written prompt tells
# Carmen to lead with the answer; out loud she also has to stay short, skip the markdown
# she'd otherwise format with, and say identifiers the way a person would.
_VOICE_ADDENDUM = """

YOU ARE SPEAKING ALOUD, not writing. This changes how you answer:
- Keep it to a sentence or two unless asked for detail. No lists, no headings, no markdown
  symbols — they get read out as noise. If something really is a list, say "three things"
  and name them in a sentence.
- Say identifiers naturally: "410-271" is "four ten, two seventy-one". Dates are "next
  Tuesday, the fourth", not "2026-03-04".
- Never read a URL or a file path out loud. If you generate a look-ahead PDF, just say it's
  ready and on screen.
- Round numbers when speaking: "about forty hours", not "39.75 hours".
- Keep a brisk, natural pace. Don't trail off or pad with filler.
- If a lookup will take a moment, say so in a few words first, then go do it.
- The person can interrupt you. If they do, stop and listen — don't finish your sentence.

YOU HAVE TWO CHANNELS, AND THE SCREEN GOES FIRST. Your voice is the summary; the chat
window is the record. The order for any question with data in it is:

    look it up  ->  write_to_chat  ->  speak a short summary

Call write_to_chat BEFORE you speak, every time the answer contains a lookup result, a
summary, more than one fact, or any number, date or status. Put the complete answer there —
structure, bullets, exact identifiers, exact dates, full numbers — written the way you would
type it. THEN say one or two sentences about it out loud. Do not read the written answer
aloud; summarize it. Skip write_to_chat only for greetings and one-liners with no data.{accent_block}
"""

_EDIT_ADDENDUM = """

CORRECTION FOR THIS USER — YOU CAN MAKE CHANGES. The read-only rule above does not apply
to you here: this person is an admin, and you have propose_release_changes. How it works:

- When they ask you to change/move/set/update/add something on a release, call
  propose_release_changes with EVERY change they asked for in ONE call.
- That saves NOTHING. It puts a confirmation card on their screen showing the release, the
  project, and every change from-and-to. A human confirms it before anything is written.
- After proposing, say ONE short line out loud while they look at the card — a quick
  read-back is ideal: "one seventy, four fifty-three to Ship Planning, and a note for
  Bill." Ten words at most. Never list the changes in detail or ask "shall I confirm?";
  the card is right there and says all of it. Your speech here is heard, not written down,
  so keep it to something worth hearing with your eyes elsewhere.
- When they say "confirm", "go ahead", "yes" or "do it", that is them pressing the button
  on that card. It is NOT a new instruction to you. Do not call propose_release_changes
  again and do not ask what they want confirmed. Stay quiet; the screen is handling it.
- You will be told when a change has actually been applied. Only then say it is done, and
  say it in a few words — "done", or "that's in Ship Planning now". NEVER claim a change is
  saved before you have been told it was.
- If you are not sure which release they mean, look it up and ask BEFORE proposing. That is
  the moment to check a number, not after the card is up.
- Do not call write_to_chat for a change you proposed — the card is the written record.
- You still cannot change anything other than stage, notes, ship date and install date.

STAGES ARE NOT DATES. "Install Start" and "Install Complete" are STAGE names — so is
"Ship Planning", "Paint Complete", "Cut Start" and the rest. The install date is a separate
field. "Move it to install start" means the STAGE. Only touch install date or ship date
when they actually give you a date. If you are unsure which they mean, ask.

NOTES OVERWRITE THE CELL, and that is fine — the release's activity feed keeps every
previous note, so nothing is lost. Write the new note as the current note. Only keep the
old text as well if they explicitly say to add to it or leave it.

NOTES ARE THEIR WORDS, NOT YOURS. Put down what the person actually said, close to verbatim.
If they say "mention Bill, hey let's get Saul on this", the note is "@Bill hey let's get Saul
on this". Do not summarise it, do not re-word it into a status line, and never invent detail
— no names, places, or reasons they did not say. If you did not catch a word, ask rather than
guessing at it.

GETTING IT WRONG IS FINE, LEAVING IT WRONG IS NOT. If they correct you, call
propose_release_changes again with the CORRECTED FULL set of changes. The new card replaces
the old one, so include everything that should happen, not just the fix.
"""

_ACCENT_TEMPLATE = """

ACCENT: speak English with a {accent} accent — the rhythm and warmth of it, natural and
unforced, never a caricature. Your word choice stays plain American job-shop English; only
the delivery carries the accent. A Spanish word slips in only where it would anyway."""


class LiveNotConfigured(RuntimeError):
    """Live voice is off or unkeyed — the UI should hide the Live toggle."""


class LiveError(RuntimeError):
    """Brokering a live session failed. User-safe message; details go to the log."""


def is_configured() -> bool:
    return bool(cfg.CARMEN_LIVE_ENABLED and cfg.CARMEN_VOICE_ENABLED and cfg.XAI_API_KEY)


def can_edit(user) -> bool:
    """Spoken edits are admin-only. Checked here AND on the apply route."""
    return bool(cfg.CARMEN_EDIT_ENABLED and user is not None and getattr(user, "is_admin", False))


def config_summary(user=None) -> dict:
    return {
        "enabled": bool(cfg.CARMEN_LIVE_ENABLED),
        "configured": is_configured(),
        "can_edit": can_edit(user),
        "model": cfg.CARMEN_LIVE_MODEL,
        "voice_id": cfg.CARMEN_VOICE_ID,
        "sample_rate": cfg.CARMEN_LIVE_SAMPLE_RATE,
        "max_session_seconds": cfg.CARMEN_LIVE_MAX_SESSION_SECONDS,
        "speed": cfg.CARMEN_LIVE_SPEED,
        "reasoning_effort": cfg.CARMEN_LIVE_REASONING_EFFORT,
        "accent": (cfg.CARMEN_VOICE_ACCENT or "") or None,
    }


def realtime_tools(user=None) -> list:
    """Carmen's read-only tools, restated in xAI's `function` shape.

    Anthropic calls the schema `input_schema`; xAI calls it `parameters`. Nothing else
    differs, so the one definition list in `tools.py` stays the single source of truth —
    a tool added there is automatically reachable by voice.

    The propose-changes tool is appended only for users allowed to edit, so a read-only
    user's session has no way to name it.
    """
    out = []
    for t in tools.TOOL_DEFINITIONS:
        out.append({
            "type": "function",
            "name": t["name"],
            "description": t["description"],
            "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
        })
    out.append(_WRITE_TO_CHAT_DEF)
    if can_edit(user):
        out.append(edits.PROPOSE_TOOL_DEF)
    return out


def instructions_for(user) -> str:
    accent = (cfg.CARMEN_VOICE_ACCENT or "").strip()
    accent_block = _ACCENT_TEMPLATE.format(accent=accent) if accent else ""
    base = build_system_prompt(user) + _VOICE_ADDENDUM.format(accent_block=accent_block)
    if can_edit(user):
        # The written prompt tells her she is read-only and has no tools that change
        # anything. For an admin that is no longer true, so it has to be corrected here
        # rather than left to contradict the tool she can see.
        base += _EDIT_ADDENDUM
    return base


def session_config(user) -> dict:
    """The `session.update` payload the browser should send once the socket opens.

    Assembled server-side so the prompt and the tool list can't be edited by the client.
    """
    rate = cfg.CARMEN_LIVE_SAMPLE_RATE
    return {
        "voice": cfg.CARMEN_VOICE_ID,
        "instructions": instructions_for(user),
        "tools": realtime_tools(user),
        # The lookups do the thinking; deliberating before every reply just adds dead air.
        "reasoning": {"effort": cfg.CARMEN_LIVE_REASONING_EFFORT},
        "turn_detection": {
            "type": "server_vad",
            "silence_duration_ms": cfg.CARMEN_LIVE_SILENCE_MS,
        },
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": rate},
                # Gives us the user's words as text, so the live conversation can be
                # written into the same history the typed chat keeps. The keyterms are
                # the same shop vocabulary the clip transcriber gets — without them
                # "submittal" and job numbers come back mangled.
                "transcription": {
                    "enabled": True,
                    "language_hint": cfg.CARMEN_VOICE_LANGUAGE,
                    # Shop vocabulary + real people's names, so "Saul" doesn't land in a
                    # note as "Salvo".
                    "keyterms": voice.keyterms(),
                },
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": rate},
                "speed": cfg.CARMEN_LIVE_SPEED,
            },
        },
    }


def _extract_secret(body: dict) -> str:
    """Pull the token out of xAI's client-secret response.

    The field name isn't pinned in the docs and the endpoint is young, so accept the
    shapes in circulation (flat value/token/secret, or an OpenAI-style nested object)
    rather than hard-failing on a rename.
    """
    if not isinstance(body, dict):
        return ""
    for key in ("value", "client_secret", "secret", "token", "ephemeral_token"):
        found = body.get(key)
        if isinstance(found, str) and found:
            return found
        if isinstance(found, dict):
            nested = found.get("value") or found.get("secret") or found.get("token")
            if isinstance(nested, str) and nested:
                return nested
    return ""


def mint_client_secret() -> dict:
    """Ask xAI for a short-lived secret the browser can open the socket with.

    The real API key never leaves the server; the secret expires on its own.
    """
    if not is_configured():
        raise LiveNotConfigured("Carmen's live voice isn't configured on this server.")

    try:
        resp = requests.post(
            f"{cfg.XAI_API_BASE}/realtime/client_secrets",
            headers={"Authorization": f"Bearer {cfg.XAI_API_KEY}",
                     "Content-Type": "application/json"},
            json={"expires_after": {"seconds": cfg.CARMEN_LIVE_TOKEN_TTL_SECONDS}},
            timeout=cfg.CARMEN_VOICE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException as exc:
        logger.error("carmen_live_token_failed", error=str(exc),
                     error_type=type(exc).__name__, exc_info=True)
        raise LiveError("Couldn't start a live session — xAI didn't issue a token.") from exc

    secret = _extract_secret(body)
    if not secret:
        logger.error("carmen_live_token_unparsed", keys=sorted(body.keys())
                     if isinstance(body, dict) else None)
        raise LiveError("Couldn't start a live session — the token response wasn't understood.")

    return {
        "token": secret,
        "expires_at": (body.get("expires_at") if isinstance(body, dict) else None),
        "ttl_seconds": cfg.CARMEN_LIVE_TOKEN_TTL_SECONDS,
    }


def run_tool(name: str, arguments: dict, *, user_id: int) -> dict:
    """Execute one of Carmen's read-only tools on behalf of the live session.

    `user_id` comes from the Flask session, never from the caller, so a live session can
    only ever see what that signed-in user could see by typing the same question.
    """
    return tools.execute_tool(name, arguments or {}, context={"user_id": user_id})
