"""Session isolation between internal User and external Subcontractor
identities — the load-bearing guarantee of this whole feature: an external
account can never accidentally resolve as, or gain, internal access.

Uses real Flask session state via client.session_transaction() (not mocked
get_current_user/get_current_subcontractor) so these tests exercise the
actual session-key-reading logic, not a stand-in for it.
"""
from datetime import datetime

from app.auth.utils import hash_password
from app.brain.tm.subcontractors.command import _generate_and_store_invite_token
from app.models import TMTicket, db
from tests.conftest import make_user, make_subcontractor


def _create_ticket():
    ticket = TMTicket(status="draft", created_by="test_admin")
    db.session.add(ticket)
    db.session.commit()
    return ticket


def test_user_session_cannot_read_subcontractor_me(app, client):
    user = make_user("staffer", is_admin=False)
    with client.session_transaction() as sess:
        sess['user_id'] = user.id

    resp = client.get('/api/subcontractor-auth/me')
    assert resp.status_code == 401


def test_subcontractor_session_cannot_read_user_me(app, client):
    sub = make_subcontractor('sam@acme.test', accepted=True)
    with client.session_transaction() as sess:
        sess['subcontractor_id'] = sub.id

    resp = client.get('/api/auth/me')
    assert resp.status_code == 401


def test_subcontractor_session_gets_401_not_403_on_admin_route(app, client):
    """401, not 403: proves get_current_user() never falls back to reading
    subcontractor_id — a future refactor that blurs this gets caught here,
    not discovered as a live privilege-escalation bug."""
    sub = make_subcontractor('sam@acme.test', accepted=True)
    with client.session_transaction() as sess:
        sess['subcontractor_id'] = sub.id

    resp = client.post('/brain/subcontractors', json={
        'company_name': 'x', 'contact_name': 'y', 'email': 'z@z.test',
    })
    assert resp.status_code == 401


def test_user_session_gets_401_on_subcontractor_ticket_routes(app, client):
    user = make_user("staffer", is_admin=True)
    ticket = _create_ticket()
    with client.session_transaction() as sess:
        sess['user_id'] = user.id

    resp = client.get(f'/brain/subcontractor/tm-tickets/{ticket.id}')
    assert resp.status_code == 401


def test_deactivated_subcontractor_session_gets_401(app, client):
    sub = make_subcontractor('sam@acme.test', accepted=True, is_active=False)
    with client.session_transaction() as sess:
        sess['subcontractor_id'] = sub.id

    resp = client.get('/api/subcontractor-auth/me')
    assert resp.status_code == 401


def test_login_sets_subcontractor_id_not_user_id(app, client):
    sub = make_subcontractor('sam@acme.test', accepted=False)
    sub.password_hash = hash_password('correcthorse123')
    sub.invite_accepted_at = datetime.utcnow()
    db.session.commit()

    resp = client.post('/api/subcontractor-auth/login', json={
        'email': 'sam@acme.test', 'password': 'correcthorse123',
    })
    assert resp.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get('subcontractor_id') == sub.id
        assert 'user_id' not in sess


def test_subcontractor_login_clears_a_stale_staff_session(app, client):
    """A browser that was previously logged in as staff (e.g. an admin testing
    both identities in one tab) must not end up with BOTH session keys set —
    that would let the subcontractor tab's login silently also carry admin
    access into the main app."""
    user = make_user('staffer', is_admin=True)
    sub = make_subcontractor('sam@acme.test', accepted=False)
    sub.password_hash = hash_password('correcthorse123')
    sub.invite_accepted_at = datetime.utcnow()
    db.session.commit()

    with client.session_transaction() as sess:
        sess['user_id'] = user.id

    resp = client.post('/api/subcontractor-auth/login', json={
        'email': 'sam@acme.test', 'password': 'correcthorse123',
    })
    assert resp.status_code == 200

    with client.session_transaction() as sess:
        assert 'user_id' not in sess
        assert sess.get('subcontractor_id') == sub.id


def test_accept_invite_clears_a_stale_staff_session(app, client):
    user = make_user('staffer', is_admin=True)
    sub = make_subcontractor('sam@acme.test')
    raw_token = _generate_and_store_invite_token(sub)
    db.session.commit()

    with client.session_transaction() as sess:
        sess['user_id'] = user.id

    resp = client.post('/api/subcontractor-auth/accept-invite', json={
        'token': raw_token, 'password': 'correcthorse123', 'confirm_password': 'correcthorse123',
    })
    assert resp.status_code == 200

    with client.session_transaction() as sess:
        assert 'user_id' not in sess
        assert sess.get('subcontractor_id') == sub.id
