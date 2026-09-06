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
  attachment_ids_from_url(url) -> {attachment_id, item_id, item_type, project_id}
  workflow_responses(payload) -> {approver_id: {response_name, approver_name, is_final_pdf}}
  response_name_of(node) -> "Final PDF Pack" | None   (flat or nested shapes)
  walk_file_objects(payload) -> [(file_dict, {approver_id, response_name, approver_name}), ...]
  raw_submittal_payloads(project_id, submittal_id) -> (submittal, workflow_data)   [debug]
  find_matching_paths(obj) -> ["$.path.to.key = value", ...]                        [debug]
  probe_attachment(project_id, submittal_id, attachment_id, item_id, item_type)     [debug]
  markup_evidence(obj) -> ["$.path = value", ...]  (markup/annotation mentions)
  download_markup_pdf(project_id, item_id, item_type, attachment_id, company_id=None) -> bytes | None
  download_submittal_drawing(project_id, submittal_id, ref=None) -> (bytes|None, filename|None, ref|None)

An AttachmentRef is a dict: {source, name, item_id, item_type, attachment_id, project_id,
company_id}. `source` is "originating" (the submitter's drawing, item_type SubmittalLog) or
"approver" (a reviewer's marked-up Final PDF Pack, item_type SubmittalLogApprover).
"""
import json
import re
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


#: Procore's workflow response name for the returned FC set. Tolerant match — Procore
#: sometimes renames the response after an FC set update.
def is_final_pdf_response_name(name) -> bool:
    """True when a distributed response's name is the Final PDF Pack row."""
    n = (name or "").strip().lower()
    return n == "final pdf pack" or ("final" in n and "pdf" in n)


#: A response name can arrive flat, or nested under an object, depending on which payload
#: and API version it came from. Procore's UI calls all of them the "response".
_RESPONSE_NAME_KEYS = ("response_name", "distributed_response_name",
                       "submittal_response_name", "workflow_response_name")
_RESPONSE_OBJECT_KEYS = ("response", "distributed_response", "submittal_response",
                         "workflow_response")


def response_name_of(node):
    """The response name on one object, flat or nested. None when it carries none."""
    if not isinstance(node, dict):
        return None
    for key in _RESPONSE_NAME_KEYS:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in _RESPONSE_OBJECT_KEYS:
        value = node.get(key)
        if isinstance(value, dict):
            name = value.get("name") or value.get("response_name") or value.get("label")
            if isinstance(name, str) and name.strip():
                return name
    return None


def _approver_name(response):
    """Best display name for whoever holds a distributed response."""
    for key in ("approver_name", "name", "submittal_approver", "approver", "user", "login_information"):
        who = response.get(key)
        if isinstance(who, dict):
            found = who.get("name") or who.get("login") or who.get("email_address")
            if found:
                return found
        elif isinstance(who, str) and who:
            return who
    return None


def workflow_responses(payload, _out=None, _depth=0):
    """{approver_id: {response_name, approver_name, is_final_pdf}} anywhere in a payload.

    This is the "Workflow Responses" block in Procore's own UI: one row per approver,
    carrying the response name ("Final PDF Pack") and the drawing they returned. It is the
    only authoritative statement of what a returned drawing *is* — the file object never
    says.

    Deliberately a walk over any dict that pairs an approver id with a response name,
    rather than a read of `last_distributed_submittal.distributed_responses` alone (where
    `procore._final_pdf_approver_ids` reads it). That one path is the *latest distribution
    round on one revision*: a pack attached and then distributed can leave the response on
    a sibling revision's payload, on the approver record, or nested as `response: {name}` —
    all of which a fixed-key read silently returns nothing for.
    """
    out = {} if _out is None else _out
    if _depth > 8:
        return out
    if isinstance(payload, list):
        for item in payload:
            workflow_responses(item, out, _depth + 1)
        return out
    if not isinstance(payload, dict):
        return out

    approver_id = None
    for key in _APPROVER_ID_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            value = value.get("id")
        if value is not None:
            approver_id = value
            break

    response_name = response_name_of(payload)
    if approver_id is None and response_name:
        # An approver record fetched on its own keys its id as plain `id`; a dict that
        # carries a response name IS the response row, so that id is the approver's.
        approver_id = payload.get("id")
    if approver_id is not None and response_name:
        # First sighting wins; a later, thinner one must not blank a name we already have.
        out.setdefault(approver_id, {
            "response_name": response_name,
            "approver_name": _approver_name(payload),
            "is_final_pdf": is_final_pdf_response_name(response_name),
        })

    for value in payload.values():
        if isinstance(value, (dict, list)):
            workflow_responses(value, out, _depth + 1)
    return out


#: Keys Procore hangs file lists off. "attachments" is the documented one; workflow
#: payloads also carry returned drawings under "documents" (and, on some responses, the
#: file sits inside the response row itself rather than in a list on the submittal).
_FILE_LIST_KEYS = ("attachments", "documents", "files", "drawings", "uploads")

#: Keys that identify the approver/response a nested file belongs to.
_APPROVER_ID_KEYS = ("submittal_approver_id", "approver_id", "submittal_approver")


def _response_context(node, inherited):
    """Approver/response facts a nested file inherits from the object holding it."""
    ctx = dict(inherited)
    for key in _APPROVER_ID_KEYS:
        value = node.get(key)
        if isinstance(value, dict):
            value = value.get("id")
        if value is not None:
            ctx["approver_id"] = value
            break
    name = response_name_of(node)
    if name:
        ctx["response_name"] = name
        ctx["approver_name"] = _approver_name(node) or ctx.get("approver_name")
    return ctx


def walk_file_objects(node, _ctx=None, _out=None, _depth=0):
    """Every file-ish dict anywhere in a Procore payload, with its response context.

    Yields (file_dict, context) where context carries the nearest enclosing approver id,
    response name and approver name. Written as a walk rather than a fixed
    `payload["attachments"]` read because Procore does not put returned drawings in one
    place: the same Final PDF Pack can arrive as a submittal attachment, as a
    workflow_data attachment, or as a *document* hanging off the approver's own response
    row. Reading one key silently dropped the others.
    """
    out = [] if _out is None else _out
    ctx = _ctx or {}
    if _depth > 8:
        return out
    if isinstance(node, list):
        for item in node:
            walk_file_objects(item, ctx, out, _depth + 1)
        return out
    if not isinstance(node, dict):
        return out

    ctx = _response_context(node, ctx)
    for key, value in node.items():
        if key in _FILE_LIST_KEYS:
            for item in (value if isinstance(value, list) else [value]):
                if isinstance(item, dict):
                    out.append((item, ctx))
                    # A file entry can itself nest further files (revisions, markups).
                    walk_file_objects(item, ctx, out, _depth + 1)
        elif isinstance(value, (dict, list)):
            walk_file_objects(value, ctx, out, _depth + 1)
    return out


def attachment_ids_from_url(url):
    """Public wrapper over the id parser: {attachment_id, item_id, item_type, project_id}.

    Callers use it to recognise a known attachment by its stored viewer URL — e.g. matching
    `Releases.viewer_url` (the Final PDF Pack the nightly FC worker linked) against the
    candidates on a submittal.
    """
    return _ids_from_url(url) or {}


def _creator_name(att):
    for key in ("created_by", "uploaded_by", "author", "login_information"):
        who = att.get(key)
        if isinstance(who, dict):
            name = who.get("name") or who.get("login") or who.get("email_address")
            if name:
                return name
        elif isinstance(who, str) and who:
            return who
    return None


def _ref_from_attachment(att, source, project_id):
    """Build an AttachmentRef from a Procore attachment object, or None if we can't
    recover the ids needed to download it.

    The download ids are required; everything after them is display metadata, present or
    absent depending on which Procore endpoint the attachment came back from. It is carried
    through as-is (never inferred) so a caller can show *what* a candidate actually is.
    """
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
        # Display metadata — may be None; never guessed.
        "viewer_url": att.get("viewer_url"),
        "created_at": att.get("created_at") or att.get("uploaded_at"),
        "updated_at": att.get("updated_at"),
        "size_bytes": att.get("byte_size") or att.get("size") or att.get("file_size"),
        "created_by": _creator_name(att),
        "approver_id": att.get("approver_id"),
        "is_originating_attachment": att.get("is_originating_attachment"),
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

    Both payloads are *walked* (see walk_file_objects) rather than read at
    `payload["attachments"]`: Procore also carries returned drawings as workflow
    `documents`, and as files nested inside an approver's own response row. Reading the one
    documented key hid those.
    """
    refs = []
    seen = {}  # (item_id, attachment_id) -> ref
    responses = {}  # approver_id -> workflow response row (fills from the submittal GET)

    def add(att, default_source, ctx=None):
        if not (isinstance(att, dict) and _looks_like_pdf(att)):
            return
        ctx = ctx or {}
        # is_originating_attachment, when present, is the truth for source labeling.
        orig = att.get("is_originating_attachment")
        source = "originating" if orig is True else ("approver" if orig is False
                                                     else default_source)
        ref = _ref_from_attachment(att, source, project_id)
        if not ref:
            return
        # Procore states what a returned drawing is on the approver's workflow response,
        # never on the file object — carry it across so callers can say "Final PDF Pack"
        # because Procore said so, not because the filename looked right. The response can
        # reach us two ways: the file names its approver_id (mapped through `responses`),
        # or the file was nested inside the response row itself (the walk's context).
        if ref.get("approver_id") is None and ctx.get("approver_id") is not None:
            ref["approver_id"] = ctx["approver_id"]
        response = responses.get(ref.get("approver_id")) or {}
        response_name = ctx.get("response_name") or response.get("response_name")
        ref["response_name"] = response_name
        ref["approver_name"] = ctx.get("approver_name") or response.get("approver_name")
        ref["is_final_pdf_response"] = is_final_pdf_response_name(response_name)
        # Did Procore's own payload mention markups on this file? The rendered download
        # burns them in either way; this is how we know there were any to burn.
        ref["markup_paths"] = markup_evidence(att)
        ref["has_markup"] = bool(ref["markup_paths"])

        key = (ref["item_id"], ref["attachment_id"])
        if key in seen:
            # The same file legitimately appears twice — once as a submittal attachment and
            # again on the approver's workflow response. Merge rather than drop: whichever
            # sighting carries the response row is the one that knows what the file IS, and
            # it is usually the second one.
            kept = seen[key]
            if source == "originating":
                kept["source"] = "originating"
            if not kept.get("response_name") and ref.get("response_name"):
                kept["response_name"] = ref["response_name"]
                kept["approver_name"] = ref.get("approver_name") or kept.get("approver_name")
                kept["approver_id"] = ref.get("approver_id") or kept.get("approver_id")
                kept["is_final_pdf_response"] = ref.get("is_final_pdf_response", False)
            # Display metadata is often thin on one of the two copies.
            for field in ("created_at", "updated_at", "size_bytes", "created_by", "viewer_url"):
                if kept.get(field) is None and ref.get(field) is not None:
                    kept[field] = ref[field]
            # Markup evidence on either sighting counts for the file.
            if ref.get("has_markup") and not kept.get("has_markup"):
                kept["has_markup"] = True
                kept["markup_paths"] = ref.get("markup_paths")
            return
        seen[key] = ref
        refs.append(ref)
        logger.debug(
            "procore_attachment_candidate",
            submittal_id=submittal_id,
            attachment_id=ref["attachment_id"],
            item_type=ref["item_type"],
            name=ref["name"],
            approver_id=ref.get("approver_id"),
            response_name=ref.get("response_name"),
            approver_name=ref.get("approver_name"),
            is_final_pdf_response=ref.get("is_final_pdf_response"),
            source=ref["source"],
            attachment_keys=sorted(att.keys()),
        )

    sub = _request_json(
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}",
        company_id=cfg.PROD_PROCORE_COMPANY_ID,
    )
    if isinstance(sub, dict):
        responses.update(workflow_responses(sub))
        for att, ctx in walk_file_objects(sub):
            # Anything reached through a response row is a returned copy, not our upload.
            default = "approver" if ctx.get("response_name") else "originating"
            add(att, default, ctx)

    wf = _request_json(
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}/workflow_data",
        company_id=cfg.PROD_PROCORE_COMPANY_ID,
    )
    if isinstance(wf, dict):
        # workflow_data repeats the approver rows; anything it names is a response row too.
        responses.update(workflow_responses(wf))
        for att, ctx in walk_file_objects(wf):
            add(att, "approver", ctx)

    # Submitter's clean drawings first.
    refs.sort(key=lambda r: 0 if r["source"] == "originating" else 1)
    logger.info("procore_submittal_drawings_found", project_id=project_id,
                submittal_id=submittal_id, count=len(refs),
                sources=[r["source"] for r in refs],
                responses=[r.get("response_name") for r in refs],
                workflow_responses=len(responses))
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


_FINAL_PDF_TEXT_RE = re.compile(r"final.{0,12}pdf", re.I)


def find_matching_paths(obj, pattern=_FINAL_PDF_TEXT_RE, _path="$", _out=None):
    """Every JSON path in `obj` whose key or string value matches `pattern`.

    Answers "is the Final PDF Pack name hiding somewhere in this payload?" without having
    to read a 400-line dump by eye. Returns ["$.a.b[0].response_name = Final PDF Pack", ...].
    """
    out = [] if _out is None else _out
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{_path}.{k}"
            if isinstance(v, (dict, list)):
                find_matching_paths(v, pattern, path, out)
            else:
                text = "" if v is None else str(v)
                if pattern.search(str(k)) or pattern.search(text):
                    out.append(f"{path} = {text[:160]}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_matching_paths(v, pattern, f"{_path}[{i}]", out)
    return out


def raw_submittal_payloads(project_id, submittal_id):
    """The two payloads find_submittal_drawing_refs reads, unmodified.

    For debugging only — the puller's labels come from `find_submittal_drawing_refs`, not
    from here; this exists so a human can see what Procore actually sent.
    """
    submittal = _request_json(
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}",
        company_id=cfg.PROD_PROCORE_COMPANY_ID,
    )
    workflow = _request_json(
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}/workflow_data",
        company_id=cfg.PROD_PROCORE_COMPANY_ID,
    )
    return submittal, workflow


def _probe_get(url, company_id=None):
    """GET that reports its status instead of swallowing it. Debug paths only."""
    try:
        resp = requests.get(url, headers=_headers(company_id), timeout=_REQUEST_TIMEOUT_S)
        body = None
        if resp.text:
            try:
                body = resp.json()
            except ValueError:
                body = None
        return resp.status_code, body
    except requests.RequestException as exc:
        return None, {"error": str(exc)}


def _shape(body):
    """A body's shape without its bulk: type, size, and the keys in play."""
    if isinstance(body, dict):
        return {"type": "object", "keys": sorted(body.keys())}
    if isinstance(body, list):
        first = body[0] if body and isinstance(body[0], dict) else None
        return {"type": "array", "length": len(body),
                "item_keys": sorted(first.keys()) if first else None}
    return {"type": type(body).__name__}


def probe_attachment(project_id, submittal_id, attachment_id, item_id=None,
                     item_type=None, company_id=None):
    """Take one attachment's ids back to Procore and report what each endpoint returns.

    Debug only — nothing here decides a label. It exists for the case this was written
    for: an attachment whose `response_name` came back null because the submittal's
    `distributed_responses` did not mention its approver. The approver record itself is
    the next place the response name can live, so the probe asks for it directly, along
    with the other endpoints that might describe the file.

    Returns one row per URL: status, body shape, whether the attachment id appears in the
    response at all, every JSON path in it that looks like a final-PDF label, and any
    approver->response mapping it yields.
    """
    company_id = company_id or cfg.PROD_PROCORE_COMPANY_ID
    approver_id = item_id if (item_type or "").endswith("Approver") else None

    candidates = [
        # The approver record — where a response name lives when the submittal payload
        # omitted it. Tried as both a collection and a single record; Procore's shape for
        # these has moved between API versions.
        f"{API_HOST}/rest/v1.0/projects/{project_id}/submittals/{submittal_id}/approvers",
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}/approvers",
    ]
    if approver_id:
        candidates += [
            f"{API_HOST}/rest/v1.0/projects/{project_id}/submittals/{submittal_id}/approvers/{approver_id}",
            f"{API_HOST}/rest/v1.0/submittal_approvers/{approver_id}?project_id={project_id}",
            f"{API_HOST}/rest/v1.0/projects/{project_id}/submittal_approvers/{approver_id}",
        ]
    candidates += [
        # The attachment/file itself.
        f"{API_HOST}/rest/v1.0/projects/{project_id}/attachments/{attachment_id}",
        f"{API_HOST}/rest/v1.0/attachments/{attachment_id}?project_id={project_id}",
        f"{API_HOST}/rest/v1.0/companies/{company_id}/attachments/{attachment_id}",
        f"{API_HOST}/rest/v1.0/projects/{project_id}/documents/{attachment_id}",
        f"{API_HOST}/rest/v1.0/companies/{company_id}/prostore/files/{attachment_id}",
        # Other renderings of the submittal, in case one carries responses the others drop.
        f"{API_HOST}/rest/v1.0/projects/{project_id}/submittals/{submittal_id}",
        f"{API_HOST}/rest/v1.0/projects/{project_id}/submittal_logs/{submittal_id}",
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}/workflow_data",
        # The index serializer — where the production FC-link path actually reads
        # last_distributed_submittal from. The detail endpoint may simply not return it.
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals?filters[id][]={submittal_id}",
        # Response *names* are project/company configuration ("Approved", "Final PDF Pack",
        # …). If an approver row carries only a response id, this is the id→name map.
        f"{API_HOST}/rest/v1.0/projects/{project_id}/submittal_responses",
        f"{API_HOST}/rest/v1.0/companies/{company_id}/submittal_responses",
        # A pack attached and then distributed can land the response on another revision,
        # or on the distribution record rather than the submittal.
        f"{API_HOST}/rest/v1.0/projects/{project_id}/submittals/{submittal_id}/revisions",
        f"{API_HOST}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}/revisions",
        f"{API_HOST}/rest/v1.0/projects/{project_id}/submittals/{submittal_id}/distributions",
        f"{API_HOST}/rest/v1.0/projects/{project_id}/submittals/{submittal_id}/distributed_submittals",
        # The change log the client reads in the UI — attach, then distribute.
        f"{API_HOST}/rest/v1.0/projects/{project_id}/submittals/{submittal_id}/changes",
        f"{API_HOST}/rest/v1.0/projects/{project_id}/submittals/{submittal_id}/change_history",
    ]

    rows = []
    for url in candidates:
        status, body = _probe_get(url, company_id)
        serialized = json.dumps(body, default=str) if body is not None else ""
        rows.append({
            "url": url.split("?", 1)[0],
            "status": status,
            "shape": _shape(body) if body is not None else None,
            "mentions_attachment": str(attachment_id) in serialized,
            "mentions_approver": bool(approver_id) and str(approver_id) in serialized,
            "final_pdf_paths": find_matching_paths(body) if body is not None else [],
            "response_names": sorted({
                r["response_name"] for r in workflow_responses(body or {}).values()
                if r.get("response_name")
            }),
            "approver_responses": {
                str(k): v.get("response_name")
                for k, v in workflow_responses(body or {}).items()
            },
        })
        logger.debug("procore_attachment_probe", url=rows[-1]["url"], status=status,
                     mentions_attachment=rows[-1]["mentions_attachment"],
                     final_pdf_hits=len(rows[-1]["final_pdf_paths"]))

    logger.info("procore_attachment_probed", project_id=project_id,
                submittal_id=submittal_id, attachment_id=attachment_id,
                item_type=item_type, tried=len(rows),
                ok=[r["url"] for r in rows if r["status"] == 200])
    return rows


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


#: Keys and paths that indicate an approver drew on the drawing.
_MARKUP_TEXT_RE = re.compile(r"markup|annotation", re.I)


def markup_evidence(obj):
    """Every JSON path in `obj` whose key or value talks about markups/annotations.

    The rendered PDF always comes back through document_markup_downloadable_pdfs, so the
    bytes we save already carry whatever an approver drew. This says whether Procore's own
    payload admits there *was* anything drawn — which is what a reviewer wants to know
    before choosing between two candidate files.
    """
    return find_matching_paths(obj or {}, _MARKUP_TEXT_RE)


def download_markup_pdf(project_id, item_id, item_type, attachment_id, company_id=None,
                        *, poll_max=_POLL_MAX, poll_interval=_POLL_INTERVAL_S, meta=None):
    """Render + download one submittal-attachment PDF via find_or_create (async).

    Returns the PDF bytes, or None on failure. Polls the endpoint until it returns a
    download URL (the render is server-side and takes a few seconds). This endpoint is
    Procore's *markup* renderer: the file it produces has any approver markups burned in.

    Pass a dict as `meta` to receive what the render reported (its keys, the polls it took,
    and any markup/annotation fields it mentioned) — the caller can then tell the user
    whether markups came through rather than assuming.
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
            if meta is not None:
                hits = markup_evidence(data)
                meta.update({
                    "rendered_via": "document_markup_downloadable_pdfs",
                    "polls": attempt,
                    "response_keys": sorted(data.keys()) if isinstance(data, dict) else None,
                    "markup_paths": hits,
                    "has_markup_evidence": bool(hits),
                })
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
