"""Tests for the PDF markup feature: storage helpers, commands, and HTTP routes.

The shared `app` fixture (tests/conftest.py) wraps each test in a single
app_context so we never create nested ones inside a test — that would detach
fixtures-created ORM rows from the live session.
"""

from __future__ import annotations

import io
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from tests.conftest import make_release, make_user

PDF_MIN = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def storage_root(tmp_path, app):
    """Point the PDF storage helpers at a tmp directory for the test."""
    app.config['PDF_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


@pytest.fixture
def release_id(app):
    r = make_release(job=999, release="A", job_name="Markup test")
    from app.models import db
    db.session.commit()
    return r.id


@pytest.fixture
def drafter_user(app):
    return make_user("drafter1", is_drafter=True)


@pytest.fixture
def admin_user(app):
    return make_user("admin1", is_admin=True)


@pytest.fixture
def plain_user(app):
    return make_user("plain1")


def _patch_get_current_user(user):
    """Patch every binding of get_current_user that the routes/services consult."""
    targets = (
        'app.auth.utils.get_current_user',
        'app.brain.job_log.routes.get_current_user',
        'app.brain.job_log.pdf_markup_routes.get_current_user',
        'app.services.job_event_service.get_current_user',
    )
    stack = ExitStack()
    for t in targets:
        stack.enter_context(patch(t, return_value=user))
    return stack


def _post_pdf(client, release_id, payload, *, source_version_id=None, note=None, filename="x.pdf"):
    data = {'file': (io.BytesIO(payload), filename)}
    if source_version_id is not None:
        data['source_version_id'] = str(source_version_id)
    if note is not None:
        data['note'] = note
    return client.post(
        f'/brain/releases/{release_id}/drawing',
        data=data,
        content_type='multipart/form-data',
    )


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def test_storage_save_and_read_roundtrip(app, storage_root):
    from app.brain.job_log.features.pdf_markup.storage import save_pdf, read_pdf

    key = save_pdf(release_id=42, version=1, data=PDF_MIN)
    assert key == "42/v1.pdf"
    assert (storage_root / "42" / "v1.pdf").is_file()
    assert read_pdf(key) == PDF_MIN


def test_storage_save_overwrites_same_version(app, storage_root):
    from app.brain.job_log.features.pdf_markup.storage import save_pdf, read_pdf

    save_pdf(7, 1, b"%PDF-original")
    save_pdf(7, 1, b"%PDF-replaced")
    assert read_pdf("7/v1.pdf") == b"%PDF-replaced"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def test_upload_initial_drawing_creates_v1_and_event(app, storage_root, release_id, drafter_user):
    from app.brain.job_log.features.pdf_markup.command import UploadInitialDrawingCommand
    from app.models import ReleaseDrawingVersion, ReleaseEvents

    with _patch_get_current_user(drafter_user):
        version = UploadInitialDrawingCommand(
            release_id=release_id,
            file_bytes=PDF_MIN,
            filename="orig.pdf",
            mime_type='application/pdf',
            uploaded_by_user_id=drafter_user.id,
            note="first",
        ).execute()

    assert version.version_number == 1
    assert version.source_version_id is None
    assert (storage_root / f"{release_id}" / "v1.pdf").is_file()

    all_versions = ReleaseDrawingVersion.query.filter_by(release_id=release_id).all()
    assert len(all_versions) == 1

    events = ReleaseEvents.query.filter_by(action='upload_drawing').all()
    assert len(events) == 1
    assert events[0].payload['to']['version'] == 1
    assert events[0].payload['to']['version_id'] == version.id


def test_upload_initial_when_version_exists_raises(app, storage_root, release_id, drafter_user):
    from app.brain.job_log.features.pdf_markup.command import UploadInitialDrawingCommand

    with _patch_get_current_user(drafter_user):
        UploadInitialDrawingCommand(
            release_id=release_id, file_bytes=PDF_MIN, filename="orig.pdf",
            mime_type='application/pdf', uploaded_by_user_id=drafter_user.id,
        ).execute()

        with pytest.raises(ValueError):
            UploadInitialDrawingCommand(
                release_id=release_id, file_bytes=PDF_MIN, filename="dup.pdf",
                mime_type='application/pdf', uploaded_by_user_id=drafter_user.id,
            ).execute()


def test_save_drawing_version_increments_and_links_source(app, storage_root, release_id, drafter_user):
    from app.brain.job_log.features.pdf_markup.command import (
        SaveDrawingVersionCommand,
        UploadInitialDrawingCommand,
    )
    from app.models import ReleaseDrawingVersion, ReleaseEvents

    with _patch_get_current_user(drafter_user):
        v1 = UploadInitialDrawingCommand(
            release_id=release_id, file_bytes=PDF_MIN, filename="orig.pdf",
            mime_type='application/pdf', uploaded_by_user_id=drafter_user.id,
        ).execute()

        v2 = SaveDrawingVersionCommand(
            release_id=release_id, file_bytes=PDF_MIN + b"\n% v2 marks",
            uploaded_by_user_id=drafter_user.id, source_version_id=v1.id,
            note="added strokes",
        ).execute()

    assert v2.version_number == 2
    assert v2.source_version_id == v1.id
    all_versions = ReleaseDrawingVersion.query.filter_by(release_id=release_id).order_by(
        ReleaseDrawingVersion.version_number
    ).all()
    assert [v.version_number for v in all_versions] == [1, 2]

    save_events = ReleaseEvents.query.filter_by(action='save_drawing_version').all()
    assert len(save_events) == 1
    assert save_events[0].payload['to']['source_version_id'] == v1.id


def test_command_unlinks_file_when_db_commit_fails(app, storage_root, release_id, drafter_user):
    from app.brain.job_log.features.pdf_markup.command import UploadInitialDrawingCommand
    from app.models import db

    original_commit = db.session.commit

    def boom():
        raise RuntimeError("simulated commit failure")

    db.session.commit = boom
    try:
        with _patch_get_current_user(drafter_user):
            with pytest.raises(RuntimeError):
                UploadInitialDrawingCommand(
                    release_id=release_id, file_bytes=PDF_MIN, filename="orig.pdf",
                    mime_type='application/pdf', uploaded_by_user_id=drafter_user.id,
                ).execute()
    finally:
        db.session.commit = original_commit

    assert not (storage_root / f"{release_id}" / "v1.pdf").exists()


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_post_first_upload_returns_201_with_v1(app, storage_root, release_id, drafter_user):
    with _patch_get_current_user(drafter_user):
        client = app.test_client()
        resp = _post_pdf(client, release_id, PDF_MIN, note="initial")

    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body['version_number'] == 1
    assert body['source_version_id'] is None
    assert body['note'] == "initial"


def test_post_second_upload_requires_source_version_id(app, storage_root, release_id, drafter_user):
    with _patch_get_current_user(drafter_user):
        client = app.test_client()
        first = _post_pdf(client, release_id, PDF_MIN)
        assert first.status_code == 201

        second = _post_pdf(client, release_id, PDF_MIN + b"\n% v2")
        assert second.status_code == 400

        v1_id = first.get_json()['id']
        third = _post_pdf(client, release_id, PDF_MIN + b"\n% v2", source_version_id=v1_id)

    assert third.status_code == 201
    assert third.get_json()['version_number'] == 2


def test_get_versions_lists_desc_excludes_deleted(app, storage_root, release_id, drafter_user):
    from app.models import ReleaseDrawingVersion, db

    with _patch_get_current_user(drafter_user):
        client = app.test_client()
        first = _post_pdf(client, release_id, PDF_MIN)
        v1_id = first.get_json()['id']
        second = _post_pdf(client, release_id, PDF_MIN + b"\n%v2", source_version_id=v1_id)
        assert second.status_code == 201

        v1 = db.session.get(ReleaseDrawingVersion, v1_id)
        v1.is_deleted = True
        db.session.commit()

        resp = client.get(f'/brain/releases/{release_id}/drawing/versions')

    assert resp.status_code == 200
    versions = resp.get_json()['versions']
    assert [v['version_number'] for v in versions] == [2]


def test_get_file_streams_pdf(app, storage_root, release_id, drafter_user):
    with _patch_get_current_user(drafter_user):
        client = app.test_client()
        upload = _post_pdf(client, release_id, PDF_MIN)
        vid = upload.get_json()['id']
        resp = client.get(f'/brain/releases/{release_id}/drawing/versions/{vid}/file')

    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
    assert resp.data == PDF_MIN


def test_delete_requires_admin(app, storage_root, release_id, drafter_user, admin_user):
    with _patch_get_current_user(drafter_user):
        client = app.test_client()
        upload = _post_pdf(client, release_id, PDF_MIN)
        vid = upload.get_json()['id']
        forbidden = client.delete(f'/brain/releases/{release_id}/drawing/versions/{vid}')

    assert forbidden.status_code == 403

    with _patch_get_current_user(admin_user):
        admin_resp = app.test_client().delete(f'/brain/releases/{release_id}/drawing/versions/{vid}')

    assert admin_resp.status_code == 200, admin_resp.data


def test_upload_forbidden_for_non_drafter_non_admin(app, storage_root, release_id, plain_user):
    with _patch_get_current_user(plain_user):
        client = app.test_client()
        resp = _post_pdf(client, release_id, PDF_MIN)
    assert resp.status_code == 403


def test_upload_allowed_for_admin_without_drafter_flag(app, storage_root, release_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        resp = _post_pdf(client, release_id, PDF_MIN)
    assert resp.status_code == 201


def test_non_pdf_returns_400(app, storage_root, release_id, drafter_user):
    with _patch_get_current_user(drafter_user):
        client = app.test_client()
        resp = _post_pdf(client, release_id, b"not a pdf at all", filename="x.pdf")
    assert resp.status_code == 400


def test_oversize_upload_returns_413(app, storage_root, release_id, drafter_user):
    app.config['MAX_CONTENT_LENGTH'] = 1024
    with _patch_get_current_user(drafter_user):
        client = app.test_client()
        resp = _post_pdf(client, release_id, b"%PDF-" + b"x" * 4096)
    assert resp.status_code == 413
