"""Anthropic Claude wrapper for Banana Boy with tool-use loop."""
import json

from flask import current_app

from app.banana_boy.tools import TOOL_DEFINITIONS, execute_tool
from app.logging_config import get_logger

logger = get_logger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
MAX_TOOL_ITERATIONS = 5
SYSTEM_PROMPT = (
    "You are Banana Boy, a friendly personal assistant inside the MHMW operations app. "
    "Be concise and direct. If you don't know something, say so. "
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


def generate_reply(history, extra_system_context: str = "", tool_context: dict | None = None):
    """Run the chat turn, including any tool-use round trips.

    `history` is a list of {role, content} the chat route built. `extra_system_context`
    is appended to SYSTEM_PROMPT (used by the chat route for Gmail context).
    `tool_context` carries per-request data tools may need (e.g. user_id).
    Returns the final assistant text. Raises BananaBoyAPIError on upstream failure.
    """
    tool_context = tool_context or {}
    system_prompt = SYSTEM_PROMPT
    if extra_system_context:
        system_prompt = f"{SYSTEM_PROMPT}\n\n{extra_system_context}"

    client = _get_client()
    messages = list(history)

    for iteration in range(MAX_TOOL_ITERATIONS):
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
