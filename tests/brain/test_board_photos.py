"""Tests for the board (bug tracker) photo attachments feature: the upload
command and the HTTP routes.

Mirrors test_release_photos.py, but board routes are admin-only, so the auth
checks differ (403 for non-admins).
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


@pytest.fixture
def storage_root(tmp_path, app):
    app.config['PHOTO_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


@pytest.fixture
def admin_user(app):
    return make_user("board_admin", is_admin=True)


@pytest.fixture
def non_admin_user(app):
    return make_user("board_grunt", is_admin=False)


@pytest.fixture
def item_id(app, admin_user):
    from app.models import BoardItem, db
    item = BoardItem(
        title="Photo test card",
        body="needs a screenshot",
        category="General",
        author_id=admin_user.id,
        author_name=admin_user.first_name or admin_user.username,
    )
    db.session.add(item)
    db.session.commit()
    return item.id


def _patch_get_current_user(user):
    targets = (
        'app.auth.utils.get_current_user',  # used by @admin_required
        'app.brain.board.photo_routes.get_current_user',
    )
    stack = ExitStack()
    for t in targets:
        stack.enter_context(patch(t, return_value=user))
    return stack


def _post_photo(client, item_id, payload, *, filename="x.png"):
    data = {'file': (io.BytesIO(payload), filename)}
    return client.post(
        f'/brain/board/items/{item_id}/photos',
        data=data,
        content_type='multipart/form-data',
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_upload_requires_login(app, storage_root, item_id):
    with _patch_get_current_user(None):
        client = app.test_client()
        resp = _post_photo(client, item_id, PNG_MIN)
    assert resp.status_code == 401


def test_upload_forbidden_for_non_admin(app, storage_root, item_id, non_admin_user):
    with _patch_get_current_user(non_admin_user):
        client = app.test_client()
        resp = _post_photo(client, item_id, PNG_MIN)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_upload_returns_201_and_writes_file(app, storage_root, item_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        resp = _post_photo(client, item_id, PNG_MIN)

    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body['mime_type'] == 'image/png'
    assert body['board_item_id'] == item_id
    assert (storage_root / 'board' / str(item_id) / f"{body['id']}.png").is_file()


def test_upload_to_missing_item_returns_404(app, storage_root, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        resp = _post_photo(client, 999999, PNG_MIN)
    assert resp.status_code == 404


def test_non_image_returns_400(app, storage_root, item_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        resp = _post_photo(client, item_id, b"%PDF-not-an-image", filename="x.pdf")
    assert resp.status_code == 400


def test_list_excludes_deleted_newest_first(app, storage_root, item_id, admin_user):
    from app.models import BoardItemPhoto, db

    with _patch_get_current_user(admin_user):
        client = app.test_client()
        first = _post_photo(client, item_id, PNG_MIN)
        second = _post_photo(client, item_id, PNG_MIN)
        assert first.status_code == 201 and second.status_code == 201
        first_id = first.get_json()['id']
        second_id = second.get_json()['id']

        p1 = db.session.get(BoardItemPhoto, first_id)
        p1.is_deleted = True
        db.session.commit()

        resp = client.get(f'/brain/board/items/{item_id}/photos')

    assert resp.status_code == 200
    photos = resp.get_json()['photos']
    # The deleted first photo is excluded; only the newer one remains.
    assert [p['id'] for p in photos] == [second_id]


def test_item_get_includes_photos(app, storage_root, item_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        pid = _post_photo(client, item_id, PNG_MIN).get_json()['id']
        resp = client.get(f'/brain/board/items/{item_id}')

    assert resp.status_code == 200
    body = resp.get_json()
    assert 'photos' in body
    assert [p['id'] for p in body['photos']] == [pid]


def test_get_file_streams_image(app, storage_root, item_id, admin_user):
    with _patch_get_current_user(admin_user):
        client = app.test_client()
        pid = _post_photo(client, item_id, PNG_MIN).get_json()['id']
        resp = client.get(f'/brain/board/items/{item_id}/photos/{pid}/file')

    assert resp.status_code == 200
    assert resp.content_type == 'image/png'
    assert resp.data == PNG_MIN


def test_delete_soft_deletes(app, storage_root, item_id, admin_user):
    from app.models import BoardItemPhoto, db

    with _patch_get_current_user(admin_user):
        client = app.test_client()
        pid = _post_photo(client, item_id, PNG_MIN).get_json()['id']
        resp = client.delete(f'/brain/board/items/{item_id}/photos/{pid}')

        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'
        photo = db.session.get(BoardItemPhoto, pid)
        assert photo.is_deleted is True
