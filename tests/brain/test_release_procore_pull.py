"""Tests for the release-side Final PDF Pack puller.

Procore itself is always mocked (tests/README.md): `find_submittal_drawing_refs` and
`download_markup_pdf` are patched at the point the puller imports them. What is under test
is our half — how a release resolves to a submittal, how a pulled attachment becomes a
drawing version, and what the routes say when nothing resolves.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

import pytest

from tests.conftest import make_release, make_user

PDF_MIN = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\ntrailer\n<<>>\n%%EOF\n"

REF = {
    'source': 'approver',
    'name': 'Final PDF Pack.pdf',
    'item_id': 900,
    'item_type': 'SubmittalLogApprover',
    'attachment_id': 5150,
    'project_id': 777,
    'company_id': 18521,
}

MODULE = 'app.brain.job_log.features.pdf_markup.procore_pull'


@pytest.fixture
def storage_root(tmp_path, app):
    app.config['PDF_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


@pytest.fixture
def drafter(app):
    return make_user("pulldrafter", is_drafter=True)


def _make_submittal(submittal_id="4242", project_id="777", **extra):
    from app.models import Submittals, db
    row = Submittals(submittal_id=submittal_id, procore_project_id=project_id, **extra)
    db.session.add(row)
    db.session.flush()
    return row


def _patch_user(user):
    stack = ExitStack()
    for target in (
        'app.auth.utils.get_current_user',
        'app.brain.job_log.pdf_markup_routes.get_current_user',
        'app.services.job_event_service.get_current_user',
    ):
        stack.enter_context(patch(target, return_value=user))
    return stack


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_resolves_from_the_link_the_nightly_worker_wrote(app):
    from app.brain.job_log.features.pdf_markup.procore_pull import resolve_submittal

    _make_submittal("4242", "777", title="340-666 FC")
    release = make_release(job=340, release="666", procore_submittal_id="4242")

    ref = resolve_submittal(release)
    assert (ref.submittal_id, ref.project_id, ref.how) == ("4242", "777", 'release_link')
    assert ref.title == "340-666 FC"


def test_falls_back_to_the_submittal_mirror_on_job_release(app):
    from app.brain.job_log.features.pdf_markup.procore_pull import resolve_submittal

    _make_submittal("9001", "777", project_number="340", rel="666")
    release = make_release(job=340, release="666")

    ref = resolve_submittal(release)
    assert (ref.submittal_id, ref.how) == ("9001", 'submittals_table')


def test_project_id_comes_off_the_viewer_url_when_we_have_no_submittal_row(app):
    from app.brain.job_log.features.pdf_markup.procore_pull import resolve_submittal

    release = make_release(
        job=340, release="666", procore_submittal_id="4242",
        viewer_url="https://app.procore.com/webclients/host/companies/18521/projects/777/tools/submittals/4242",
    )
    ref = resolve_submittal(release)
    assert ref.project_id == "777"


def test_unlinked_release_raises_the_gap_error(app):
    from app.brain.job_log.features.pdf_markup.procore_pull import (
        SubmittalNotResolved, resolve_submittal,
    )

    release = make_release(job=341, release="667")
    with pytest.raises(SubmittalNotResolved):
        resolve_submittal(release)


def test_override_wins_over_the_link(app):
    from app.brain.job_log.features.pdf_markup.procore_pull import resolve_submittal

    _make_submittal("4242", "777")
    _make_submittal("5555", "888")
    release = make_release(job=340, release="666", procore_submittal_id="4242")

    ref = resolve_submittal(release, submittal_id_override="5555")
    assert (ref.submittal_id, ref.project_id, ref.how) == ("5555", "888", 'override')


# ---------------------------------------------------------------------------
# Pull
# ---------------------------------------------------------------------------


def test_pull_creates_v1_and_records_provenance(app, storage_root, drafter):
    from app.brain.job_log.features.pdf_markup.procore_pull import pull_document
    from app.models import ReleaseDrawingVersion

    _make_submittal("4242", "777")
    release = make_release(job=340, release="666", procore_submittal_id="4242")

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=PDF_MIN) as dl:
        version, ref = pull_document(release, 5150, uploaded_by_user_id=drafter.id)

    # meta is the out-dict the render fills with markup evidence; alternatives are the
    # fallback id triples for when Procore 404s the first one.
    args, kwargs = dl.call_args
    assert args == (777, 900, 'SubmittalLogApprover', 5150)
    assert kwargs['company_id'] == 18521
    assert kwargs['meta'] == {}
    last = kwargs['alternatives'][-1]
    assert last['item_type'] == 'SubmittalLog'
    assert last['source'].startswith('submittal_log')
    assert version.version_number == 1
    assert version.original_filename == 'Final PDF Pack.pdf'
    assert '5150' in version.note and '4242' in version.note
    assert ref['source'] == 'approver'
    assert ReleaseDrawingVersion.query.filter_by(release_id=release.id).count() == 1


def test_second_pull_chains_a_new_version_off_the_newest(app, storage_root, drafter):
    from app.brain.job_log.features.pdf_markup.procore_pull import pull_document

    _make_submittal("4242", "777")
    release = make_release(job=340, release="666", procore_submittal_id="4242")

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=PDF_MIN):
        first, _ = pull_document(release, 5150, uploaded_by_user_id=drafter.id)
        second, _ = pull_document(release, 5150, uploaded_by_user_id=drafter.id)

    assert (second.version_number, second.source_version_id) == (2, first.id)


def test_listing_marks_an_attachment_already_attached(app, storage_root, drafter):
    from app.brain.job_log.features.pdf_markup.procore_pull import list_documents, pull_document

    _make_submittal("4242", "777")
    release = make_release(job=340, release="666", procore_submittal_id="4242")

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=PDF_MIN):
        pull_document(release, 5150, uploaded_by_user_id=drafter.id)
        payload = list_documents(release)

    doc = payload['documents'][0]
    assert doc['attachment_id'] == 5150
    assert doc['attached']['version_number'] == 1
    assert payload['submittal']['resolved_by'] == 'release_link'


def test_role_marks_the_pack_the_worker_linked_on_the_release(app):
    """The release's viewer_url IS the FC pack's attachment viewer — the strongest
    identification we can offer, and it must beat the item_type heuristic."""
    from app.brain.job_log.features.pdf_markup.procore_pull import list_documents

    _make_submittal("4242", "777")
    release = make_release(
        job=340, release="666", procore_submittal_id="4242",
        viewer_url=(
            "https://app.procore.com/1234/project/submittal_logs/view_attachment"
            "?attachment_id=5150&item_id=900&item_type=SubmittalLogApprover&project_id=777"
        ),
    )

    other = {**REF, 'attachment_id': 6000, 'item_type': 'SubmittalLog', 'name': 'Shop set.pdf'}
    with patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[other, REF]):
        payload = list_documents(release)

    # Linked pack sorts first regardless of the order Procore returned.
    assert [d['role'] for d in payload['documents']] == ['final_pack', 'submitted']
    assert payload['documents'][0]['role_evidence'] == 'release_link'
    assert payload['documents'][0]['is_release_linked'] is True
    assert payload['documents'][1]['is_release_linked'] is False


def test_role_follows_item_type_not_procores_originating_flag(app):
    """The bug this replaced: an attachment carrying item_type SubmittalLogApprover was
    labelled 'submitted drawing' because it arrived on the submittal's own attachments."""
    from app.brain.job_log.features.pdf_markup.procore_pull import list_documents

    _make_submittal("4242", "777")
    release = make_release(job=340, release="666", procore_submittal_id="4242")

    mislabelled = {**REF, 'source': 'originating', 'is_originating_attachment': None}
    with patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[mislabelled]):
        doc = list_documents(release)['documents'][0]

    assert doc['role'] == 'approver_copy'
    # Procore's own flag stays visible as secondary evidence, it just doesn't drive the label.
    assert doc['source'] == 'originating'


def test_listing_carries_the_metadata_that_identifies_a_file(app):
    from app.brain.job_log.features.pdf_markup.procore_pull import list_documents

    _make_submittal("4242", "777", title="170-181 Bearing Angles", type="For Construction",
                    status="Approved", ball_in_court="Doug", rel="181", project_number="170")
    release = make_release(job=170, release="181", procore_submittal_id="4242")

    rich = {**REF, 'created_at': '2026-08-30T18:02:00Z', 'created_by': 'Sam Approver',
            'size_bytes': 2_411_724, 'approver_id': 991}
    # The Procore URL is built from the configured company id; pin it so the assertion
    # does not depend on whoever's .env is loaded (CI has none — procore_url was None).
    from app.config import Config as cfg
    with patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[rich]), \
            patch.object(cfg, 'PROD_PROCORE_COMPANY_ID', '18521'):
        payload = list_documents(release)

    doc = payload['documents'][0]
    assert doc['created_by'] == 'Sam Approver'
    assert doc['size_bytes'] == 2_411_724
    assert doc['approver_id'] == 991
    sub = payload['submittal']
    assert (sub['type'], sub['status'], sub['ball_in_court']) == ('For Construction', 'Approved', 'Doug')
    assert sub['procore_url'] == (
        'https://app.procore.com/webclients/host/companies/18521'
        '/projects/777/tools/submittals/4242'
    )


def test_procore_workflow_response_names_the_final_pdf_pack(app):
    """Procore states what a returned drawing is on the approver's Workflow Responses row
    ("Dalton Rauer — Final PDF Pack"), never on the attachment. That beats every heuristic,
    including a release with no viewer_url linked yet."""
    from app.brain.job_log.features.pdf_markup.procore_pull import list_documents

    _make_submittal("4242", "777")
    release = make_release(job=170, release="181", procore_submittal_id="4242")

    pack = {**REF, 'response_name': 'Final PDF Pack', 'approver_name': 'Dalton Rauer',
            'is_final_pdf_response': True}
    shop = {**REF, 'attachment_id': 6000, 'item_type': 'SubmittalLog',
            'name': 'Shop set.pdf', 'is_final_pdf_response': False}

    with patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[shop, pack]):
        docs = list_documents(release)['documents']

    assert docs[0]['role'] == 'final_pack'
    assert docs[0]['role_evidence'] == 'workflow_response'
    assert docs[0]['response_name'] == 'Final PDF Pack'
    assert docs[0]['approver_name'] == 'Dalton Rauer'
    # No viewer_url on the release, so this is Procore's word alone — and that is enough.
    assert docs[0]['is_release_linked'] is False
    assert docs[1]['role'] == 'submitted'


def test_linked_detection_falls_back_to_whole_url_comparison(app):
    """`Releases.viewer_url` is sometimes a submittal *page* URL, which carries no
    attachment_id — the id match can never fire, so compare the URLs themselves."""
    from app.brain.job_log.features.pdf_markup.procore_pull import list_documents

    page_url = 'https://app.procore.com/webclients/host/companies/18521/projects/777/tools/submittals/4242'
    _make_submittal("4242", "777")
    release = make_release(job=170, release="181", procore_submittal_id="4242",
                           viewer_url=page_url)

    same = {**REF, 'viewer_url': page_url}
    other = {**REF, 'attachment_id': 6000, 'viewer_url': 'https://app.procore.com/elsewhere'}
    with patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[same, other]):
        docs = list_documents(release)['documents']

    by_id = {d['attachment_id']: d for d in docs}
    assert by_id[5150]['is_release_linked'] is True
    assert by_id[6000]['is_release_linked'] is False


def test_marked_up_copy_sorts_ahead_of_a_clean_one(app):
    """Two Final PDF Packs, one with markups: the shop builds from the marked-up set."""
    from app.brain.job_log.features.pdf_markup.procore_pull import list_documents

    _make_submittal("4242", "777")
    release = make_release(job=170, release="181", procore_submittal_id="4242")

    clean = {**REF, 'attachment_id': 5150, 'is_final_pdf_response': True,
             'response_name': 'Final PDF Pack', 'has_markup': False}
    marked = {**REF, 'attachment_id': 5151, 'is_final_pdf_response': True,
              'response_name': 'Final PDF Pack', 'has_markup': True}

    with patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[clean, marked]):
        docs = list_documents(release)['documents']

    assert [d['attachment_id'] for d in docs] == [5151, 5150]
    assert docs[0]['has_markup'] is True


def test_pull_records_the_response_and_markups_in_the_version_note(app, storage_root, drafter):
    from app.brain.job_log.features.pdf_markup.procore_pull import pull_document

    _make_submittal("4242", "777")
    release = make_release(job=170, release="181", procore_submittal_id="4242")
    pack = {**REF, 'response_name': 'Final PDF Pack', 'approver_name': 'Dalton Rauer',
            'is_final_pdf_response': True, 'has_markup': True,
            'markup_paths': ['$.markup_count = 3']}

    def _render(*args, meta=None, **kwargs):
        if meta is not None:
            meta.update({'has_markup_evidence': True, 'polls': 2,
                         'markup_paths': ['$.markups[0].id = 7']})
        return PDF_MIN

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[pack]), \
            patch(f'{MODULE}.download_markup_pdf', side_effect=_render):
        version, target = pull_document(release, 5150, uploaded_by_user_id=drafter.id)

    assert 'Final PDF Pack' in version.note
    assert 'markups included' in version.note
    assert target['carried_markup'] is True
    assert target['markup_paths'] == ['$.markup_count = 3', '$.markups[0].id = 7']


def test_pull_does_not_claim_markups_when_nothing_says_there_were_any(app, storage_root, drafter):
    from app.brain.job_log.features.pdf_markup.procore_pull import pull_document

    _make_submittal("4242", "777")
    release = make_release(job=170, release="181", procore_submittal_id="4242")

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=PDF_MIN):
        version, target = pull_document(release, 5150, uploaded_by_user_id=drafter.id)

    assert 'markups included' not in version.note
    assert target['carried_markup'] is False


def test_pull_falls_back_to_the_submittal_log_triple(app, storage_root, drafter):
    """Procore 404s "Item not found" when the posted (item_id, item_type) names no single
    item — which happens when an attachment's viewer and download URLs disagree. The
    render is handed the alternatives; the file itself is fine."""
    from app.brain.job_log.features.pdf_markup.procore_pull import pull_document

    _make_submittal("4242", "777")
    release = make_release(job=170, release="448", procore_submittal_id="4242")
    mixed = {**REF, 'approver_id': 180149488, 'id_candidates': [
        {'item_id': 180149488, 'item_type': 'SubmittalLogApprover',
         'attachment_id': 6050048728, 'project_id': 777, 'source': 'viewer_url'},
    ]}

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[mixed]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=PDF_MIN) as dl:
        pull_document(release, 5150, uploaded_by_user_id=drafter.id)

    # Both attachment ids are crossed with every item candidate — the working pair can be
    # (item from one URL, attachment id from the other). The approver-id fallback dedups
    # into the viewer_url item here: same (id, type).
    alternatives = dl.call_args.kwargs['alternatives']
    sources = [a['source'] for a in alternatives]
    assert sources[0].startswith('viewer_url')
    assert any(s.startswith('submittal_log') for s in sources)
    pairs = {(str(a['item_id']), str(a['attachment_id'])) for a in alternatives}
    assert ('180149488', '6050048728') in pairs
    assert ('180149488', '5150') in pairs
    assert ('4242', '6050048728') in pairs


def test_pull_of_an_attachment_not_on_the_submittal_errors(app, storage_root, drafter):
    from app.brain.job_log.features.pdf_markup.procore_pull import ProcorePullError, pull_document

    _make_submittal("4242", "777")
    release = make_release(job=340, release="666", procore_submittal_id="4242")

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]):
        with pytest.raises(ProcorePullError):
            pull_document(release, 999999, uploaded_by_user_id=drafter.id)


def test_non_pdf_bytes_are_rejected(app, storage_root, drafter):
    from app.brain.job_log.features.pdf_markup.procore_pull import ProcorePullError, pull_document

    _make_submittal("4242", "777")
    release = make_release(job=340, release="666", procore_submittal_id="4242")

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=b'<html>nope</html>'):
        with pytest.raises(ProcorePullError):
            pull_document(release, 5150, uploaded_by_user_id=drafter.id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_documents_route_returns_candidates(app, client, storage_root, drafter):
    _make_submittal("4242", "777", title="340-666 FC")
    release = make_release(job=340, release="666", procore_submittal_id="4242")
    from app.models import db
    db.session.commit()

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]):
        resp = client.get(f'/brain/releases/{release.id}/procore-documents')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['submittal']['submittal_id'] == '4242'
    assert body['documents'][0]['source'] == 'approver'


def test_documents_route_409s_when_nothing_is_linked(app, client, storage_root, drafter):
    release = make_release(job=341, release="667")
    from app.models import db
    db.session.commit()

    with _patch_user(drafter):
        resp = client.get(f'/brain/releases/{release.id}/procore-documents')

    assert resp.status_code == 409
    assert resp.get_json()['resolvable'] is False


def test_pull_route_attaches_and_returns_the_version(app, client, storage_root, drafter):
    _make_submittal("4242", "777")
    release = make_release(job=340, release="666", procore_submittal_id="4242")
    from app.models import db
    db.session.commit()

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=PDF_MIN):
        resp = client.post(f'/brain/releases/{release.id}/procore-documents/5150/pull')

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['version']['version_number'] == 1
    assert body['pulled']['source'] == 'approver'


def test_pull_route_502s_when_procore_returns_nothing(app, client, storage_root, drafter):
    _make_submittal("4242", "777")
    release = make_release(job=340, release="666", procore_submittal_id="4242")
    from app.models import db
    db.session.commit()

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=None):
        resp = client.post(f'/brain/releases/{release.id}/procore-documents/5150/pull')

    assert resp.status_code == 502


def test_raw_download_rescues_a_pull_the_markup_renderer_refuses(app, storage_root, drafter):
    """Procore 404s every id triple but still holds the file. A clean copy beats no
    drawing — provided the version says it is clean."""
    from app.brain.job_log.features.pdf_markup.procore_pull import pull_document

    _make_submittal("4242", "777")
    release = make_release(job=170, release="448", procore_submittal_id="4242")
    pack = {**REF, 'response_name': 'Final PDF Pack', 'is_final_pdf_response': True,
            'has_markup': True}

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[pack]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=None), \
            patch(f'{MODULE}.download_attachment_raw', return_value=PDF_MIN) as raw:
        version, target = pull_document(release, 5150, uploaded_by_user_id=drafter.id)

    raw.assert_called_once()
    assert version.version_number == 1
    assert 'clean copy' in version.note
    # The payload said there were markups, but these bytes never went through the renderer.
    assert target['carried_markup'] is False
    assert target['render_fallback'] == 'raw_attachment'


def test_pull_errors_only_when_the_raw_download_also_fails(app, storage_root, drafter):
    from app.brain.job_log.features.pdf_markup.procore_pull import ProcorePullError, pull_document

    _make_submittal("4242", "777")
    release = make_release(job=170, release="448", procore_submittal_id="4242")

    with _patch_user(drafter), \
            patch(f'{MODULE}.find_submittal_drawing_refs', return_value=[REF]), \
            patch(f'{MODULE}.download_markup_pdf', return_value=None), \
            patch(f'{MODULE}.download_attachment_raw', return_value=None):
        with pytest.raises(ProcorePullError):
            pull_document(release, 5150, uploaded_by_user_id=drafter.id)
