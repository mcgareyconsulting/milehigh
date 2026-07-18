"""Download a submittal drawing PDF from Procore.

Feasibility findings (2026-07-10, scripts/procore_attachment_probe.py) drive the design:
  - Attachment `download_url` values point at app.procore.com (the web app) and 401 for
    API tokens — unusable. Don't build on them.
  - The API way is POST /rest/v1.0/document_markup_downloadable_pdfs/find_or_create with a
    Procore-Company-Id header and body {item_id, item_type, attachment_id, project_id}
    (the same ids embedded in the attachment's viewer/download URL). It is ASYNC: the first
    POST starts the render, and re-POSTing the same body returns a download URL once the PDF
    is ready. We then GET that URL for the bytes.
  - Our ProcoreAPI session client does NOT send the Procore-Company-Id header, so this module
    makes its own authenticated requests (mirroring app/procore/procore.py:get_workflow_data).

Public API:
  find_submittal_drawing_refs(project_id, submittal_id) -> [AttachmentRef, ...]
  download_markup_pdf(project_id, item_id, item_type, attachment_id, company_id=None) -> bytes | None
  download_submittal_drawing(project_id, submittal_id, ref=None) -> (bytes|None, filename|None, ref|None)

An AttachmentRef is a dict: {source, name, item_id, item_type, attachment_id, project_id,
company_id}. `source` is "originating" (the submitter's drawing, item_type SubmittalLog) or
"approver" (a reviewer's marked-up Final PDF Pack, item_type SubmittalLogApprover).
"""
import time
from urllib.parse import urlparse, parse_qs

import requests

from app.config import Config as cfg
from app.procore.procore_auth import get_access_token
from app.logging_config import get_logger

logger = get_logger(__name__)

API_HOST = (cfg.PROD_PROCORE_BASE_URL or "https://api.procore.com").rstrip("/")
MARKUP_PDF_PATH = "/rest/v1.0/document_markup_downloadable_pdfs/find_or_create"

# id params Procore embeds in an attachment's viewer/download URL.
_ID_PARAMS = ("attachment_id", "item_id", "item_type", "project_id")

# Async render polling.
_POLL_MAX = 30
_POLL_INTERVAL_S = 4
_REQUEST_TIMEOUT_S = 90
_DOWNLOAD_TIMEOUT_S = 120


def _headers(company_id, *, json_body=False):
    h = {"Authorization": f"Bearer {get_access_token()}", "Accept": "application/json"}
    if company_id:
        h["Procore-Company-Id"] = str(company_id)
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _ids_from_url(url):
    """Pull the {attachment_id, item_id, item_type, project_id} + company_id Procore
    embeds in an attachment's viewer/download URL."""
    if not url:
        return {}
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    out = {k: q[k][0] for k in _ID_PARAMS if k in q}
    # company id lives in the path: /companies/<id>/...
    for i, seg in enumerate(parsed.path.split("/")):
        if seg == "companies" and i + 1 < len(parsed.path.split("/")):
            nxt = parsed.path.split("/")[i + 1]
            if nxt.isdigit():
                out["company_id"] = nxt
    return out


def _looks_like_pdf(att):
    name = (att.get("name") or att.get("filename") or "").lower()
    ctype = (att.get("content_type") or att.get("mime_type") or "").lower()
    return name.endswith(".pdf") or "pdf" in ctype


def _ref_from_attachment(att, source, project_id):
    """Build an AttachmentRef from a Procore attachment object, or None if we can't
    recover the ids needed to download it."""
    ids = _ids_from_url(att.get("download_url")) or {}
    ids.update({k: v for k, v in (_ids_from_url(att.get("viewer_url")) or {}).items()
                if k not in ids})
    item_id = ids.get("item_id")
    item_type = ids.get("item_type")
    attachment_id = ids.get("attachment_id") or att.get("id")
    if not (item_id and item_type and attachment_id):
        return None
    return {
        "source": source,
        "name": att.get("name") or att.get("filename"),
        "item_id": int(item_id),
        "item_type": item_type,
        "attachment_id": int(attachment_id),
        "project_id": int(ids.get("project_id") or project_id),
        "company_id": ids.get("company_id") or str(cfg.PROD_PROCORE_COMPANY_ID or ""),
    }


def find_submittal_drawing_refs(project_id, submittal_id):
    """Enumerate downloadable drawing attachments on a submittal.

    Works on any revision (each Procore submittal revision has its own id; this reads
    whatever revision `submittal_id` points at). One drawing can appear multiple times in
    workflow_data — once as the submitter's clean copy (`is_originating_attachment: True`)
    and once per approver markup (False) — but those variants share the same
    (item_id, attachment_id), so we dedup on that and keep one ref per drawing, preferring
    the originating copy. Returns originating drawings first, then approver-only ones. PDFs
    only. Makes two GETs (the submittal + its workflow_data), no downloads.
    """
    refs = []
    seen = {}  # (item_id, attachment_id) -> ref

    def add(att, default_source):
        if not (isinstance(att, dict) and _looks_like_pdf(att)):
            return
        # is_originating_attachment, when present, is the truth for source labeling.
        orig = att.get("is_originating_attachment")
        source = "originating" if orig is True else ("approver" if orig is False
                                                     else default_source)
        ref = _ref_from_attachment(att, source, project_id)
        if not ref:
            return
        key = (ref["item_id"], ref["attachment_id"])
        if key in seen:
            # Same underlying drawing seen again — upgrade the label to originating if this
            # variant is the clean copy.
            if source == "originating":
                seen[key]["source"] = "originating"
            return
        seen[key] = ref
        refs.append(ref)

    sub = _request_json(
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}",
        company_id=cfg.PROD_PROCORE_COMPANY_ID,
    )
    if isinstance(sub, dict):
        for att in sub.get("attachments") or []:
            add(att, "originating")

    wf = _request_json(
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}/workflow_data",
        company_id=cfg.PROD_PROCORE_COMPANY_ID,
    )
    if isinstance(wf, dict):
        for att in wf.get("attachments") or []:
            add(att, "approver")

    # Submitter's clean drawings first.
    refs.sort(key=lambda r: 0 if r["source"] == "originating" else 1)
    logger.info("procore_submittal_drawings_found", project_id=project_id,
                submittal_id=submittal_id, count=len(refs),
                sources=[r["source"] for r in refs])
    return refs


def _request_json(url, company_id=None):
    try:
        resp = requests.get(url, headers=_headers(company_id), timeout=_REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json() if resp.text else None
    except requests.RequestException as exc:
        logger.error("procore_attachment_get_failed", url=url, error=str(exc),
                     error_type=type(exc).__name__, exc_info=True)
        return None


def _find_download_url(data):
    """Recursively find the first http(s) URL in a find_or_create response."""
    if isinstance(data, str) and data.startswith("http"):
        return data
    if isinstance(data, dict):
        for k in ("download_url", "url", "file_url", "pdf_url"):
            v = data.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for v in data.values():
            found = _find_download_url(v)
            if found:
                return found
    if isinstance(data, list):
        for v in data:
            found = _find_download_url(v)
            if found:
                return found
    return None


def _download_bytes(url, company_id):
    """GET a (possibly signed) download URL and return PDF bytes, or None."""
    # Signed URLs may reject an Authorization header; try with our creds, then bare.
    for hdrs in (_headers(company_id), {}):
        try:
            resp = requests.get(url, headers=hdrs, stream=True, allow_redirects=True,
                                timeout=_DOWNLOAD_TIMEOUT_S)
        except requests.RequestException as exc:
            logger.error("procore_pdf_download_failed", error=str(exc),
                         error_type=type(exc).__name__, exc_info=True)
            continue
        if resp.status_code != 200:
            resp.close()
            continue
        content = resp.content
        if content[:5] == b"%PDF-":
            return content
        resp.close()
    logger.error("procore_pdf_download_no_pdf", host=urlparse(url).netloc)
    return None


def download_markup_pdf(project_id, item_id, item_type, attachment_id, company_id=None,
                        *, poll_max=_POLL_MAX, poll_interval=_POLL_INTERVAL_S):
    """Render + download one submittal-attachment PDF via find_or_create (async).

    Returns the PDF bytes, or None on failure. Polls the endpoint until it returns a
    download URL (the render is server-side and takes a few seconds).
    """
    company_id = company_id or cfg.PROD_PROCORE_COMPANY_ID
    body = {
        "item_id": int(item_id),
        "item_type": item_type,
        "attachment_id": int(attachment_id),
        "project_id": int(project_id),
    }
    url = f"{API_HOST}{MARKUP_PDF_PATH}"

    for attempt in range(1, poll_max + 1):
        try:
            resp = requests.post(url, headers=_headers(company_id, json_body=True),
                                 json=body, timeout=_REQUEST_TIMEOUT_S)
        except requests.RequestException as exc:
            logger.error("procore_markup_pdf_post_failed", item_id=item_id,
                         item_type=item_type, error=str(exc),
                         error_type=type(exc).__name__, exc_info=True)
            return None

        # 202 Accepted = the render is in progress; 200/201 = done. The download URL
        # appears (url != null) once rendering completes. Anything else is a real error.
        if resp.status_code not in (200, 201, 202):
            logger.error("procore_markup_pdf_bad_status", item_id=item_id,
                         item_type=item_type, attachment_id=attachment_id,
                         status=resp.status_code, body=(resp.text or "")[:300])
            return None

        try:
            data = resp.json()
        except ValueError:
            data = None
        download_url = _find_download_url(data)
        if download_url:
            logger.info("procore_markup_pdf_ready", item_id=item_id, item_type=item_type,
                        attempts=attempt)
            return _download_bytes(download_url, company_id)

        # No URL yet — still rendering. A populated error_message/has_failed means give up.
        if isinstance(data, dict) and (data.get("error_message") or data.get("has_failed")
                                       or data.get("error")):
            logger.error("procore_markup_pdf_render_failed", item_id=item_id,
                         item_type=item_type, body=(resp.text or "")[:300])
            return None
        logger.debug("procore_markup_pdf_processing", item_id=item_id, attempt=attempt,
                     status=(data or {}).get("status") if isinstance(data, dict) else None)
        time.sleep(poll_interval)

    logger.error("procore_markup_pdf_timeout", item_id=item_id, item_type=item_type,
                 polls=poll_max)
    return None


def download_submittal_drawing(project_id, submittal_id, ref=None):
    """Convenience: resolve a submittal's best drawing attachment and download it.

    Pass an explicit `ref` (from find_submittal_drawing_refs) to target a specific
    attachment; otherwise the first originating drawing is used, falling back to the first
    approver markup. Returns (pdf_bytes|None, filename|None, ref|None).
    """
    if ref is None:
        refs = find_submittal_drawing_refs(project_id, submittal_id)
        if not refs:
            return None, None, None
        ref = refs[0]  # originating sorts before approver in find_submittal_drawing_refs

    pdf = download_markup_pdf(
        ref["project_id"], ref["item_id"], ref["item_type"], ref["attachment_id"],
        company_id=ref.get("company_id"),
    )
    return pdf, (ref.get("name") if pdf else None), ref
