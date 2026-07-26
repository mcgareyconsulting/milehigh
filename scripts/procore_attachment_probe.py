"""Feasibility probe: can we DOWNLOAD a submittal's drawing bytes from Procore?

Read-only. Settles the go/no-go gate for the "continuous compliance via Procore
ingestion" track (docs/bb-pdf-review-hardening-plan.md, Track B). It does NOT write
anything to Procore or our DB — only GETs.

What it does:
  1. Pick a submittal (CLI args, else auto-select a recent one from our Submittals
     table that has a Procore project id, preferring For Construction / GC types).
  2. GET the submittal (v1.1) and its workflow_data, and enumerate EVERY attachment
     object and EVERY url-like field on them (so we can see viewer_url vs a real
     download url).
  3. For the first PDF-looking attachment, try to actually download the bytes with our
     client-credentials Bearer token: report HTTP status, final host, content-type,
     content-length, and whether the body starts with the %PDF magic.
  4. Print a GO / NO-GO verdict.

NOTE: our Procore client only talks to api.procore.com (production) — that's the only
host we have credentials for (the ENVIRONMENT var only switches the webhook destination,
not the API). So this reads REAL company Procore data, exactly like every inbound webhook
already does. It is strictly read-only.

Usage:
  python scripts/procore_attachment_probe.py
  python scripts/procore_attachment_probe.py --project-id 12345 --submittal-id 67890
  python scripts/procore_attachment_probe.py --save /tmp/probe.pdf   # keep the file
"""
import argparse
import re
import sys
import time
from urllib.parse import urlparse, parse_qs

import requests

# Non-secret id params we want from Procore's own urls; anything else (sig/token/expires)
# is left untouched and never printed.
ID_PARAMS = ("attachment_id", "item_id", "item_type", "project_id")

from app import create_app
from app.config import Config as cfg
from app.models import Submittals
from app.procore.client import get_procore_client
from app.procore.procore import get_workflow_data
from app.procore.procore_auth import get_access_token

API_HOST = "https://api.procore.com"

# Attachment fields Procore is known to use for links; we probe all of them plus any
# other key whose name contains "url".
KNOWN_URL_FIELDS = ("url", "download_url", "viewer_url", "file_url", "prostore_url")
PDF_HINT = (".pdf",)


def _redact(url: str) -> str:
    """Print host+path only — Procore signed download URLs carry a signature in the
    query string; don't leak it into logs."""
    if not url:
        return "(none)"
    return url.split("?", 1)[0] + ("?…" if "?" in url else "")


def _pick_submittal(args):
    """Return (project_id, submittal_id, label) from CLI args or the DB."""
    if args.project_id and args.submittal_id:
        return str(args.project_id), str(args.submittal_id), "cli-supplied"

    q = Submittals.query.filter(Submittals.procore_project_id.isnot(None))
    rows = q.order_by(Submittals.last_updated.desc()).limit(200).all()
    if not rows:
        return None, None, None

    def rank(r):
        t = (r.type or "").lower()
        if "for construction" in t:
            return 0
        if "gc" in t or "approval" in t:
            return 1
        if "drafting release" in t:
            return 2
        return 3

    best = sorted(rows, key=rank)[0]
    return (str(best.procore_project_id), str(best.submittal_id),
            f"{best.title!r} (type={best.type!r})")


def _url_fields(att: dict):
    """Every (field_name, value) on an attachment object that looks like a URL."""
    out = []
    for k, v in att.items():
        if not isinstance(v, str):
            continue
        if k in KNOWN_URL_FIELDS or "url" in k.lower():
            out.append((k, v))
    return out


def _looks_like_pdf(att: dict) -> bool:
    name = (att.get("name") or att.get("filename") or "").lower()
    ctype = (att.get("content_type") or att.get("mime_type") or "").lower()
    return name.endswith(PDF_HINT) or "pdf" in ctype


def _dump_attachments(label, attachments):
    print(f"\n  {label}: {len(attachments)} attachment(s)")
    for i, att in enumerate(attachments):
        if not isinstance(att, dict):
            print(f"    [{i}] (non-dict: {type(att).__name__})")
            continue
        name = att.get("name") or att.get("filename") or "(no name)"
        print(f"    [{i}] name={name!r} keys={sorted(att.keys())}")
        for k, v in _url_fields(att):
            print(f"         {k} = {_redact(v)}")
    return [a for a in attachments if isinstance(a, dict)]


def _try_download(url: str, save_path: str | None):
    """GET url with our Bearer token, streamed. Report what came back. Read only enough
    to confirm the PDF magic; don't pull the whole file unless --save was given."""
    token = get_access_token()
    print(f"\n  → downloading {_redact(url)}")
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            stream=True,
            allow_redirects=True,
            timeout=60,
        )
    except requests.RequestException as e:
        print(f"    REQUEST ERROR: {type(e).__name__}: {e}")
        return False

    final_host = requests.utils.urlparse(resp.url).netloc
    ctype = resp.headers.get("Content-Type", "")
    clen = resp.headers.get("Content-Length", "?")
    print(f"    status={resp.status_code} final_host={final_host} "
          f"content_type={ctype!r} content_length={clen}")

    if resp.status_code != 200:
        snippet = (resp.text or "")[:300].replace("\n", " ")
        print(f"    body: {snippet}")
        resp.close()
        return False

    first = next(resp.iter_content(chunk_size=8192), b"")
    is_pdf = first[:5] == b"%PDF-"
    print(f"    first_bytes={first[:8]!r} is_pdf={is_pdf}")

    if save_path:
        with open(save_path, "wb") as fh:
            fh.write(first)
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)
        print(f"    saved → {save_path}")
    resp.close()
    return is_pdf


def _api_get(path: str, company_id: str, stream=False):
    """GET an api.procore.com REST path with Bearer + Procore-Company-Id header
    (the header our production client currently omits). Returns the response or None."""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if company_id:
        headers["Procore-Company-Id"] = str(company_id)
    url = f"{API_HOST}{path}"
    try:
        return requests.get(url, headers=headers, stream=stream,
                            allow_redirects=True, timeout=60)
    except requests.RequestException as e:
        print(f"    REQUEST ERROR on {path}: {type(e).__name__}: {e}")
        return None


def _query_val(url: str, key: str):
    m = re.search(rf"[?&]{key}=([^&]+)", url or "")
    return m.group(1) if m else None


def _download_signed(url: str, company_id: str, save_path):
    """Follow a (possibly signed) download url returned by the markup endpoint and
    confirm PDF bytes. Try with and without our bearer/company header."""
    token = get_access_token()
    for hdrs in ({"Authorization": f"Bearer {token}", "Procore-Company-Id": str(company_id)}, {}):
        try:
            r = requests.get(url, headers=hdrs, stream=True, allow_redirects=True, timeout=60)
        except requests.RequestException as e:
            print(f"      follow-url error: {type(e).__name__}: {e}")
            continue
        first = next(r.iter_content(8192), b"") if r.status_code == 200 else b""
        print(f"      follow status={r.status_code} ctype={r.headers.get('Content-Type','')!r} "
              f"first={first[:8]!r}")
        if first[:5] == b"%PDF-":
            if save_path:
                with open(save_path, "wb") as fh:
                    fh.write(first)
                    for c in r.iter_content(65536):
                        fh.write(c)
                print(f"      saved → {save_path}")
            r.close()
            return True
        r.close()
    return False


def _find_url_in(obj):
    """Recursively pull the first http(s) url out of a JSON response."""
    if isinstance(obj, str) and obj.startswith("http"):
        return obj
    if isinstance(obj, dict):
        for k in ("url", "download_url", "file_url"):
            if isinstance(obj.get(k), str) and obj[k].startswith("http"):
                return obj[k]
        for v in obj.values():
            u = _find_url_in(v)
            if u:
                return u
    if isinstance(obj, list):
        for v in obj:
            u = _find_url_in(v)
            if u:
                return u
    return None


def _try_markup_pdf(att: dict, company_id: str, project_id: str, save_path):
    """POST document_markup_downloadable_pdfs/find_or_create (the correct endpoint).

    Per Procore's docs it's ASYNC: the first call starts processing; re-POST the SAME
    body and, when rendering completes, the response carries the download URL. Body params
    item_id/item_type/attachment_id are exactly the ones in the attachment's viewer_url.
    """
    # Procore's docs: item_id/item_type/attachment_id are "the same parameters included in
    # the URL when viewing the attachment." The authoritative source is the download_url
    # query string; fall back to the viewer_url. Print the id params so we can see them.
    def ids_from(url):
        q = parse_qs(urlparse(url or "").query)
        return {k: q[k][0] for k in ID_PARAMS if k in q}

    dl_ids = ids_from(att.get("download_url"))
    vw_ids = ids_from(att.get("viewer_url"))
    print(f"\n  download_url id params: {dl_ids}")
    print(f"  viewer_url id params:   {vw_ids}")

    path = "/rest/v1.0/document_markup_downloadable_pdfs/find_or_create"
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
               "Procore-Company-Id": str(company_id)}

    # Build candidate bodies: prefer the download_url ids; also try item_type variants
    # (docs example uses "SubmittalLog"; our viewer said "SubmittalLogApprover").
    def mk(src, item_type_override=None):
        if not src.get("item_id") or not src.get("attachment_id"):
            return None
        return {
            "item_id": int(src["item_id"]),
            "item_type": item_type_override or src.get("item_type") or "SubmittalLog",
            "attachment_id": int(src["attachment_id"]),
            "project_id": int(src.get("project_id") or project_id),
        }

    seen, bodies = set(), []
    for src in (dl_ids, vw_ids):
        for it in (None, "SubmittalLog", "SubmittalLogApprover"):
            b = mk(src, it)
            key = b and tuple(sorted(b.items()))
            if b and key not in seen:
                seen.add(key)
                bodies.append(b)
    if not bodies:
        print("    could not assemble a body (missing item_id/attachment_id in the urls).")
        return None

    for body in bodies:
        print(f"\n  POST {path}  body={body}")
        for attempt in range(1, 9):  # poll while it renders
            try:
                r = requests.post(f"{API_HOST}{path}", headers=headers, json=body, timeout=90)
            except requests.RequestException as e:
                print(f"    POST error: {type(e).__name__}: {e}")
                break
            try:
                data = r.json()
            except ValueError:
                data = None
            text = (r.text or "")[:400].replace("\n", " ")
            url = _find_url_in(data) if data else None
            status_field = data.get("status") if isinstance(data, dict) else None
            print(f"    attempt {attempt}: http={r.status_code} status={status_field!r} "
                  f"url={'yes' if url else 'no'}")
            if r.status_code not in (200, 201):
                print(f"      body: {text}")
                break  # try next candidate body
            if url:
                print(f"      download url ready: {_redact(url)}")
                return path if _download_signed(url, company_id, save_path) else None
            time.sleep(4)  # still processing; re-request the same body
    return None


def _try_api_endpoints(att: dict, company_id: str, project_id: str, save_path):
    """Try the real REST file endpoints (with the company-id header) using the ids we
    can extract from the attachment. One that returns %PDF settles the gate as GO."""
    att_id = att.get("id")
    # prostore id is embedded in the viewer_url: .../prostore/<id>?...
    m = re.search(r"/prostore/(\d+)", att.get("viewer_url") or "")
    prostore_id = m.group(1) if m else None
    print(f"\n  ids: attachment_id={att_id} prostore_id={prostore_id} "
          f"company_id={company_id} project_id={project_id}")

    candidates = []
    if prostore_id:
        candidates += [
            f"/rest/v1.0/companies/{company_id}/prostore/files/{prostore_id}",
            f"/rest/v1.0/files/{prostore_id}",
            f"/rest/v1.0/projects/{project_id}/documents/{prostore_id}",
        ]
    if att_id:
        candidates.append(f"/rest/v1.0/projects/{project_id}/documents/{att_id}")

    for path in candidates:
        resp = _api_get(path, company_id, stream=True)
        if resp is None:
            continue
        ctype = resp.headers.get("Content-Type", "")
        print(f"    {path}\n      → status={resp.status_code} content_type={ctype!r} "
              f"final_host={requests.utils.urlparse(resp.url).netloc}")
        if resp.status_code == 200:
            first = next(resp.iter_content(chunk_size=8192), b"")
            if first[:5] == b"%PDF-":
                print(f"      first_bytes={first[:8]!r} is_pdf=True  ← WORKS")
                if save_path:
                    with open(save_path, "wb") as fh:
                        fh.write(first)
                        for c in resp.iter_content(65536):
                            fh.write(c)
                    print(f"      saved → {save_path}")
                resp.close()
                return path
            # JSON body may carry a signed download url — surface it.
            body = (resp.text or "")[:400].replace("\n", " ")
            print(f"      body: {body}")
        resp.close()
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-id", type=int)
    ap.add_argument("--submittal-id", type=int)
    ap.add_argument("--save", help="save the downloaded file to this path")
    ap.add_argument("--dump-json", help="write raw submittal + workflow_data JSON here")
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        project_id, submittal_id, label = _pick_submittal(args)
        if not submittal_id:
            print("No submittal found (no CLI args and no rows with a Procore project id).")
            sys.exit(2)

        print(f"Probing submittal {submittal_id} (project {project_id}) — {label}")
        print(f"API host: {cfg.PROD_PROCORE_BASE_URL} / {get_procore_client().BASE_URL}")

        client = get_procore_client()
        candidates = []  # (source, url) to try downloading

        # 1) submittal-by-id (v1.1) — has attachments + last_distributed_submittal
        try:
            sub = client.get_submittal_by_id(project_id, submittal_id)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            print(f"\nget_submittal_by_id FAILED: HTTP {code} — {(e.response.text if e.response else '')[:300]}")
            sub = None

        if isinstance(sub, dict):
            atts = _dump_attachments("submittal.attachments", sub.get("attachments") or [])
            for att in atts:
                if _looks_like_pdf(att):
                    for _, url in _url_fields(att):
                        candidates.append(("submittal.attachments", url))

        # 2) workflow_data — where get_final_pdf_viewers reads viewer_url today
        try:
            wf = get_workflow_data(project_id, submittal_id)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            print(f"\nget_workflow_data FAILED: HTTP {code}")
            wf = {}
        pdf_atts = []  # attachment dicts to try REST file endpoints against
        company_id = str(cfg.PROD_PROCORE_COMPANY_ID or "")
        if args.dump_json:
            import json
            with open(args.dump_json, "w") as fh:
                json.dump({"submittal": sub, "workflow_data": wf}, fh, indent=2, default=str)
            print(f"\n  raw JSON dumped → {args.dump_json}")

        if isinstance(wf, dict) and wf.get("attachments"):
            atts = _dump_attachments("workflow_data.attachments", wf.get("attachments") or [])
            for att in atts:
                # company id is embedded in the viewer_url: .../companies/<id>/...
                m = re.search(r"/companies/(\d+)", att.get("viewer_url") or "")
                if m:
                    company_id = m.group(1)
                if _looks_like_pdf(att):
                    pdf_atts.append(att)
                for _, url in _url_fields(att):
                    candidates.append(("workflow_data.attachments", url))

        if not candidates:
            print("\nNO-GO (so far): found no url-bearing attachment on this submittal. "
                  "Try a For Construction submittal known to carry a drawing set "
                  "(pass --project-id/--submittal-id).")
            sys.exit(1)

        # Path A: the attachment's own url fields (download_url is app.procore.com — we
        # expect this to 401; kept to document the dead end).
        print("\n--- Path A: attachment download_url / viewer_url (as-provided) ---")
        seen = set()
        ordered = sorted(candidates, key=lambda c: ("viewer" in c[1].lower(), c[1]))
        downloaded_pdf = False
        for source, url in ordered:
            if url in seen or not url.startswith("http"):
                continue
            seen.add(url)
            print(f"[{source}]")
            if _try_download(url, args.save):
                downloaded_pdf = True
                break

        # Path B: the correct endpoint — document_markup_downloadable_pdfs/find_or_create.
        winning_endpoint = None
        if not downloaded_pdf and pdf_atts:
            print("\n--- Path B: document_markup_downloadable_pdfs/find_or_create ---")
            for att in pdf_atts:
                winning_endpoint = _try_markup_pdf(att, company_id, project_id, args.save)
                if winning_endpoint:
                    break

        print("\n" + "=" * 60)
        if downloaded_pdf:
            print("GO ✅ — downloaded real PDF bytes from the attachment url with our token.")
        elif winning_endpoint:
            print(f"GO ✅ — downloaded real PDF bytes via REST endpoint:\n    {winning_endpoint}\n"
                  "  (Bearer + Procore-Company-Id header). Ingestion is feasible; wire this "
                  "endpoint + header into the Procore client.")
        else:
            print("NEEDS-ATTENTION ❌ — no path yielded PDF bytes yet.\n"
                  "  Path A (download_url) is app.procore.com and rejects API tokens (session-only) — expected.\n"
                  "  Path B REST attempts above show the real story: a 403 = Data Connection App lacks\n"
                  "  file/document read permission (Procore portal change); a 404 = wrong endpoint for this\n"
                  "  attachment kind (submittal-approver files may need a different files API — confirm with\n"
                  "  Procore developer support). A 200 with a JSON body likely carries a signed url to follow.")
        print("=" * 60)


if __name__ == "__main__":
    main()
