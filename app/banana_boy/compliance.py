"""Sonnet-powered fab-drawing compliance scan.

Hands a PDF up as a `document` block alongside the Division 05 KB and asks
Sonnet to return PASSING / FLAGGED / NOT_DETERMINABLE findings with verbatim
page citations. Banana Boy (Haiku) calls this through the
`scan_drawing_compliance` tool and narrates the result.

No-hallucination guardrails live in SCAN_PROMPT: every numeric finding must
quote the page callout verbatim, every rule citation must name a KB filename,
and missing dimensions go to NOT_DETERMINABLE — never inferred.
"""
import base64
import time

from app.banana_boy.knowledge_base import get_knowledge_base
from app.banana_boy.pricing import anthropic_cost
from app.logging_config import get_logger

logger = get_logger(__name__)

SONNET_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

SCAN_PROMPT = (
    "You are a fab-drawing compliance reviewer for Mile High Metal Works. "
    "You are reviewing Division 05 Miscellaneous Metals fab packages "
    "(stairs, railings, guardrails, structural steel) against the "
    "<knowledge_base> block in this system prompt — IBC, ADA, AISC, AWS, "
    "OSHA standards.\n\n"
    "OUTPUT FORMAT — return exactly three sections, in this order:\n\n"
    "## PASSING\n"
    "Bulleted list. Each bullet: `field — value (page N, callout: \"<verbatim text>\") — KB rule: <file>, <section>`\n\n"
    "## FLAGGED\n"
    "Bulleted list of items that fail or appear to fail a KB rule. Same shape "
    "as PASSING, plus a one-sentence `Why:` line stating which rule fails and "
    "by how much.\n\n"
    "## NOT_DETERMINABLE\n"
    "Bulleted list of dimensions the KB calls for that are NOT annotated on "
    "any page in this drawing package. One bullet per item, naming the field "
    "and which KB rule it relates to.\n\n"
    "HARD RULES — violating these is a failure:\n"
    "1. Every numeric value MUST cite a page number AND quote the verbatim "
    "callout text from that page. If you cannot quote a callout, the value "
    "goes in NOT_DETERMINABLE.\n"
    "2. Every rule citation MUST name a KB source filename (shown as "
    "'## Source: <filename>' headers in the knowledge_base block) and the "
    "section number from that file.\n"
    "3. Do NOT estimate. Do NOT infer dimensions from drawing geometry. Read "
    "only what is printed.\n"
    "4. If the same dimension appears with different values on different "
    "pages, list both with their citations under FLAGGED — never silently "
    "pick one.\n"
    "5. If a KB rule has no matching dimension in the drawing, it goes in "
    "NOT_DETERMINABLE — not PASSING.\n"
    "6. No prose outside the three sections. No preamble. No conclusion."
)


def _get_anthropic_client():
    # Lazy import to avoid the tools.py <-> client.py cycle.
    from app.banana_boy.client import _get_client

    return _get_client()


def scan_pdf(pdf_bytes: bytes, job: int, release: str,
             usage_sink: list | None = None) -> str:
    """Run the Sonnet compliance scan on a fab-package PDF.

    Returns the model's findings text (PASSING / FLAGGED / NOT_DETERMINABLE
    sections). When `usage_sink` is provided, one record describing this
    Sonnet call is appended (provider, model, tokens, duration, cost). The
    PDF base64 payload is replaced with a stub before being recorded so we
    don't bloat the usage table with megabytes of binary.
    """
    client = _get_anthropic_client()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    system_blocks = [
        {"type": "text", "text": SCAN_PROMPT},
    ]
    kb_text = get_knowledge_base()
    if kb_text:
        system_blocks.append({
            "type": "text",
            "text": f"<knowledge_base>\n{kb_text}\n</knowledge_base>",
            "cache_control": {"type": "ephemeral"},
        })

    user_content = [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_b64,
            },
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                f"Scan job-release {job}-{release}. Return PASSING, "
                f"FLAGGED, and NOT_DETERMINABLE sections per the "
                f"system prompt. Cite page + verbatim callout for "
                f"every numeric finding."
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
        _record_scan_usage(
            usage_sink,
            job=job, release=release,
            duration_ms=duration_ms,
            pdf_size_bytes=len(pdf_bytes),
            system_blocks=system_blocks,
            response=response,
        )

    parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


def _record_scan_usage(usage_sink, *, job, release, duration_ms,
                       pdf_size_bytes, system_blocks, response):
    """Append a single usage row for a compliance-scan Sonnet call."""
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
        "operation": "compliance_scan",
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
            "pdf_size_bytes": pdf_size_bytes,
            "system": system_blocks,
            "user_message": (
                f"<pdf document block: {pdf_size_bytes} bytes> + scan instructions"
            ),
            "stop_reason": getattr(response, "stop_reason", None),
            "response_text": response_text,
        },
    })
