"""Splice families share one document hub (T9, 2026-09-23).

A release and its splices (340, 340.1, 340.2) are one family for documents:
  - `drawing/versions?family=1` from ANY member lists every member's files, each tagged
    with the release it is attached to (archived splices in, soft-deleted ones out).
  - A Final PDF Pack pull from a splice resolves the ORIGINAL's submittal and lands on the
    original; "already attached" is read across the family.

Procore is always mocked (tests/README.md) at the point the puller imports it.
"""

from __future__ import annotations

import io
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

PULL = 'app.brain.job_log.features.pdf_markup.procore_pull'


@pytest.fixture
def storage_root(tmp_path, app):
    app.config['PDF_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


@pytest.fixture
def drafter(app):
    return make_user("splicedocs", is_drafter=True)


@pytest.fixture
def family(app):
    """340-666 with two splices; .2 is archived (its files still count)."""
    from app.models import db
    parent = make_release(job=340, release="666", procore_submittal_id="4242")
    s1 = make_release(job=340, release="666.1", parent_release_id=parent.id)
    s2 = make_release(job=340, release="666.2", parent_release_id=parent.id, is_archived=True)
    db.session.commit()
    return parent, s1, s2


def _as(user):
    stack = ExitStack()
    for target in (
        'app.auth.utils.get_current_user',
        'app.brain.job_log.pdf_markup_routes.get_current_user',
        'app.services.job_event_service.get_current_user',
    ):
        stack.enter_context(patch(target, return_value=user))
    return stack


def _upload(client, release_id, name, source_version_id=None):
    data = {'file': (io.BytesIO(PDF_MIN), name)}
    if source_version_id is not None:
        data['source_version_id'] = str(source_version_id)
    resp = client.post(f'/brain/releases/{release_id}/drawing',
                       data=data, content_type='multipart/form-data')
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _make_submittal(submittal_id="4242", project_id="777"):
    from app.models import Submittals, db
    db.session.add(Submittals(submittal_id=submittal_id, procore_project_id=project_id))
    db.session.flush()


# ---------------------------------------------------------------------------
# Family helpers
# ---------------------------------------------------------------------------


def test_origin_of_a_splice_is_its_parent_and_of_an_original_is_itself(app, family):
    from app.brain.job_log.features.splice.command import splice_origin

    parent, s1, _ = family
    assert splice_origin(s1).id == parent.id
    assert splice_origin(parent).id == parent.id


def test_family_is_the_same_from_every_member_and_drops_soft_deleted(app, family):
    from app.brain.job_log.features.splice.command import release_family
    from app.models import db

    parent, s1, s2 = family
    gone = make_release(job=340, release="666.3", parent_release_id=parent.id, is_active=False)
    db.session.commit()

    expected = [parent.id, s1.id, s2.id]
    for member in (parent, s1, s2):
        assert [r.id for r in release_family(member)] == expected
    assert gone.id not in expected


# ---------------------------------------------------------------------------
# drawing/versions?family=1
# ---------------------------------------------------------------------------


def test_family_listing_shows_every_members_files_from_any_member(app, storage_root, family, drafter):
    parent, s1, s2 = family
    with _as(drafter):
        client = app.test_client()
        p1 = _upload(client, parent.id, "parent.pdf")
        _upload(client, parent.id, "parent-v2.pdf", source_version_id=p1['id'])
        _upload(client, s1.id, "splice1.pdf")
        _upload(client, s2.id, "splice2.pdf")

        bodies = [client.get(f'/brain/releases/{rid}/drawing/versions?family=1').get_json()
                  for rid in (parent.id, s1.id, s2.id)]

    for body in bodies:
        # Original first (newest version first within it), then splices in creation order.
        assert [(v['release_label'], v['version_number']) for v in body['versions']] == [
            ('340-666', 2), ('340-666', 1), ('340-666.1', 1), ('340-666.2', 1),
        ]
        by_label = {v['release_label']: v for v in body['versions']}
        assert by_label['340-666.1']['release_id'] == s1.id
        assert by_label['340-666.1']['is_splice'] is True
        assert by_label['340-666']['is_splice'] is False
        assert [(m['release_label'], m['is_archived']) for m in body['family']] == [
            ('340-666', False), ('340-666.1', False), ('340-666.2', True),
        ]


def test_listing_without_family_flag_stays_one_release(app, storage_root, family, drafter):
    parent, s1, _ = family
    with _as(drafter):
        client = app.test_client()
        _upload(client, parent.id, "parent.pdf")
        _upload(client, s1.id, "splice1.pdf")
        body = client.get(f'/brain/releases/{s1.id}/drawing/versions').get_json()

    assert [v['release_id'] for v in body['versions']] == [s1.id]
    assert 'family' not in body


def test_family_versions_are_still_owned_by_their_release(app, storage_root, family, drafter):
    """A sibling's file is read through ITS release's routes, never the open row's."""
    parent, s1, _ = family
    with _as(drafter):
        client = app.test_client()
        v = _upload(client, s1.id, "splice1.pdf")
        own = client.get(f'/brain/releases/{s1.id}/drawing/versions/{v["id"]}/file')
        via_parent = client.get(f'/brain/releases/{parent.id}/drawing/versions/{v["id"]}/file')

    assert own.status_code == 200
    assert via_parent.status_code == 404


def test_a_soft_deleted_splice_opened_directly_still_sees_its_own_files(app, storage_root, family, drafter):
    from app.models import db
    parent, s1, _ = family
    with _as(drafter):
        client = app.test_client()
        _upload(client, s1.id, "splice1.pdf")
        s1.is_active = False
        db.session.commit()
        body = client.get(f'/brain/releases/{s1.id}/drawing/versions?family=1').get_json()

    assert s1.id in [v['release_id'] for v in body['versions']]


# ---------------------------------------------------------------------------
# Final PDF Pack pull from a splice
# ---------------------------------------------------------------------------


def test_pull_from_a_splice_resolves_and_lands_on_the_original(app, storage_root, family, drafter):
    from app.brain.job_log.features.pdf_markup.procore_pull import pull_document
    from app.models import ReleaseDrawingVersion

    parent, s1, _ = family
    _make_submittal()
    with _as(drafter), \
            patch(f'{PULL}.find_submittal_drawing_refs', return_value=[REF]) as refs, \
            patch(f'{PULL}.download_markup_pdf', return_value=PDF_MIN):
        version, _ = pull_document(s1, 5150, uploaded_by_user_id=drafter.id)

    # The splice has no submittal link of its own; the original's is what was asked for.
    assert refs.call_args.args == ("777", "4242")
    assert version.release_id == parent.id
    assert ReleaseDrawingVersion.query.filter_by(release_id=s1.id).count() == 0


def test_listing_from_a_splice_names_the_original_as_where_pulls_land(app, family):
    from app.brain.job_log.features.pdf_markup.procore_pull import list_documents

    parent, s1, _ = family
    _make_submittal()
    with patch(f'{PULL}.find_submittal_drawing_refs', return_value=[REF]):
        from_splice = list_documents(s1)
        from_parent = list_documents(parent)

    assert from_splice['submittal']['submittal_id'] == '4242'
    assert from_splice['pack_release'] == {
        'release_id': parent.id, 'release_label': '340-666', 'via_splice': True,
    }
    assert from_parent['pack_release']['via_splice'] is False


def test_already_attached_is_read_across_the_family(app, storage_root, family, drafter):
    """A pack that sits on any member (e.g. pulled onto a splice before this change)
    reads as attached from every member."""
    from app.brain.job_log.features.pdf_markup.procore_pull import PULL_NOTE, list_documents

    parent, s1, s2 = family
    _make_submittal()
    with _as(drafter):
        _upload(app.test_client(), s2.id, "Final PDF Pack.pdf")
    from app.models import ReleaseDrawingVersion, db
    v = ReleaseDrawingVersion.query.filter_by(release_id=s2.id).one()
    v.note = PULL_NOTE.format(submittal_id="4242", attachment_id=5150)
    db.session.commit()

    with patch(f'{PULL}.find_submittal_drawing_refs', return_value=[REF]):
        for member in (parent, s1):
            attached = list_documents(member)['documents'][0]['attached']
            assert attached['release_id'] == s2.id
            assert attached['version_id'] == v.id


def test_pull_route_from_a_splice_returns_the_originals_version(app, client, storage_root, family, drafter):
    parent, s1, _ = family
    _make_submittal()
    from app.models import db
    db.session.commit()

    with _as(drafter), \
            patch(f'{PULL}.find_submittal_drawing_refs', return_value=[REF]), \
            patch(f'{PULL}.download_markup_pdf', return_value=PDF_MIN):
        resp = client.post(f'/brain/releases/{s1.id}/procore-documents/5150/pull')

    assert resp.status_code == 201
    assert resp.get_json()['version']['release_id'] == parent.id
