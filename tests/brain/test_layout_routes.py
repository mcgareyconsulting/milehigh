"""Integration tests for the K2 grid engine's per-user layout persistence.

HTTP through the test client against the in-memory DB. The mock user fixtures carry
id=1 (admin) / id=2 (non-admin), which is what scopes the rows.
"""
import pytest

from app.models import UserPanelLayout, db


def entry(panel_id, span=1, rows=2, hidden=False):
    return {'id': panel_id, 'span': span, 'rows': rows, 'hidden': hidden}


def test_get_layout_returns_empty_when_nothing_saved(admin_client):
    resp = admin_client.get('/brain/layout/projects:560')
    assert resp.status_code == 200
    assert resp.get_json() == {
        'surface_key': 'projects:560',
        'layout': [],
        'updated_at': None,
    }


def test_put_then_get_round_trips_order_size_and_hidden(admin_client):
    layout = [
        entry('releases', span=3, rows=4),
        entry('submittals', span=2, rows=1),
        entry('budget', hidden=True),
    ]
    put = admin_client.put('/brain/layout/projects:560', json={'layout': layout})
    assert put.status_code == 200
    assert put.get_json()['layout'] == layout

    got = admin_client.get('/brain/layout/projects:560')
    assert got.get_json()['layout'] == layout


def test_put_normalizes_partial_entries(admin_client):
    """Missing span/hidden default rather than being rejected."""
    resp = admin_client.put('/brain/layout/metrics', json={'layout': [{'id': 'a'}]})
    assert resp.status_code == 200
    assert resp.get_json()['layout'] == [entry('a')]


def test_put_accepts_legacy_bare_id_strings(admin_client):
    """Layouts saved before size classes existed were plain id arrays."""
    resp = admin_client.put('/brain/layout/metrics', json={'layout': ['a', 'b']})
    assert resp.status_code == 200
    assert resp.get_json()['layout'] == [entry('a'), entry('b')]


def test_put_upserts_rather_than_duplicating(app, admin_client):
    admin_client.put('/brain/layout/projects:560', json={'layout': [entry('a'), entry('b')]})
    admin_client.put('/brain/layout/projects:560', json={'layout': [entry('b', span=2)]})

    rows = UserPanelLayout.query.filter_by(user_id=1, surface_key='projects:560').all()
    assert len(rows) == 1
    assert rows[0].layout == [entry('b', span=2)]


def test_layouts_are_scoped_per_surface(admin_client):
    admin_client.put('/brain/layout/projects:560', json={'layout': [entry('a')]})
    admin_client.put('/brain/layout/projects:944', json={'layout': [entry('b')]})

    assert admin_client.get('/brain/layout/projects:560').get_json()['layout'] == [entry('a')]
    assert admin_client.get('/brain/layout/projects:944').get_json()['layout'] == [entry('b')]


def test_layouts_are_scoped_per_user(app, admin_client):
    """Another user's layout for the same surface is never read or overwritten.

    Uses a directly-inserted row for user 2 rather than the non_admin_client fixture:
    both client fixtures patch the same module attribute, so requesting them in one
    test makes the last patch win for both.
    """
    db.session.add(UserPanelLayout(
        user_id=2, surface_key='employee_home', layout=[entry('other')],
    ))
    db.session.commit()

    admin_client.put('/brain/layout/employee_home', json={'layout': [entry('a')]})

    assert admin_client.get('/brain/layout/employee_home').get_json()['layout'] == [entry('a')]
    other = UserPanelLayout.query.filter_by(user_id=2, surface_key='employee_home').one()
    assert other.layout == [entry('other')]


def test_put_dedupes_by_id_and_drops_blanks(admin_client):
    resp = admin_client.put('/brain/layout/metrics', json={
        'layout': [entry('a', span=2), entry('a', span=3), {'id': '  '}, entry('b')],
    })
    assert resp.status_code == 200
    # First-seen wins, so the span=2 entry survives.
    assert resp.get_json()['layout'] == [entry('a', span=2), entry('b')]


@pytest.mark.parametrize('body', [
    {},                                            # missing 'layout'
    {'layout': 'not-a-list'},
    {'layout': [123]},                             # not an object or string
    {'layout': [{'id': 5}]},                       # non-string id
    {'layout': [{'id': 'x' * 121}]},               # id over MAX_ID_LEN
    {'layout': [{'id': 'a', 'span': 4}]},          # span outside 1..3
    {'layout': [{'id': 'a', 'span': 'wide'}]},     # non-numeric span
    {'layout': [{'id': 'a', 'rows': 9}]},          # rows outside 1..4
    {'layout': [{'id': 'a', 'rows': 'tall'}]},     # non-numeric rows
    {'layout': [{'id': 'a', 'span': True}]},       # bool is an int subclass — must not pass
    {'layout': [{'id': f'p{i}'} for i in range(101)]},  # over MAX_PANELS
])
def test_put_rejects_malformed_bodies(admin_client, body):
    resp = admin_client.put('/brain/layout/metrics', json=body)
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_put_rejects_overlong_surface_key(admin_client):
    resp = admin_client.put('/brain/layout/' + 'k' * 121, json={'layout': [entry('a')]})
    assert resp.status_code == 400


def test_layout_requires_login(client):
    """Unauthenticated access is refused (login_required -> 401)."""
    assert client.get('/brain/layout/projects:560').status_code == 401
    assert client.put('/brain/layout/projects:560', json={'layout': []}).status_code == 401
