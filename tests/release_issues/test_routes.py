"""HTTP tests for the Release Issue Register: admin gate, validation, detail payload,
attachment isolation and file-type checks, soft delete, and the storage-root config."""
import importlib
import io

import pytest

from app.models import ReleaseIssueAttachment, db
from tests.release_issues.conftest import valid_issue_payload

PDF_BYTES = b'%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<<>>\n%%EOF\n'
PNG_BYTES = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


def _create(client, release_id, **overrides):
    return client.post(f'/brain/releases/{release_id}/issues', json=valid_issue_payload(**overrides))


def _upload(client, issue_id, data, filename, **form):
    return client.post(
        f'/brain/release-issues/{issue_id}/attachments',
        data={'file': (io.BytesIO(data), filename), **form},
        content_type='multipart/form-data',
    )


# --- auth --------------------------------------------------------------------


ROUTES = [
    ('get', '/brain/release-issues/options'),
    ('get', '/brain/releases/{rid}/issues'),
    ('post', '/brain/releases/{rid}/issues'),
    ('get', '/brain/release-issues/1'),
    ('patch', '/brain/release-issues/1'),
    ('post', '/brain/release-issues/1/comments'),
    ('post', '/brain/release-issues/1/attachments'),
    ('get', '/brain/release-issues/1/attachments/1/file'),
    ('delete', '/brain/release-issues/1/attachments/1'),
]

# The client fixtures each patch get_current_user, so one per test — two would stack.


@pytest.mark.parametrize('method,path', ROUTES)
def test_every_route_forbids_non_admins(plain_client, release, method, path):
    assert getattr(plain_client, method)(path.format(rid=release.id)).status_code == 403


@pytest.mark.parametrize('method,path', ROUTES)
def test_every_route_requires_login(anon_client, release, method, path):
    assert getattr(anon_client, method)(path.format(rid=release.id)).status_code == 401


# --- options / list / create --------------------------------------------------


def test_options_serve_the_v1_department_list(admin_client):
    body = admin_client.get('/brain/release-issues/options').get_json()
    assert [d['label'] for d in body['departments']] == ['Drafting', 'Paint', 'Fab', 'Ship/Install']
    assert len(body['categories']) == 12
    assert body['closed_statuses'] == ['closed', 'resolved']


def test_create_returns_detail_and_list_shows_summary(admin_client, release):
    resp = _create(admin_client, release.id)
    assert resp.status_code == 201
    detail = resp.get_json()
    assert detail['issue']['display_id'] == '290-153-I1'
    assert detail['comments'] == [] and detail['attachments'] == [] and detail['changes'] == []

    listing = admin_client.get(f'/brain/releases/{release.id}/issues').get_json()
    assert [i['id'] for i in listing['issues']] == [detail['issue']['id']]
    assert listing['summary']['open_count'] == 1
    assert listing['summary']['open_estimated_cost'] == 1200.0


def test_create_missing_field_is_400(admin_client, release):
    resp = _create(admin_client, release.id, department='')
    assert resp.status_code == 400
    assert 'Department' in resp.get_json()['error']


def test_unknown_release_and_issue_are_404(admin_client):
    assert admin_client.get('/brain/releases/9999/issues').status_code == 404
    assert admin_client.post('/brain/releases/9999/issues', json=valid_issue_payload()).status_code == 404
    assert admin_client.get('/brain/release-issues/9999').status_code == 404
    assert admin_client.patch('/brain/release-issues/9999', json={'status': 'closed'}).status_code == 404


# --- update / comments --------------------------------------------------------


def test_patch_then_comment_builds_full_timeline(admin_client, release):
    issue_id = _create(admin_client, release.id).get_json()['issue']['id']

    patched = admin_client.patch(f'/brain/release-issues/{issue_id}', json={'status': 'in_progress'})
    assert patched.status_code == 200
    assert patched.get_json()['issue']['status'] == 'in_progress'

    assert admin_client.post(f'/brain/release-issues/{issue_id}/comments', json={'body': 'On it'}).status_code == 201
    admin_client.patch(f'/brain/release-issues/{issue_id}', json={'status': 'resolved'})

    detail = admin_client.get(f'/brain/release-issues/{issue_id}').get_json()
    assert [(c['old_value'], c['new_value']) for c in detail['changes']] == [
        ('open', 'in_progress'), ('in_progress', 'resolved'),
    ]
    assert [c['body'] for c in detail['comments']] == ['On it']


def test_patch_invalid_status_is_400(admin_client, release):
    issue_id = _create(admin_client, release.id).get_json()['issue']['id']
    resp = admin_client.patch(f'/brain/release-issues/{issue_id}', json={'status': 'done-ish'})
    assert resp.status_code == 400


def test_blank_comment_is_400(admin_client, release):
    issue_id = _create(admin_client, release.id).get_json()['issue']['id']
    assert admin_client.post(f'/brain/release-issues/{issue_id}/comments', json={'body': ''}).status_code == 400


# --- attachments ----------------------------------------------------------------


def test_pdf_and_photo_upload_and_stream(admin_client, release, storage_root):
    issue_id = _create(admin_client, release.id).get_json()['issue']['id']

    pdf = _upload(admin_client, issue_id, PDF_BYTES, 'rework.pdf')
    png = _upload(admin_client, issue_id, PNG_BYTES, 'damage.png')
    assert pdf.status_code == 201 and png.status_code == 201
    assert pdf.get_json()['mime_type'] == 'application/pdf'
    assert png.get_json()['mime_type'] == 'image/png'
    assert (storage_root / str(issue_id) / f"{pdf.get_json()['id']}.pdf").exists()

    streamed = admin_client.get(f"/brain/release-issues/{issue_id}/attachments/{pdf.get_json()['id']}/file")
    assert streamed.status_code == 200
    assert streamed.data == PDF_BYTES


def test_non_photo_non_pdf_rejected(admin_client, release, storage_root):
    issue_id = _create(admin_client, release.id).get_json()['issue']['id']
    resp = _upload(admin_client, issue_id, b'just some text here', 'notes.txt')
    assert resp.status_code == 400
    assert ReleaseIssueAttachment.query.count() == 0


def test_attachment_on_issue_a_not_reachable_through_issue_b(admin_client, release, storage_root):
    a = _create(admin_client, release.id).get_json()['issue']['id']
    b = _create(admin_client, release.id, title='Second').get_json()['issue']['id']
    att_id = _upload(admin_client, a, PDF_BYTES, 'a.pdf').get_json()['id']

    assert [x['id'] for x in admin_client.get(f'/brain/release-issues/{a}').get_json()['attachments']] == [att_id]
    assert admin_client.get(f'/brain/release-issues/{b}').get_json()['attachments'] == []
    assert admin_client.get(f'/brain/release-issues/{b}/attachments/{att_id}/file').status_code == 404
    assert admin_client.delete(f'/brain/release-issues/{b}/attachments/{att_id}').status_code == 404


def test_comment_attachment_links_to_comment(admin_client, release, storage_root):
    issue_id = _create(admin_client, release.id).get_json()['issue']['id']
    comment_id = admin_client.post(
        f'/brain/release-issues/{issue_id}/comments', json={'body': 'photo attached'},
    ).get_json()['id']

    resp = _upload(admin_client, issue_id, PNG_BYTES, 'c.png', comment_id=str(comment_id))
    assert resp.status_code == 201
    assert resp.get_json()['comment_id'] == comment_id


def test_delete_is_soft_and_keeps_file(admin_client, release, storage_root):
    issue_id = _create(admin_client, release.id).get_json()['issue']['id']
    att = _upload(admin_client, issue_id, PDF_BYTES, 'keep.pdf').get_json()

    resp = admin_client.delete(f"/brain/release-issues/{issue_id}/attachments/{att['id']}")
    assert resp.status_code == 200

    row = db.session.get(ReleaseIssueAttachment, att['id'])
    assert row.is_deleted is True
    assert (storage_root / str(issue_id) / f"{att['id']}.pdf").exists()
    assert admin_client.get(f'/brain/release-issues/{issue_id}').get_json()['attachments'] == []
    assert admin_client.get(f"/brain/release-issues/{issue_id}/attachments/{att['id']}/file").status_code == 404
    again = admin_client.delete(f"/brain/release-issues/{issue_id}/attachments/{att['id']}")
    assert again.get_json()['status'] == 'already_deleted'


# --- storage root config ----------------------------------------------------------


def test_issue_storage_root_derives_onto_the_mounted_disk(monkeypatch):
    import app.config
    try:
        for key in ('PDF_STORAGE_ROOT', 'RELEASE_ISSUE_STORAGE_ROOT'):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv('PDF_STORAGE_ROOT', '/var/data/pdfs')
        importlib.reload(app.config)
        assert app.config.Config.RELEASE_ISSUE_STORAGE_ROOT == '/var/data/release_issues'

        monkeypatch.setenv('RELEASE_ISSUE_STORAGE_ROOT', '/mnt/other/issues')
        importlib.reload(app.config)
        assert app.config.Config.RELEASE_ISSUE_STORAGE_ROOT == '/mnt/other/issues'
    finally:
        monkeypatch.undo()
        importlib.reload(app.config)
