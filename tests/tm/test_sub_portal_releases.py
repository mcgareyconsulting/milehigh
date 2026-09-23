"""The crew-scoped subcontractor release read-model (T3 slice 1).

The load-bearing test here is test_payload_keys_equal_the_allowlist. It asserts
EQUALITY, not containment, so adding a column to Releases and wiring it into the
internal serializer can never silently place it in a subcontractor payload — the
build fails and someone has to decide. That test is the wall; the rest are the
scoping rules around it.
"""
from app.brain.sub_portal.service import SUB_FIELDS, serialize_release_for_sub
from app.models import db

from tests.conftest import make_release, make_subcontractor
from tests.tm.conftest import subcontractor_authed_client


def _sub(crew, email='crew@sub.test'):
    s = make_subcontractor(email, accepted=True)
    s.installer_team = crew
    db.session.commit()
    return s


def test_payload_keys_equal_the_allowlist(app):
    r = make_release(101, 'A', installer='Saul 1', install_hrs=8, num_guys=2)
    db.session.commit()
    assert set(serialize_release_for_sub(r)) == set(SUB_FIELDS)


def test_forbidden_fields_are_absent(app):
    """Named separately from the equality test so a failure says WHICH wall broke."""
    r = make_release(102, 'A', installer='Saul 1', fab_hrs=99.0, fab_order=3,
                     invoiced='X', notes='internal note', trello_card_id='abc123')
    db.session.commit()
    payload = serialize_release_for_sub(r)
    for forbidden in ('Fab Hrs', 'Fab Order', 'Invoiced', 'Notes', 'trello_card_id',
                      'is_active', 'is_archived', 'source_of_update'):
        assert forbidden not in payload, forbidden
    assert 99.0 not in payload.values()   # fab hours not smuggled under another key


def test_only_the_accounts_own_crew_is_returned(app):
    make_release(201, 'A', installer='Saul 1')
    make_release(202, 'A', installer='Octavio')
    make_release(203, 'A', installer=None)
    sub = _sub('Saul 1')

    stack, client = subcontractor_authed_client(app, sub)
    with stack:
        body = client.get('/brain/subcontractor/releases').get_json()
    assert [r['Job #'] for r in body['releases']] == [201]
    assert body['installer_team'] == 'Saul 1'


def test_unscoped_account_sees_nothing(app):
    """Fail closed: no crew must mean no releases, never an unfiltered query."""
    make_release(301, 'A', installer='Saul 1')
    sub = _sub(None)

    stack, client = subcontractor_authed_client(app, sub)
    with stack:
        resp = client.get('/brain/subcontractor/releases')
        teams = client.get('/brain/subcontractor/installer-teams').get_json()
    assert resp.status_code == 200
    assert resp.get_json()['releases'] == []
    assert teams['installer_teams'] == []


def test_archived_and_soft_deleted_are_excluded(app):
    make_release(401, 'A', installer='Saul 1')
    make_release(402, 'A', installer='Saul 1', is_archived=True)
    make_release(403, 'A', installer='Saul 1', is_active=False)
    sub = _sub('Saul 1')

    stack, client = subcontractor_authed_client(app, sub)
    with stack:
        body = client.get('/brain/subcontractor/releases').get_json()
    assert [r['Job #'] for r in body['releases']] == [401]


def test_installer_teams_names_only_their_own_crew(app):
    """The internal /brain/installer-teams returns the whole roster; this one must
    not, or a sub learns every other crew's name."""
    sub = _sub('Saul 1')
    stack, client = subcontractor_authed_client(app, sub)
    with stack:
        body = client.get('/brain/subcontractor/installer-teams').get_json()
    assert body['installer_teams'] == ['Saul 1']


def test_routes_require_a_subcontractor_session(app, client):
    assert client.get('/brain/subcontractor/releases').status_code == 401
    assert client.get('/brain/subcontractor/installer-teams').status_code == 401
