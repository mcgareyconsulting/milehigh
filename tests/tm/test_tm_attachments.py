"""Tests for T&M ticket photo/video attachments: the upload command and the
HTTP routes.

Mirrors tests/brain/test_board_photos.py, plus a draft-only gate that board
photos don't have: attachments can only be added/removed while the parent
ticket is still a draft.
"""
from __future__ import annotations

import io
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from tests.conftest import make_user

# A 1x1 PNG (valid magic bytes).
PNG_MIN = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal ISO-BMFF ftyp box with an 'isom' brand — enough for sniff_video_mime.
MP4_MIN = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00" + b"\x00" * 8


@pytest.fixture
def storage_root(tmp_path, app):
    app.config['PHOTO_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


@pytest.fixture
def admin_user(app):
    return make_user("tm_photo_admin", is_admin=True)


@pytest.fixture
def non_admin_user(app):
    return make_user("tm_photo_grunt", is_admin=False)


@pytest.fixture
def ticket_id(app, admin_user):
    from app.models import TMTicket, db
    ticket = TMTicket(status="draft", created_by=admin_user.username)
    db.session.add(ticket)
    db.session.commit()
    return ticket.id


def _patch_get_current_user(user):
    targets = (
        'app.auth.utils.get_current_user',  # used by @admin_required
        'app.brain.tm.photos.routes.get_current_user',
    )
    stack = ExitStack()
    for t in targets:
        stack.enter_context(patch(t, return_value=user))
    return stack


def _post_attachment(client, ticket_id, payload, *, filename="x.png"):
    data = {'file': (io.BytesIO(payload), filename)}
    return client.post(
        f'/brain/tm-tickets/{ticket_id}/attachments',
        data=data,
        content_type='multipart/form-data',
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_upload_requires_login(app, storage_root, ticket_id):
    with _patch_get_current_user(None):
        client = app.test_client()
        resp = _post_attachment(client, ticket_id, PNG_MIN)
    assert resp.status_code == 401


def test_upload_forbidden_for_non_admin(app, storage_root, ticket_id, non_admin_user):
    with _patch_get_current_user(non_admin_user):
        client = app.test_client()
        resp = _post_attachment(client, ticket_id, PNG_MIN)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


def test_upload_image_returns_201_and_writes_file(app, storage_root, ticket_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        resp = _post_attachment(client, ticket_id, PNG_MIN)

    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body['mime_type'] == 'image/png'
    assert body['is_video'] is False
    assert body['tm_ticket_id'] == ticket_id
    assert body['uploaded_by']['name'] == admin_user.username
    assert (storage_root / 'tm' / str(ticket_id) / f"{body['id']}.png").is_file()


def test_upload_video_returns_201_and_writes_file(app, storage_root, ticket_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        resp = _post_attachment(client, ticket_id, MP4_MIN, filename="clip.mp4")

    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body['mime_type'] == 'video/mp4'
    assert body['is_video'] is True
    assert (storage_root / 'tm' / str(ticket_id) / f"{body['id']}.mp4").is_file()


def test_upload_to_missing_ticket_returns_404(app, storage_root, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        resp = _post_attachment(client, 999999, PNG_MIN)
    assert resp.status_code == 404


def test_non_media_returns_400(app, storage_root, ticket_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        resp = _post_attachment(client, ticket_id, b"%PDF-not-media", filename="x.pdf")
    assert resp.status_code == 400


def test_upload_to_non_draft_ticket_returns_400(app, storage_root, ticket_id, admin_user):
    from app.models import TMTicket, db
    ticket = db.session.get(TMTicket, ticket_id)
    ticket.status = "submitted"
    db.session.commit()

    with _patch_get_current_user(admin_user):
        client = app.test_client()
        resp = _post_attachment(client, ticket_id, PNG_MIN)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# List / file / delete
# ---------------------------------------------------------------------------


def test_list_excludes_deleted_newest_first(app, storage_root, ticket_id, admin_user):
    from app.models import TMTicketAttachment, db

    with _patch_get_current_user(admin_user):
        client = app.test_client()
        first = _post_attachment(client, ticket_id, PNG_MIN)
        second = _post_attachment(client, ticket_id, PNG_MIN)
        assert first.status_code == 201 and second.status_code == 201
        first_id = first.get_json()['id']
        second_id = second.get_json()['id']

        a1 = db.session.get(TMTicketAttachment, first_id)
        a1.is_deleted = True
        db.session.commit()

        resp = client.get(f'/brain/tm-tickets/{ticket_id}/attachments')

    assert resp.status_code == 200
    attachments = resp.get_json()['attachments']
    assert [a['id'] for a in attachments] == [second_id]


def test_get_file_streams_image(app, storage_root, ticket_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        aid = _post_attachment(client, ticket_id, PNG_MIN).get_json()['id']
        resp = client.get(f'/brain/tm-tickets/{ticket_id}/attachments/{aid}/file')

    assert resp.status_code == 200
    assert resp.content_type == 'image/png'
    assert resp.data == PNG_MIN


def test_delete_soft_deletes(app, storage_root, ticket_id, admin_user):
    from app.models import TMTicketAttachment, db

    with _patch_get_current_user(admin_user):
        client = app.test_client()
        aid = _post_attachment(client, ticket_id, PNG_MIN).get_json()['id']
        resp = client.delete(f'/brain/tm-tickets/{ticket_id}/attachments/{aid}')

        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'
        attachment = db.session.get(TMTicketAttachment, aid)
        assert attachment.is_deleted is True


def test_delete_already_deleted_is_idempotent(app, storage_root, ticket_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        aid = _post_attachment(client, ticket_id, PNG_MIN).get_json()['id']
        first = client.delete(f'/brain/tm-tickets/{ticket_id}/attachments/{aid}')
        second = client.delete(f'/brain/tm-tickets/{ticket_id}/attachments/{aid}')

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()['status'] == 'already_deleted'


def test_delete_on_non_draft_ticket_returns_400(app, storage_root, ticket_id, admin_user):
    from app.models import TMTicket, db

    with _patch_get_current_user(admin_user):
        client = app.test_client()
        aid = _post_attachment(client, ticket_id, PNG_MIN).get_json()['id']

        ticket = db.session.get(TMTicket, ticket_id)
        ticket.status = "approved"
        db.session.commit()

        resp = client.delete(f'/brain/tm-tickets/{ticket_id}/attachments/{aid}')
    assert resp.status_code == 400
