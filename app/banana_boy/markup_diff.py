"""Sonnet-powered diff scan over two marked-up drawing versions.

Given a 'from' PDF and a 'to' PDF for the same release, asks Sonnet to report
the markups that were added between them: text annotations quoted verbatim,
ink and stamp annotations described spatially. Banana Boy (Haiku) calls this
through the `scan_markup_diff` tool.

No-hallucination guardrails mirror compliance.py: don't infer intent, only
report what is on the page; cite page numbers; quote text annotations
verbatim.
"""
import base64
import time

from app.banana_boy.pricing import anthropic_cost
from app.logging_config import get_logger

logger = get_logger(__name__)

SONNET_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

DIFF_PROMPT = (
    "You are a fab-drawing markup reviewer for Mile High Metal Works. "
    "Two PDF versions of the same For-Construction drawing package will be "
    "supplied as document blocks: the FIRST document is the EARLIER version "
    "('from'); the SECOND document is the LATER version ('to'). Your job is "
    "to identify the markups that were ADDED in the 'to' version relative "
    "to the 'from' version.\n\n"
    "OUTPUT FORMAT — return exactly two sections, in this order:\n\n"
    "## ADDED ANNOTATIONS\n"
    "Bulleted list, one bullet per added markup. For text annotations, use "
    "the shape: `Page N — text annotation: \"<verbatim quoted text>\"` "
    "(quote exactly what the annotation says, no paraphrasing). For ink, "
    "highlight, or stamp annotations, use the shape: `Page N — <ink|stamp|"
    "highlight>: <short spatial description, e.g. 'red circle around the "
    "stair stringer detail in the lower-right'>`. Group bullets by page.\n\n"
    "## OBSERVATIONS\n"
    "Optional. Up to 3 short bullets noting patterns the drafter may want "
    "to know — e.g. 'multiple annotations cluster on page 4', 'every added "
    "text annotation references stair tread depth'. No bullets if nothing "
    "stands out.\n\n"
    "HARD RULES — violating these is a failure:\n"
    "1. Only report markups that exist in the LATER version and NOT in the "
    "earlier version. If you are unsure whether a markup was already there, "
    "do NOT include it.\n"
    "2. Quote text annotations VERBATIM. Do not paraphrase or summarize the "
    "annotation text.\n"
    "3. Do NOT infer the drafter's intent. Do not say 'this means the "
    "drafter wants to ...'. Report only what is on the page.\n"
    "4. Cite a page number for every bullet.\n"
    "5. If there are no added markups, return `## ADDED ANNOTATIONS` with "
    "the single bullet `- (none)` and omit the OBSERVATIONS section.\n"
    "6. No prose outside the two sections. No preamble. No conclusion."
)


def _get_anthropic_client():
    # Lazy import to avoid the tools.py <-> client.py cycle.
    from app.banana_boy.client import _get_client

    return _get_client()


def scan_markup_diff_pdfs(*, from_bytes: bytes, to_bytes: bytes,
                          job: int, release: str,
                          from_version: int, to_version: int,
                          usage_sink: list | None = None) -> str:
    """Run the Sonnet markup-diff scan and return the findings text."""
    client = _get_anthropic_client()
    from_b64 = base64.b64encode(from_bytes).decode("ascii")
    to_b64 = base64.b64encode(to_bytes).decode("ascii")

    system_blocks = [{"type": "text", "text": DIFF_PROMPT}]

    user_content = [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": from_b64,
            },
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": to_b64,
            },
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                f"FROM document above is {job}-{release} drawing version "
                f"{from_version}. TO document is version {to_version}. "
                f"Identify only the annotations ADDED between them, per "
                f"the system prompt."
            ),
        },
    ]

    t0 = time.monotonic()
    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=MAX_TOKENS,
        system=system_blocks,
        messages=[{"role": "user", "content": user_content}],
    )
    duration_ms = int((time.monotonic() - t0) * 1000)

    if usage_sink is not None:
        _record_diff_usage(
            usage_sink,
            job=job, release=release,
            from_version=from_version, to_version=to_version,
            duration_ms=duration_ms,
            from_size=len(from_bytes), to_size=len(to_bytes),
            response=response,
        )

    parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


def _record_diff_usage(usage_sink, *, job, release, from_version, to_version,
                       duration_ms, from_size, to_size, response):
    u = getattr(response, "usage", None)
    input_tokens = getattr(u, "input_tokens", None) if u else None
    output_tokens = getattr(u, "output_tokens", None) if u else None
    cache_read = getattr(u, "cache_read_input_tokens", None) if u else None
    cache_creation = getattr(u, "cache_creation_input_tokens", None) if u else None

    response_text = "".join(
        getattr(b, "text", "") for b in response.content
        if getattr(b, "type", None) == "text"
    )

    usage_sink.append({
        "provider": "anthropic",
        "operation": "markup_diff_scan",
        "model": SONNET_MODEL,
        "iteration": None,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "cost_usd": anthropic_cost(
            SONNET_MODEL,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
            cache_read_tokens=cache_read or 0,
            cache_creation_tokens=cache_creation or 0,
        ),
        "payload": {
            "job": job,
            "release": release,
            "from_version": from_version,
            "to_version": to_version,
            "from_size_bytes": from_size,
            "to_size_bytes": to_size,
            "user_message": (
                f"<from pdf: {from_size} bytes> + <to pdf: {to_size} bytes> + diff instructions"
            ),
            "stop_reason": getattr(response, "stop_reason", None),
            "response_text": response_text,
        },
    })
