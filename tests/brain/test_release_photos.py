"""Tests for the release photo attachments feature: image sniffing, the upload
command, and the HTTP routes.

Mirrors test_pdf_markup.py. Photos are open to any logged-in user (unlike
drawings), so the auth checks differ.
"""

from __future__ import annotations

import io
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from tests.conftest import make_release, make_user

# A 1x1 PNG (valid magic bytes).
PNG_MIN = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def storage_root(tmp_path, app):
    app.config['PHOTO_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


@pytest.fixture
def release_id(app):
    r = make_release(job=888, release="P", job_name="Photo test")
    from app.models import db
    db.session.commit()
    return r.id


@pytest.fixture
def plain_user(app):
    return make_user("photographer1")


def _patch_get_current_user(user):
    targets = (
        'app.auth.utils.get_current_user',
        'app.brain.job_log.photo_routes.get_current_user',
        'app.services.job_event_service.get_current_user',
    )
    stack = ExitStack()
    for t in targets:
        stack.enter_context(patch(t, return_value=user))
    return stack


def _post_photo(client, release_id, payload, *, note=None, stage=None, filename="x.png"):
    data = {'file': (io.BytesIO(payload), filename)}
    if note is not None:
        data['note'] = note
    if stage is not None:
        data['stage'] = stage
    return client.post(
        f'/brain/releases/{release_id}/photos',
        data=data,
        content_type='multipart/form-data',
    )


# ---------------------------------------------------------------------------
# Image sniffing
# ---------------------------------------------------------------------------


def test_sniff_recognizes_png_and_jpeg():
    from app.brain.job_log.features.photos.payloads import sniff_image_mime

    assert sniff_image_mime(PNG_MIN) == 'image/png'
    assert sniff_image_mime(b"\xff\xd8\xff\xe0" + b"0" * 20) == 'image/jpeg'
    assert sniff_image_mime(b"not an image at all") is None


def test_is_probably_image_falls_back_to_mimetype_and_name():
    from app.brain.job_log.features.photos.payloads import is_probably_image

    # HEIC has no png/jpeg magic but should pass via mimetype/name.
    assert is_probably_image(b"junkjunkjunk", 'image/heic', 'IMG.HEIC')
    assert is_probably_image(b"junkjunkjunk", '', 'photo.jpg')
    assert not is_probably_image(b"%PDF-1.4 stuff", 'application/pdf', 'x.pdf')


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_upload_allowed_for_plain_user_returns_201(app, storage_root, release_id, plain_user):
    with _patch_get_current_user(plain_user):
        client = app.test_client()
        resp = _post_photo(client, release_id, PNG_MIN, note="north wall")

    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body['note'] == "north wall"
    assert body['mime_type'] == 'image/png'
    assert (storage_root / str(release_id) / f"{body['id']}.png").is_file()


def test_upload_requires_login(app, storage_root, release_id):
    with _patch_get_current_user(None):
        client = app.test_client()
        resp = _post_photo(client, release_id, PNG_MIN)
    assert resp.status_code == 401


def test_upload_with_valid_stage_tag_is_stored(app, storage_root, release_id, plain_user):
    with _patch_get_current_user(plain_user):
        client = app.test_client()
        resp = _post_photo(client, release_id, PNG_MIN, stage="Welded QC")

    assert resp.status_code == 201, resp.data
    assert resp.get_json()['stage'] == "Welded QC"


def test_upload_with_unknown_stage_returns_400(app, storage_root, release_id, plain_user):
    with _patch_get_current_user(plain_user):
        client = app.test_client()
        resp = _post_photo(client, release_id, PNG_MIN, stage="Not A Stage")
    assert resp.status_code == 400


def test_non_image_returns_400(app, storage_root, release_id, plain_user):
    with _patch_get_current_user(plain_user):
        client = app.test_client()
        resp = _post_photo(client, release_id, b"%PDF-not-an-image", filename="x.pdf")
    assert resp.status_code == 400


def test_list_excludes_deleted_newest_first(app, storage_root, release_id, plain_user):
    from app.models import ReleasePhoto, db

    with _patch_get_current_user(plain_user):
        client = app.test_client()
        first = _post_photo(client, release_id, PNG_MIN, note="one")
        second = _post_photo(client, release_id, PNG_MIN, note="two")
        assert first.status_code == 201 and second.status_code == 201

        p1 = db.session.get(ReleasePhoto, first.get_json()['id'])
        p1.is_deleted = True
        db.session.commit()

        resp = client.get(f'/brain/releases/{release_id}/photos')

    assert resp.status_code == 200
    photos = resp.get_json()['photos']
    assert [p['note'] for p in photos] == ['two']


def test_get_file_streams_image(app, storage_root, release_id, plain_user):
    with _patch_get_current_user(plain_user):
        client = app.test_client()
        upload = _post_photo(client, release_id, PNG_MIN)
        pid = upload.get_json()['id']
        resp = client.get(f'/brain/releases/{release_id}/photos/{pid}/file')

    assert resp.status_code == 200
    assert resp.content_type == 'image/png'
    assert resp.data == PNG_MIN


def test_patch_updates_note(app, storage_root, release_id, plain_user):
    with _patch_get_current_user(plain_user):
        client = app.test_client()
        pid = _post_photo(client, release_id, PNG_MIN, note="old").get_json()['id']
        resp = client.patch(
            f'/brain/releases/{release_id}/photos/{pid}',
            json={'note': 'updated note'},
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['note'] == 'updated note'
    # Editing the note attributes the change to the current user.
    assert body['last_edited_by'] == {'id': plain_user.id, 'name': plain_user.username}
    assert body['last_edited_at'] is not None


def test_patch_unchanged_note_does_not_stamp_editor(app, storage_root, release_id, plain_user):
    with _patch_get_current_user(plain_user):
        client = app.test_client()
        pid = _post_photo(client, release_id, PNG_MIN, note="same").get_json()['id']
        resp = client.patch(
            f'/brain/releases/{release_id}/photos/{pid}',
            json={'note': 'same'},
        )

    assert resp.status_code == 200
    # Re-saving an unchanged note leaves edit attribution untouched.
    assert resp.get_json()['last_edited_by'] is None


def test_patch_empty_note_clears_it(app, storage_root, release_id, plain_user):
    with _patch_get_current_user(plain_user):
        client = app.test_client()
        pid = _post_photo(client, release_id, PNG_MIN, note="something").get_json()['id']
        resp = client.patch(
            f'/brain/releases/{release_id}/photos/{pid}',
            json={'note': '   '},
        )

    assert resp.status_code == 200
    assert resp.get_json()['note'] is None


def test_delete_soft_deletes(app, storage_root, release_id, plain_user):
    from app.models import ReleasePhoto, db

    with _patch_get_current_user(plain_user):
        client = app.test_client()
        pid = _post_photo(client, release_id, PNG_MIN).get_json()['id']
        resp = client.delete(f'/brain/releases/{release_id}/photos/{pid}')

        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'
        photo = db.session.get(ReleasePhoto, pid)
        assert photo.is_deleted is True
