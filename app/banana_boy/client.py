"""Anthropic Claude wrapper for Banana Boy with tool-use loop."""
import json
import time

from flask import current_app

from app.banana_boy.pricing import anthropic_cost
from app.banana_boy.tools import TOOL_DEFINITIONS, execute_tool
from app.logging_config import get_logger

logger = get_logger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
MAX_TOOL_ITERATIONS = 5
SYSTEM_PROMPT = (
    "You are Banana Boy, a friendly personal assistant inside the MHMW operations app. "
    "Talk like the crew you work with — fab shop and field guys, blue-collar, "
    "American working-class. Be concise and direct. Use contractions ('that's', "
    "'we're', 'you've got'). Skip corporate filler ('I'd be happy to', "
    "'Certainly,', 'I have identified...') — just answer. Plain words over "
    "fancy ones. No emojis. If you don't know something, say so. "
    "When the user asks about a specific job, release, or project, call the "
    "search tools rather than guessing. Identifiers look like '410-271' "
    "(job-release) or just '410' (job). "
    "For change-history questions ('what happened to', 'when did stage change', "
    "'who released it', 'show me the changelog'), call get_release_history "
    "with job and release. When the user wants the full picture for a "
    "release, call search_jobs_by_identifier AND get_release_history in the "
    "same turn. "
    "SUBMITTALS DISPATCH: search_submittals fires ONLY when the user "
    "explicitly says 'submittals' or asks ball-in-court / ownership / "
    "'on my plate' / 'in my court' / 'what should I work on' / 'to-do' "
    "questions. Bare project or identifier queries are release-only. "
    "Examples — "
    "'Tell me about 440-271' → search_jobs_by_identifier only. "
    "'Tell me about Lennar Columbine' → search_jobs_by_project_name only. "
    "'Project 350' → search_jobs_by_identifier(\"350\") only. "
    "'Submittals for 350' → search_submittals(project_number=\"350\") only. "
    "'Submittals for Lennar' → search_submittals(project_name=\"Lennar\") only. "
    "'Pull submittals AND releases for 350' → BOTH "
    "search_jobs_by_identifier(\"350\") and search_submittals(project_number=\"350\"). "
    "'What submittals does Daniel have?' → search_submittals(ball_in_court=\"Daniel\"). "
    "'What's in my court?' / 'On my plate?' / 'What's on my to-do?' / "
    "'What should I be working on today?' → "
    "search_submittals(ball_in_court=<your first_name from the Current user "
    "block in the system context>). These are ball-in-court questions about "
    "MY submittals — call search_submittals, NOT get_my_notifications. "
    "URGENCY: 'what's urgent', 'urgent submittals', 'priority submittals', "
    "'what's hot', 'rush jobs' → search_submittals(urgent_only=true). "
    "Combine with other filters when asked, e.g. 'urgent ones in my court' → "
    "search_submittals(ball_in_court=<first_name>, urgent_only=true), "
    "'urgent on Lennar' → search_submittals(project_name=\"Lennar\", urgent_only=true). "
    "Urgency is defined by order_number < 1; lower is more urgent. "
    "Do not infer that 'project X' alone means 'show me submittals too'. "
    "NOTIFICATIONS DISPATCH: call get_my_notifications ONLY when the user "
    "asks specifically about mentions, notifications, '@me', alerts, or "
    "'what's new for me'. Do NOT call it for ball-in-court / on-my-plate "
    "questions — those go to search_submittals as above. "
    "EMAIL RULES: When the user asks you to send or write an email, ALWAYS "
    "call create_email_draft first — never claim to have sent without a "
    "draft. After drafting, summarize the draft (To, Subject, Body) and ask "
    "the user to confirm. Only call send_email_draft AFTER an explicit, "
    "unambiguous confirmation in the most recent user message (e.g. 'yes "
    "send it', 'go ahead'). If the user's intent is unclear, ask. If a tool "
    "result has needs_reconnect=true, tell the user to click 'Connect Gmail' "
    "to grant draft/send permission."
)

VOICE_ADDENDUM = (
    "VOICE MODE: This reply will also be read aloud. Write the chat reply "
    "as you normally would (tables, bullets, and data dumps are fine — those "
    "go in the chat window). At the very end, append a single "
    "<spoken>...</spoken> block containing a short, plain-prose summary that "
    "will be the ONLY thing read aloud. Rules for the spoken block: "
    "1–4 sentences; no markdown, no bullets, no list symbols, no headings; "
    "lead with the headline, then call out the 1–2 most important specifics "
    "(names, counts, standout numbers). If the chat reply is already a "
    "short conversational answer, still wrap that text in <spoken> so it "
    "is what gets spoken. Always include the <spoken> block — never omit it "
    "in voice mode."
)


class BananaBoyConfigError(RuntimeError):
    """Raised when the Anthropic API key is missing."""


class BananaBoyAPIError(RuntimeError):
    """Raised when the upstream Anthropic call fails."""


_CLIENT_KEY = "_banana_boy_anthropic_client"


def _get_client():
    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise BananaBoyConfigError("ANTHROPIC_API_KEY is not configured")

    cache = current_app.extensions.setdefault(_CLIENT_KEY, {})
    client = cache.get(api_key)
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        cache.clear()
        cache[api_key] = client
    return client


def _block_to_dict(block):
    """Convert an Anthropic content block (text/tool_use) to a plain dict."""
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": block.text}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return block


def _extract_text(content_blocks):
    parts = [b.text for b in content_blocks if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


def _record_anthropic_usage(usage_sink, *, iteration, duration_ms, system_prompt,
                            messages_sent, response):
    """Append a usage dict to usage_sink describing this Anthropic call."""
    if usage_sink is None:
        return
    u = getattr(response, "usage", None)
    input_tokens = getattr(u, "input_tokens", None) if u else None
    output_tokens = getattr(u, "output_tokens", None) if u else None
    cache_read = getattr(u, "cache_read_input_tokens", None) if u else None
    cache_creation = getattr(u, "cache_creation_input_tokens", None) if u else None

    response_blocks = [_block_to_dict(b) for b in response.content]

    usage_sink.append({
        "provider": "anthropic",
        "operation": "chat",
        "model": HAIKU_MODEL,
        "iteration": iteration,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "cost_usd": anthropic_cost(
            HAIKU_MODEL,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
            cache_read_tokens=cache_read or 0,
            cache_creation_tokens=cache_creation or 0,
        ),
        "payload": {
            "system": system_prompt,
            "messages": messages_sent,
            "stop_reason": getattr(response, "stop_reason", None),
            "response_blocks": response_blocks,
        },
    })


def generate_reply(history, extra_system_context: str = "", tool_context: dict | None = None,
                   usage_sink: list | None = None, voice_mode: bool = False):
    """Run the chat turn, including any tool-use round trips.

    `history` is a list of {role, content} the chat route built. `extra_system_context`
    is appended to SYSTEM_PROMPT (used by the chat route for Gmail context).
    `tool_context` carries per-request data tools may need (e.g. user_id).
    If `usage_sink` is provided, one dict per Anthropic API call is appended
    describing tokens, duration, prompt sent and response.
    `voice_mode=True` appends VOICE_ADDENDUM so the model emits a trailing
    <spoken>...</spoken> block for the TTS layer.
    Returns the final assistant text. Raises BananaBoyAPIError on upstream failure.
    """
    tool_context = tool_context or {}
    system_prompt = SYSTEM_PROMPT
    if voice_mode:
        system_prompt = f"{system_prompt}\n\n{VOICE_ADDENDUM}"
    if extra_system_context:
        system_prompt = f"{system_prompt}\n\n{extra_system_context}"

    client = _get_client()
    messages = list(history)

    for iteration in range(MAX_TOOL_ITERATIONS):
        # Snapshot the messages we're about to send (deep enough that subsequent
        # appends don't mutate what we record).
        messages_sent = json.loads(json.dumps(messages, default=str))
        t0 = time.monotonic()
        try:
            response = client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )
        except Exception as exc:
            logger.error("Anthropic API call failed", error=str(exc), exc_info=True)
            raise BananaBoyAPIError(str(exc)) from exc
        duration_ms = int((time.monotonic() - t0) * 1000)

        _record_anthropic_usage(
            usage_sink,
            iteration=iteration,
            duration_ms=duration_ms,
            system_prompt=system_prompt,
            messages_sent=messages_sent,
            response=response,
        )

        if response.stop_reason != "tool_use":
            text = _extract_text(response.content)
            if not text:
                raise BananaBoyAPIError("empty response from Anthropic")
            return text

        assistant_blocks = [_block_to_dict(b) for b in response.content]
        messages.append({"role": "assistant", "content": assistant_blocks})

        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            logger.info(
                "banana_boy_tool_call",
                iteration=iteration,
                tool=block.name,
                input=block.input,
            )
            result = execute_tool(block.name, block.input or {}, context=tool_context)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })

        if not tool_results:
            text = _extract_text(response.content)
            if not text:
                raise BananaBoyAPIError("empty response from Anthropic")
            return text

        messages.append({"role": "user", "content": tool_results})

    raise BananaBoyAPIError("exceeded tool-use iteration limit")
