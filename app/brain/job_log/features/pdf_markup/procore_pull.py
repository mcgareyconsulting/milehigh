"""Pull a release's Final PDF Pack out of Procore and land it as a drawing version.

The automatic path only ever links: `fc_retry_worker` finds the FC submittal and writes
`Releases.viewer_url` + `Releases.procore_submittal_id`, so the Job Log gets a Procore
*link*, not the PDF. This module is the manual counterpart — it downloads the actual
attachment bytes and attaches them to the release, which is what the release hub's viewer,
comments and Carmen review all read.

Two jobs:
  resolve_submittal(release, override) -> (submittal_id, project_id, how)
      Where the pack lives. Order: explicit override → the worker's link on the release →
      our own Submittals table (project_number/rel). Raises SubmittalNotResolved with a
      message the UI can show when none of those land — the "gap" case this exists for.
  list_documents / pull_document
      Enumerate the submittal's downloadable drawings (via app.procore.attachments), and
      download one into a new ReleaseDrawingVersion.

Provenance rides in the version's `note` as a parseable marker (PULL_NOTE_RE), so a
re-listing can tell which attachments are already attached without a schema change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.logging_config import get_logger
from app.config import Config as cfg
from app.models import ReleaseDrawingVersion, Submittals, db
from app.procore.attachments import (
    attachment_ids_from_url,
    download_attachment_raw,
    download_markup_pdf,
    find_matching_paths,
    find_submittal_drawing_refs,
    markup_evidence,
    probe_attachment,
    raw_submittal_payloads,
    walk_file_objects,
)

from app.brain.job_log.features.pdf_markup.command import (
    SaveDrawingVersionCommand,
    UploadInitialDrawingCommand,
)
from app.brain.job_log.features.pdf_markup.payloads import is_pdf_bytes

logger = get_logger(__name__)

#: Marker written into ReleaseDrawingVersion.note by a pull, and read back by the listing.
PULL_NOTE = "Pulled from Procore submittal {submittal_id} · attachment {attachment_id}"
PULL_NOTE_RE = re.compile(r"attachment\s+(\d+)")

#: Procore viewer URLs carry the project id: .../projects/<id>/tools/submittals/<id>
_VIEWER_PROJECT_RE = re.compile(r"/projects/(\d+)")


class SubmittalNotResolved(Exception):
    """No Procore submittal could be resolved for this release."""


class ProcorePullError(Exception):
    """Procore was reachable but the drawing could not be produced."""


@dataclass(frozen=True)
class SubmittalRef:
    submittal_id: str
    project_id: Optional[str]
    #: How we found it — 'override' | 'release_link' | 'submittals_table'
    how: str
    title: Optional[str] = None


def _project_id_for(submittal_id, release):
    """Project id for a submittal: our Submittals row first, then the release's viewer URL."""
    row = Submittals.query.filter(Submittals.submittal_id == str(submittal_id)).first()
    if row and row.procore_project_id:
        return str(row.procore_project_id)
    match = _VIEWER_PROJECT_RE.search(release.viewer_url or '')
    return match.group(1) if match else None


def resolve_submittal(release, submittal_id_override=None) -> SubmittalRef:
    """Find the Procore submittal holding this release's Final PDF Pack.

    The override exists for the gap case: a release the nightly worker has not linked yet
    (or linked to the wrong submittal) can still be pulled by hand for testing.
    """
    if submittal_id_override:
        sid = str(submittal_id_override).strip()
        row = Submittals.query.filter(Submittals.submittal_id == sid).first()
        return SubmittalRef(
            submittal_id=sid,
            project_id=(str(row.procore_project_id) if row and row.procore_project_id
                        else _project_id_for(sid, release)),
            how='override',
            title=row.title if row else None,
        )

    if release.procore_submittal_id:
        sid = str(release.procore_submittal_id)
        row = Submittals.query.filter(Submittals.submittal_id == sid).first()
        return SubmittalRef(
            submittal_id=sid,
            project_id=_project_id_for(sid, release),
            how='release_link',
            title=row.title if row else None,
        )

    # Nothing linked on the row — fall back to our own submittal mirror. Rel is typed by
    # hand (see the Submittal Matching tool), so this only hits when someone filled it in.
    row = (Submittals.query
           .filter(Submittals.project_number == str(release.job),
                   Submittals.rel == str(release.release))
           .order_by(Submittals.id.desc())
           .first())
    if row:
        return SubmittalRef(
            submittal_id=str(row.submittal_id),
            project_id=(str(row.procore_project_id) if row.procore_project_id
                        else _project_id_for(row.submittal_id, release)),
            how='submittals_table',
            title=row.title,
        )

    raise SubmittalNotResolved(
        "No Procore submittal is linked to this release yet. The nightly FC worker links "
        "one once the Final PDF Pack exists in Procore (~24h); until then, pass a submittal "
        "id to pull by hand."
    )


def attached_attachment_ids(release_id) -> dict:
    """{attachment_id (str): version dict} for versions this release already pulled."""
    out = {}
    versions = (ReleaseDrawingVersion.query
                .filter(ReleaseDrawingVersion.release_id == release_id,
                        ReleaseDrawingVersion.is_deleted.is_(False))
                .order_by(ReleaseDrawingVersion.version_number.desc())
                .all())
    for v in versions:
        match = PULL_NOTE_RE.search(v.note or '')
        if match and match.group(1) not in out:
            out[match.group(1)] = {
                'version_id': v.id,
                'version_number': v.version_number,
                'uploaded_at': v.uploaded_at.isoformat() if v.uploaded_at else None,
            }
    return out


def _same_procore_url(a, b):
    """Whether two Procore URLs point at the same thing, tolerating relative forms."""
    def norm(u):
        u = (u or '').strip()
        if not u:
            return ''
        if not u.startswith('http'):
            u = f"https://app.procore.com/{u.lstrip('/')}"
        return u.rstrip('/').lower()
    a, b = norm(a), norm(b)
    return bool(a) and a == b


def _is_release_linked(ref, linked_ids, release_viewer_url):
    """Is this the exact attachment the nightly FC worker linked on the release?

    Two ways to tell, because `Releases.viewer_url` holds whichever URL Procore handed
    `get_final_pdf_viewers`: an attachment viewer URL (which carries attachment_id, so the
    ids match) or a plain submittal page URL (which carries none — then only a whole-URL
    comparison against the candidate's own viewer_url can say).
    """
    if linked_ids.get('attachment_id'):
        return str(linked_ids['attachment_id']) == str(ref.get('attachment_id'))
    return _same_procore_url(ref.get('viewer_url'), release_viewer_url)


#: Role ranking — Final PDF Packs first, then other approver copies, then the submitted set.
_ROLE_ORDER = {'final_pack': 0, 'approver_copy': 1, 'submitted': 2}


def _role_for(ref, linked_ids):
    """(role, evidence) for one candidate — what it is, and what says so.

    Strongest first:
      workflow_response — Procore's own Workflow Responses row names this approver's
          response "Final PDF Pack". This is Procore stating it, not us guessing.
      release_link — the release's `viewer_url`, written by the nightly FC worker after
          matching the approver distribution, points at this exact attachment.
      item_type — the download URL's item_type: SubmittalLogApprover is a returned copy,
          SubmittalLog is the set we submitted.

    Procore's `is_originating_attachment` is deliberately NOT consulted: it is absent on
    most payloads, and the fallback guess behind it once labelled a Final PDF Pack a
    "submitted drawing".
    """
    if ref.get('is_final_pdf_response'):
        return 'final_pack', 'workflow_response'

    if linked_ids.get('attachment_id') and \
            str(linked_ids['attachment_id']) == str(ref.get('attachment_id')):
        return 'final_pack', 'release_link'

    if (ref.get('item_type') or '').endswith('Approver'):
        return 'approver_copy', 'item_type'
    return 'submitted', 'item_type'


def probe_candidate(release, attachment_id, submittal_id_override=None) -> dict:
    """Take one candidate's ids back to Procore and report what comes back.

    For the case where a file arrives with `response_name: null` — the submittal payload
    never mentioned its approver — so the label fell back to item_type. The approver record
    is the next place that name can live.
    """
    ref = resolve_submittal(release, submittal_id_override)
    refs = find_submittal_drawing_refs(ref.project_id, ref.submittal_id)
    target = next((r for r in refs if str(r.get('attachment_id')) == str(attachment_id)), None)
    if not target:
        return {'error': f'Attachment {attachment_id} is not on submittal {ref.submittal_id}'}

    return {
        'attachment': {
            'attachment_id': target.get('attachment_id'),
            'item_id': target.get('item_id'),
            'item_type': target.get('item_type'),
            'approver_id': target.get('approver_id'),
            'name': target.get('name'),
            'response_name': target.get('response_name'),
        },
        'endpoints': probe_attachment(
            ref.project_id, ref.submittal_id, target.get('attachment_id'),
            item_id=target.get('item_id'), item_type=target.get('item_type'),
        ),
    }


def storage_report() -> dict:
    """Where a pulled PDF actually lands, and whether that survives a deploy.

    A pulled pack goes through the same `save_pdf` as a Brain markup version, so both sit
    on whatever PDF_STORAGE_ROOT points at. Unset, that is <repo>/app/storage/pdfs — inside
    the deployed code tree, which Render wipes on every deploy. This reports the resolved
    path so an environment can be checked from the UI rather than guessed at.
    """
    from flask import current_app

    from app.brain.job_log.features.pdf_markup.storage import _storage_root

    configured = current_app.config.get('PDF_STORAGE_ROOT')
    root = str(_storage_root())
    inside_code_tree = root.startswith(str(current_app.root_path))
    return {
        'pdf_storage_root': root,
        'configured_via_env': bool(configured),
        'persistent': bool(configured) and not inside_code_tree,
        'shared_with_brain_markups': True,
        'note': (
            'Pulled packs and Brain markup versions share this root.'
            if configured else
            'PDF_STORAGE_ROOT is unset — falling back inside the code tree, which a deploy '
            'wipes. Set it to the mounted disk (e.g. /var/data/pdfs) on this environment.'
        ),
    }


def debug_payloads(release, submittal_id_override=None) -> dict:
    """Everything Procore sent for this release's submittal, for eyeballing in a console.

    Not used to decide anything — `list_documents` is the product path. This exists to
    answer "where does the Final PDF Pack name actually live in the payload?", so it ships
    the raw attachment objects, the distributed responses, and every JSON path in either
    payload whose key or value looks like a final-PDF label.
    """
    ref = resolve_submittal(release, submittal_id_override)
    submittal, workflow = raw_submittal_payloads(ref.project_id, ref.submittal_id)

    return {
        'submittal_id': ref.submittal_id,
        'project_id': ref.project_id,
        'storage': storage_report(),
        'final_pdf_paths': {
            'submittal': find_matching_paths(submittal or {}),
            'workflow_data': find_matching_paths(workflow or {}),
        },
        'submittal_keys': sorted((submittal or {}).keys()),
        'workflow_keys': sorted((workflow or {}).keys()),
        'distributed_responses': (
            ((submittal or {}).get('last_distributed_submittal') or {}).get('distributed_responses')
        ),
        'submittal_attachments': (submittal or {}).get('attachments'),
        'workflow_attachments': (workflow or {}).get('attachments'),
        'workflow_approvers': (workflow or {}).get('approvers'),
        # Every file-ish object the walk reaches, wherever it hides, with the response row
        # it inherits — this is what the collector actually sees.
        'walked_files': [
            {
                'name': f.get('name') or f.get('filename'),
                'keys': sorted(f.keys()),
                'context': ctx,
                'payload': where,
            }
            for where, payload in (('submittal', submittal), ('workflow_data', workflow))
            for f, ctx in walk_file_objects(payload or {})
        ],
    }


def list_documents(release, submittal_id_override=None) -> dict:
    """The pull workspace for one release: which submittal, and what can be pulled from it."""
    ref = resolve_submittal(release, submittal_id_override)
    if not ref.project_id:
        raise SubmittalNotResolved(
            f"Submittal {ref.submittal_id} has no Procore project id on our side — "
            "open it in Procore once, or pass a submittal id that we have synced."
        )

    refs = find_submittal_drawing_refs(ref.project_id, ref.submittal_id)
    already = attached_attachment_ids(release.id)
    # The FC pack the worker already linked on this release, by its attachment ids.
    linked_ids = attachment_ids_from_url(release.viewer_url)

    documents = []
    for r in refs:
        role, evidence = _role_for(r, linked_ids)
        is_linked = _is_release_linked(r, linked_ids, release.viewer_url)
        documents.append({
            'attachment_id': r.get('attachment_id'),
            'item_id': r.get('item_id'),
            'item_type': r.get('item_type'),
            'name': r.get('name'),
            'role': role,
            'role_evidence': evidence,
            'is_release_linked': is_linked,
            # Procore's Workflow Responses row for this attachment, when it has one.
            'response_name': r.get('response_name'),
            'approver_name': r.get('approver_name'),
            # Procore's own flag when it sent one; None means it did not say.
            'source': r.get('source'),
            'is_originating_attachment': r.get('is_originating_attachment'),
            'approver_id': r.get('approver_id'),
            # Whether Procore's payload says an approver drew on this one.
            'has_markup': bool(r.get('has_markup')),
            # 'yes' | 'no' | 'unknown' — a key merely named markup is not evidence.
            'markup_signal': r.get('markup_signal') or 'unknown',
            'id_candidates': r.get('id_candidates') or [],
            'prostore_id': r.get('prostore_id'),
            'urls': [name for name, _ in (r.get('urls') or [])],
            'created_at': r.get('created_at'),
            'updated_at': r.get('updated_at'),
            'size_bytes': r.get('size_bytes'),
            'created_by': r.get('created_by'),
            'viewer_url': r.get('viewer_url'),
            'attached': already.get(str(r.get('attachment_id'))),
        })
    # Final PDF Pack first; within a role prefer the marked-up copy, then the linked one —
    # the marked-up set is the one the shop actually builds from.
    documents.sort(key=lambda d: (
        _ROLE_ORDER.get(d['role'], 9),
        0 if d['has_markup'] else 1,
        0 if d['is_release_linked'] else 1,
    ))

    return {
        'submittal': _submittal_payload(ref, release),
        'documents': documents,
    }


def _submittal_payload(ref: 'SubmittalRef', release) -> dict:
    """Enough of the submittal to confirm it is the right one before pulling from it."""
    row = Submittals.query.filter(Submittals.submittal_id == str(ref.submittal_id)).first()
    company_id = str(cfg.PROD_PROCORE_COMPANY_ID or '')
    procore_url = (
        f"https://app.procore.com/webclients/host/companies/{company_id}"
        f"/projects/{ref.project_id}/tools/submittals/{ref.submittal_id}"
        if company_id and ref.project_id else None
    )
    return {
        'submittal_id': ref.submittal_id,
        'project_id': ref.project_id,
        'title': ref.title or (row.title if row else None),
        'type': row.type if row else None,
        'status': row.status if row else None,
        'ball_in_court': row.ball_in_court if row else None,
        'rel': row.rel if row else None,
        'project_number': row.project_number if row else None,
        'resolved_by': ref.how,
        'procore_url': procore_url,
        # The FC pack link the nightly worker wrote on the release, if it has one.
        'release_viewer_url': release.viewer_url or None,
    }


#: Each find_or_create attempt costs a round trip, so cross the id spaces but cap it.
_MAX_ID_ALTERNATIVES = 8


def _id_alternatives(target, ref):
    """Ordered fallback triples for the markup render, most specific first.

    An attachment's viewer URL and its download URL can disagree on *both* halves — the
    item they hang off AND the attachment id itself (one file, two id spaces). Pairing only
    like with like leaves the working combination untried, so cross every item candidate
    with every attachment id seen, in confidence order, deduped.
    """
    items, attachment_ids = [], []

    def add_item(item_id, item_type, source):
        if not (item_id and item_type):
            return
        key = (str(item_id), item_type)
        if key not in {(str(i[0]), i[1]) for i in items}:
            items.append((item_id, item_type, source))

    def add_attachment(attachment_id):
        if attachment_id and str(attachment_id) not in {str(a) for a in attachment_ids}:
            attachment_ids.append(attachment_id)

    for candidate in target.get('id_candidates') or []:
        add_item(candidate.get('item_id'), candidate.get('item_type'), candidate.get('source'))
        add_attachment(candidate.get('attachment_id'))
    add_attachment(target.get('attachment_id'))
    # /document-viewer/prostore/<id> — a different id space for the same file, and the one
    # the viewer URL actually names.
    add_attachment(target.get('prostore_id'))
    # A file reached through a response row is still an attachment on the log itself.
    add_item(ref.submittal_id, 'SubmittalLog', 'submittal_log')
    add_item(target.get('approver_id'), 'SubmittalLogApprover', 'approver_id')

    alternatives = []
    for item_id, item_type, source in items:
        for attachment_id in attachment_ids:
            alternatives.append({
                'item_id': item_id,
                'item_type': item_type,
                'attachment_id': attachment_id,
                'project_id': target.get('project_id'),
                'source': f"{source}+att{attachment_id}",
            })
    return alternatives[:_MAX_ID_ALTERNATIVES]


def pull_document(release, attachment_id, uploaded_by_user_id, submittal_id_override=None):
    """Download one Procore attachment and attach it as this release's next drawing version.

    Returns (version, ref). Raises SubmittalNotResolved / ProcorePullError / ValueError.
    """
    ref = resolve_submittal(release, submittal_id_override)
    if not ref.project_id:
        raise SubmittalNotResolved(
            f"Submittal {ref.submittal_id} has no Procore project id on our side."
        )

    refs = find_submittal_drawing_refs(ref.project_id, ref.submittal_id)
    target = next((r for r in refs if str(r.get('attachment_id')) == str(attachment_id)), None)
    if not target:
        raise ProcorePullError(
            f"Attachment {attachment_id} is not on submittal {ref.submittal_id}."
        )

    render_meta = {}
    pdf_bytes = download_markup_pdf(
        target['project_id'], target['item_id'], target['item_type'], target['attachment_id'],
        company_id=target.get('company_id'), meta=render_meta,
        alternatives=_id_alternatives(target, ref),
    )
    render_fallback = None
    if not pdf_bytes:
        # find_or_create is the only endpoint that burns markups in. When it refuses every
        # id shape, a clean copy of the file still beats no drawing at all — as long as we
        # say which one the user got.
        pdf_bytes = download_attachment_raw(
            dict(target, submittal_id=ref.submittal_id, project_id=ref.project_id),
        )
        if pdf_bytes:
            render_fallback = 'raw_attachment'
            logger.warning(
                "release_procore_pack_raw_fallback",
                release_id=release.id, submittal_id=ref.submittal_id,
                attachment_id=attachment_id,
            )
    if not pdf_bytes:
        raise ProcorePullError(
            "Procore has the file but would not render or release it for download. Its "
            "markup render can lag right after a distribution — try again shortly."
        )
    if not is_pdf_bytes(pdf_bytes):
        raise ProcorePullError("Procore returned something that is not a PDF.")

    # Markups burn into the rendered file; say so only when something says there were any.
    markup_paths = (target.get('markup_paths') or []) + (render_meta.get('markup_paths') or [])
    carried_markup = bool(target.get('has_markup') or render_meta.get('has_markup_evidence'))
    if render_fallback == 'raw_attachment':
        # The raw file has not been through the markup renderer, so any markups an approver
        # drew are NOT in these bytes. Say so.
        carried_markup = False

    filename = target.get('name') or f"procore-{ref.submittal_id}-{attachment_id}.pdf"
    if not filename.lower().endswith('.pdf'):
        filename = f"{filename}.pdf"
    note = PULL_NOTE.format(submittal_id=ref.submittal_id, attachment_id=attachment_id)
    if target.get('response_name'):
        note = f"{note} · {target['response_name']}"
    if carried_markup:
        note = f"{note} · markups included"
    if render_fallback == 'raw_attachment':
        note = f"{note} · clean copy (Procore would not render markups)"

    latest = (ReleaseDrawingVersion.query
              .filter(ReleaseDrawingVersion.release_id == release.id)
              .order_by(ReleaseDrawingVersion.version_number.desc())
              .first())

    if latest is None:
        version = UploadInitialDrawingCommand(
            release_id=release.id,
            file_bytes=pdf_bytes,
            filename=filename,
            mime_type='application/pdf',
            uploaded_by_user_id=uploaded_by_user_id,
            note=note,
        ).execute()
    else:
        # A pulled pack is a new revision of the release's drawing, so it chains off the
        # newest version the same way a saved markup does.
        version = SaveDrawingVersionCommand(
            release_id=release.id,
            file_bytes=pdf_bytes,
            uploaded_by_user_id=uploaded_by_user_id,
            source_version_id=latest.id,
            note=note,
        ).execute()
        if version.original_filename != filename:
            version.original_filename = filename
            db.session.commit()

    logger.info(
        "release_procore_pack_pulled",
        release=release.release,
        job=release.job,
        release_id=release.id,
        submittal_id=ref.submittal_id,
        attachment_id=attachment_id,
        version_id=version.id,
        size=len(pdf_bytes),
        source=target.get('source'),
        resolved_by=ref.how,
        response_name=target.get('response_name'),
        carried_markup=carried_markup,
        render_polls=render_meta.get('polls'),
        id_source=(render_meta.get('triple_used') or {}).get('source'),
        triples_tried=render_meta.get('triples_tried'),
        render_fallback=render_fallback,
    )
    target = dict(target, carried_markup=carried_markup, markup_paths=markup_paths,
                  render_meta=render_meta, render_fallback=render_fallback)
    return version, target
