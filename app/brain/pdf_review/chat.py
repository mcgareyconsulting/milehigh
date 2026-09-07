"""Carmen drawing chat — the fast path beside the heavy review (roadmap N18).

The open drawing version's PDF *is* the context, so a drafter can ask one-offs
("summarize the v3 markups", "does every hole have hardware that fits") and get an
answer in seconds instead of the minutes a full compliance review takes. Usable
before or after a review exists; when one exists its findings ride in the context
header, so "why did you flag sheet F1?" is answerable without re-reading the set.

Two shapes here are deliberate:

* **The PDF block is prompt-cached** (`cache_control: ephemeral`). Turn one pays to
  upload the drawing set; every follow-up reads it from cache at ~0.1x. Without this
  each question re-ships 1-2 MB and the feature is too expensive to ask casually,
  which defeats its whole purpose.
* **Sonnet, not Opus.** `service.py` stays the deep pass on a background thread. Chat
  answers in-request, so it takes the light model and a low effort budget.

Turns are **session-only in v1** — the client carries the history and nothing is
persisted. Spend is still ledgered per turn by the caller (`ai_usage.record`).
"""
import base64
import io
import time

import requests

from app.config import Config as cfg
from app.logging_config import get_logger

from app.brain.carmen_chat import pricing
from app.brain.pdf_review.rules import MHMW_CALLOUT_CONVENTIONS
from app.brain.pdf_review.service import MAX_PDF_BYTES, resolve_model

logger = get_logger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
REQUEST_TIMEOUT = 180

CHAT_MODEL_ALIAS = "sonnet"
MAX_TOKENS = 2048
EFFORT = "low"

MAX_HISTORY_TURNS = 20          # keep the cached prefix stable; drop the oldest beyond this
MAX_MESSAGE_CHARS = 4000

SYSTEM_PROMPT = (
    "You are Carmen Miranda, the drawing assistant for Mile High Metal Works, a "
    "structural-steel stair, rail, and guardrail fabricator. The attached PDF is the "
    "drawing version the user is looking at right now; answer questions about it.\n"
    "HOW TO ANSWER:\n"
    "- Be short. Two or three sentences, or a tight list. This is a chat beside a drawing, "
    "not a report — the deep compliance review is a separate tool.\n"
    "- The panel renders **bold**, `code`, and \"- \" bullet lines. Use them where they help "
    "and nothing else — headings, tables and numbered lists render as raw characters.\n"
    "- Cite the sheet label (e.g. 'F1') and quote the exact callout text you read whenever "
    "you state a dimension, a count, or a spec.\n"
    "- If the drawing does not say, say it does not say. Never infer a dimension that is not "
    "printed, and never invent a sheet.\n"
    "- ASK ONE QUESTION AT A TIME. If you need something from the user, ask for the single "
    "most useful thing and stop; do not stack up a list of questions.\n"
    "- When the CONTEXT below carries review findings, treat them as your own earlier work "
    "and answer about them directly.\n"
    "TWO DIFFERENT THINGS — never answer about one when asked about the other:\n"
    "- MARKUPS are annotations drawn ON the sheets — pen strokes, boxes, arrows, typed notes, "
    "stamps — put there by our drafters or by a GC/approver in Procore. They are part of the "
    "PDF in front of you and CONTEXT lists them page by page. Answer markup questions from "
    "the drawing and that list.\n"
    "- FINDINGS are the output of the separate code-compliance review, a different and much "
    "slower tool. Whether a review has been run has NOTHING to do with whether the drawing "
    "carries markups. If asked to summarize the markups, summarize the markups; never reply "
    "that the review has not been run.\n"
    + MHMW_CALLOUT_CONVENTIONS
)


_MARKUP_LABEL = {
    "/Ink": "pen/shape", "/FreeText": "typed note", "/Square": "box", "/Circle": "ellipse",
    "/Line": "line", "/Polygon": "polygon", "/PolyLine": "polyline", "/Stamp": "stamp",
    "/Highlight": "highlight", "/StrikeOut": "strikeout", "/Underline": "underline",
    "/Text": "sticky note", "/Popup": None,   # None = structural, not a markup
}
MAX_MARKUPS_LISTED = 40


def summarize_markups(pdf_bytes: bytes) -> list:
    """Every annotation baked into the PDF, as [{page, kind, text, key}].

    This is what "the markups" means to a reviewer — the pen strokes and typed notes on
    the sheets, whether ours or an approver's returned set. Claude can see them in the
    rendered page, but it cannot count them reliably or read a sticky note's payload, so
    we hand it the inventory. `key` is a stable-ish identity (page + kind + text + rounded
    box) used only to diff one version against the one it was saved from.

    Best-effort: a malformed PDF returns [] rather than failing the chat turn.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        out = []
        for page_no, page in enumerate(reader.pages, start=1):
            try:
                annots = page.get("/Annots") or []
            except Exception:  # noqa: BLE001
                continue
            for ref in annots:
                try:
                    a = ref.get_object()
                    subtype = str(a.get("/Subtype") or "")
                    if subtype not in _MARKUP_LABEL or _MARKUP_LABEL[subtype] is None:
                        continue
                    text = str(a.get("/Contents") or "").strip()
                    rect = [round(float(v)) for v in (a.get("/Rect") or [])]
                except Exception:  # noqa: BLE001 — one bad annotation is not a failure
                    continue
                out.append({
                    "page": page_no,
                    "kind": _MARKUP_LABEL[subtype],
                    "text": text,
                    "key": f"{page_no}|{subtype}|{text}|{rect}",
                })
        return out
    except Exception:  # noqa: BLE001
        logger.warning("carmen_drawing_chat_markup_scan_failed", exc_info=True)
        return []


def build_context_header(*, job_release=None, version=None, versions=None,
                         review=None, comments=None, markups=None, prior_keys=None) -> str:
    """A short plain-text header describing what the user has open.

    Everything here is cheap metadata — the expensive part is the PDF, which sits in
    its own cached block ahead of this. Kept out of the system prompt on purpose: the
    system prompt is stable across versions, this changes per version.
    """
    lines = ["CONTEXT (not part of the drawing — background for your answer):"]
    lines.append(f"- Job/release: {job_release or 'unknown'}")

    if version is not None:
        total = len(versions or [])
        lines.append(
            f"- Open version: v{version.version_number}"
            + (f" of {total}" if total else "")
            + (f" · {version.original_filename}" if version.original_filename else "")
            + (f" · uploaded {version.uploaded_at:%Y-%m-%d}" if version.uploaded_at else "")
        )
        if version.note:
            lines.append(f"- Version note: {version.note}")
        if version.source_version_id:
            lines.append("- This version is a markup saved on top of an earlier one.")

    # Markups first: it is the question people actually ask, and the one the model got
    # wrong when the only nearby line was "no review has been run".
    if markups is not None:
        if not markups:
            lines.append("- MARKUPS: this PDF carries no markup annotations.")
        else:
            fresh = ({m["key"] for m in markups} - set(prior_keys)) if prior_keys else None
            lines.append(
                f"- MARKUPS on this PDF: {len(markups)} annotation(s)"
                + (f", {len(fresh)} of them NEW on this version" if fresh is not None else "")
                + ". Annotations carry forward from earlier versions, so an old one still "
                "shows here."
            )
            for m in markups[:MAX_MARKUPS_LISTED]:
                new_tag = " [new on this version]" if fresh is not None and m["key"] in fresh else ""
                body = f': "{m["text"][:200]}"' if m["text"] else ""
                lines.append(f"  · p{m['page']} {m['kind']}{body}{new_tag}")
            if len(markups) > MAX_MARKUPS_LISTED:
                lines.append(f"  · (+{len(markups) - MAX_MARKUPS_LISTED} more not listed)")

    if review is not None and getattr(review, "status", None) == "complete":
        findings = review.findings or []
        lines.append(f"- FINDINGS — a Carmen code-compliance review of this version has run "
                     f"({len(findings)} findings). These are review output, not markups:")
        for i, f in enumerate(findings, start=1):
            if not isinstance(f, dict):
                continue
            bits = [f"  {i}. [{f.get('verdict') or 'n/a'}]"]
            if f.get("rule_id"):
                bits.append(str(f["rule_id"]))
            if f.get("location"):
                bits.append(f"({f['location']})")
            if f.get("issue"):
                bits.append(str(f["issue"]))
            lines.append(" ".join(bits))
    elif review is not None and getattr(review, "status", None) == "pending":
        lines.append("- FINDINGS: a code-compliance review of this version is running right now.")
    else:
        lines.append("- FINDINGS: no code-compliance review has been run on this version yet "
                     "(this says nothing about the markups above).")

    if comments:
        lines.append("- Recent comments on this version:")
        for c in comments:
            lines.append(f"  · {c.author_name}: {(c.body or '').strip()[:200]}")

    return "\n".join(lines)


def _content_blocks(pdf_bytes: bytes, context_header: str) -> list:
    """The cached turn-one payload: the drawing, then the context around it.

    `cache_control` sits on the LAST block of the prefix we want reused, so both the
    document and the header are cached together and a follow-up question re-reads
    both instead of re-uploading them.
    """
    return [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(pdf_bytes).decode("ascii"),
            },
        },
        {"type": "text", "text": context_header, "cache_control": {"type": "ephemeral"}},
    ]


def _messages(pdf_bytes: bytes, context_header: str, history: list, user_text: str) -> list:
    """Cached PDF prefix → prior turns → the new question.

    The PDF rides on the FIRST user message and every later turn appends after it, so
    the cached prefix stays byte-stable for the life of the conversation. History is
    plain text only (the client holds it); anything else is dropped.
    """
    turns = [t for t in (history or [])
             if isinstance(t, dict)
             and t.get("role") in ("user", "assistant")
             and isinstance(t.get("content"), str)
             and t["content"].strip()]
    turns = turns[-MAX_HISTORY_TURNS:]
    # A leading assistant turn would make an invalid message list.
    while turns and turns[0]["role"] != "user":
        turns.pop(0)

    blocks = _content_blocks(pdf_bytes, context_header)
    messages = []
    if turns:
        first, rest = turns[0], turns[1:]
        messages.append({"role": "user",
                         "content": blocks + [{"type": "text", "text": first["content"]}]})
        messages.extend({"role": t["role"], "content": t["content"]} for t in rest)
        messages.append({"role": "user", "content": user_text})
    else:
        messages.append({"role": "user",
                         "content": blocks + [{"type": "text", "text": user_text}]})
    return messages


def _post(messages: list, key: str, model: str):
    resp = requests.post(
        ANTHROPIC_URL,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={
            "model": model,
            "max_tokens": MAX_TOKENS,
            "output_config": {"effort": EFFORT},
            "system": [{"type": "text", "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        },
        timeout=REQUEST_TIMEOUT,
    )
    request_id = resp.headers.get("request-id") or resp.headers.get("anthropic-request-id")
    resp.raise_for_status()
    return resp.json(), request_id


def ask(pdf_bytes: bytes, context_header: str, history: list, user_text: str,
        *, version_id=None, user_id=None) -> dict:
    """One chat turn against the open drawing. Returns {configured, answer, metrics}.

    Raises `ValueError` on an empty/oversized PDF and `requests.RequestException` when
    Anthropic fails — the route turns those into 4xx/502. A missing API key is not an
    error: it returns `configured: False` so the panel renders a plain message, matching
    `carmen_chat.agent.run_chat`.
    """
    user_text = (user_text or "").strip()[:MAX_MESSAGE_CHARS]
    if not user_text:
        raise ValueError("message is required")
    if not pdf_bytes:
        raise ValueError("drawing file is empty")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("drawing is too large to chat about")

    key = cfg.ANTHROPIC_API_KEY
    if not key:
        return {
            "configured": False,
            "answer": "Carmen isn't configured yet (no Anthropic API key set on the server).",
            "metrics": {"model": "stub", "input_tokens": 0, "output_tokens": 0,
                        "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0,
                        "duration_ms": 0, "request_id": None},
        }

    model = resolve_model(CHAT_MODEL_ALIAS)
    started = time.monotonic()
    try:
        body, request_id = _post(_messages(pdf_bytes, context_header, history, user_text),
                                 key, model)
    except requests.RequestException as exc:
        logger.error("carmen_drawing_chat_failed", error=str(exc), error_type=type(exc).__name__,
                     version_id=version_id, user_id=user_id, model=model, exc_info=True)
        raise

    answer = "".join(b.get("text", "") for b in body.get("content", [])
                     if b.get("type") == "text").strip()
    if body.get("stop_reason") == "max_tokens":
        answer += "\n\n(Cut off — ask me to continue.)"

    usage = pricing.usage_from_body(body, model)
    metrics = {
        "model": usage["model"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_tokens": usage["cache_read_tokens"],
        "cache_write_tokens": usage["cache_write_tokens"],
        "cost_usd": usage["cost_usd"],
        "duration_ms": int((time.monotonic() - started) * 1000),
        "request_id": request_id,
    }
    logger.info("carmen_drawing_chat_turn", version_id=version_id, user_id=user_id,
                model=metrics["model"], request_id=request_id,
                input_tokens=metrics["input_tokens"], output_tokens=metrics["output_tokens"],
                cache_read_tokens=metrics["cache_read_tokens"],
                cache_write_tokens=metrics["cache_write_tokens"],
                cost_usd=metrics["cost_usd"], duration_ms=metrics["duration_ms"])
    return {"configured": True, "answer": answer or "(no answer)", "metrics": metrics}
