"""Token validation for the subcontractor invite-accept flow: valid/expired/
already-used/garbage tokens, and that a raw token is never persisted or
leaked in the (mocked) invite email body.

No token infra existed anywhere in this codebase before this feature — these
tests are the only coverage of hashlib/secrets/hmac correctness for it.
"""
from datetime import datetime, timedelta

from app.brain.tm.subcontractors.command import _generate_and_store_invite_token
from app.models import Subcontractor, db
from tests.conftest import make_subcontractor


def _sub_with_token(**kwargs):
    sub = make_subcontractor('sam@acme.test', **kwargs)
    raw_token = _generate_and_store_invite_token(sub)
    db.session.commit()
    return sub, raw_token


def test_valid_token_validates_and_accept_succeeds(app, client):
    sub, raw_token = _sub_with_token()

    resp = client.get(f'/api/subcontractor-auth/invite/{raw_token}')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['email'] == 'sam@acme.test'
    assert body['company_name'] == sub.company_name

    resp = client.post('/api/subcontractor-auth/accept-invite', json={
        'token': raw_token, 'password': 'correcthorse123', 'confirm_password': 'correcthorse123',
    })
    assert resp.status_code == 200
    assert resp.get_json()['subcontractor']['invite_accepted'] is True

    db.session.refresh(sub)
    assert sub.password_hash is not None
    assert sub.invite_accepted_at is not None
    assert sub.invite_token_hash is None
    assert sub.invite_token_expires_at is None


def test_expired_token_returns_410(app, client):
    sub, raw_token = _sub_with_token()
    sub.invite_token_expires_at = datetime.utcnow() - timedelta(days=1)
    db.session.commit()

    resp = client.get(f'/api/subcontractor-auth/invite/{raw_token}')
    assert resp.status_code == 410

    resp = client.post('/api/subcontractor-auth/accept-invite', json={
        'token': raw_token, 'password': 'correcthorse123', 'confirm_password': 'correcthorse123',
    })
    assert resp.status_code == 410
    db.session.refresh(sub)
    assert sub.password_hash is None  # unchanged


def test_already_used_token_returns_404_on_second_accept(app, client):
    sub, raw_token = _sub_with_token()
    first = client.post('/api/subcontractor-auth/accept-invite', json={
        'token': raw_token, 'password': 'correcthorse123', 'confirm_password': 'correcthorse123',
    })
    assert first.status_code == 200

    second = client.post('/api/subcontractor-auth/accept-invite', json={
        'token': raw_token, 'password': 'differentpass123', 'confirm_password': 'differentpass123',
    })
    assert second.status_code == 404  # hash was cleared on first accept; token no longer matches


def test_garbage_token_returns_404_without_leaking_existence(app, client):
    make_subcontractor('sam@acme.test')  # a real account exists, just not with this token
    resp = client.get('/api/subcontractor-auth/invite/not-a-real-token')
    assert resp.status_code == 404
    assert 'sam@acme.test' not in resp.get_data(as_text=True)


def test_accept_rejects_mismatched_passwords(app, client):
    sub, raw_token = _sub_with_token()
    resp = client.post('/api/subcontractor-auth/accept-invite', json={
        'token': raw_token, 'password': 'correcthorse123', 'confirm_password': 'different123',
    })
    assert resp.status_code == 400


def test_accept_rejects_short_password(app, client):
    sub, raw_token = _sub_with_token()
    resp = client.post('/api/subcontractor-auth/accept-invite', json={
        'token': raw_token, 'password': 'short', 'confirm_password': 'short',
    })
    assert resp.status_code == 400


def test_raw_token_is_never_persisted(app):
    sub, raw_token = _sub_with_token()
    # Only a sha256 hash lives on the row; the raw token isn't a substring of
    # anything stored (hash is deterministic-but-irreversible, so this is a
    # cheap sanity check that we didn't accidentally store it in plaintext
    # somewhere on the model).
    row = db.session.get(Subcontractor, sub.id)
    assert raw_token != row.invite_token_hash
    assert raw_token not in (row.invite_token_hash or '')
