"""Tests for app/brain/board/routes.py — admin-only Kanban board CRUD."""
from app.models import BoardItem, BoardActivity, Notification

from tests.conftest import make_user


URL = '/brain/board/items'
DEFAULT_ITEM = {'title': 'A', 'category': 'task'}


def _make_item(client, **overrides):
    payload = {**DEFAULT_ITEM, **overrides}
    return client.post(URL, json=payload).get_json()


def test_non_admin_blocked_from_listing_items(non_admin_client):
    assert non_admin_client.get(URL).status_code == 403


def test_non_admin_blocked_from_creating_items(non_admin_client):
    assert non_admin_client.post(URL, json={'title': 'x', 'category': 'bug'}).status_code == 403


def test_create_board_item(admin_client):
    resp = admin_client.post(URL, json={
        'title': 'Crash on submit',
        'category': 'bug',
        'priority': 'high',
        'body': 'Repro steps...',
    })
    body = resp.get_json()
    assert resp.status_code == 201
    assert body['title'] == 'Crash on submit'
    assert body['category'] == 'bug'
    assert body['priority'] == 'high'
    assert body['status'] == 'open'
    assert body['author_name'] == 'Admin'


def test_create_requires_title(admin_client):
    assert admin_client.post(URL, json={'category': 'bug'}).status_code == 400


def test_create_requires_category(admin_client):
    assert admin_client.post(URL, json={'title': 'x'}).status_code == 400


def test_list_returns_items_with_comment_counts(admin_client):
    item = _make_item(admin_client)
    admin_client.post(f'{URL}/{item["id"]}/activity', json={'body': 'first comment'})

    items = admin_client.get(URL).get_json()['items']
    assert len(items) == 1
    assert items[0]['activity_count'] == 1


def test_list_filters_by_status(admin_client):
    a = _make_item(admin_client)
    b = _make_item(admin_client, title='B')
    admin_client.patch(f'{URL}/{b["id"]}', json={'status': 'closed'})

    open_titles = {i['title'] for i in admin_client.get(f'{URL}?status=open').get_json()['items']}
    closed_titles = {i['title'] for i in admin_client.get(f'{URL}?status=closed').get_json()['items']}
    assert open_titles == {a['title']}
    assert closed_titles == {b['title']}


def test_get_returns_item_with_activity(admin_client):
    item = _make_item(admin_client)
    body = admin_client.get(f'{URL}/{item["id"]}').get_json()
    assert body['title'] == 'A'
    assert 'activity' in body


def test_get_unknown_item_returns_404(admin_client):
    assert admin_client.get(f'{URL}/9999').status_code == 404


def test_delete_removes_item_and_activity(admin_client, app):
    item = _make_item(admin_client)
    admin_client.post(f'{URL}/{item["id"]}/activity', json={'body': 'comment'})

    assert admin_client.delete(f'{URL}/{item["id"]}').status_code == 200
    with app.app_context():
        assert BoardItem.query.count() == 0
        # cascade='all, delete-orphan' on the activity relationship cleans up comments
        assert BoardActivity.query.count() == 0


def test_status_change_creates_status_change_activity(admin_client, app):
    item = _make_item(admin_client)
    admin_client.patch(f'{URL}/{item["id"]}', json={'status': 'in_progress'})

    with app.app_context():
        activities = BoardActivity.query.filter_by(item_id=item['id']).all()
        assert len(activities) == 1
        assert activities[0].type == 'status_change'
        assert activities[0].old_value == 'open'
        assert activities[0].new_value == 'in_progress'


def test_patch_without_status_change_does_not_log_activity(admin_client, app):
    item = _make_item(admin_client)
    admin_client.patch(f'{URL}/{item["id"]}', json={'title': 'A renamed'})

    with app.app_context():
        assert BoardActivity.query.filter_by(item_id=item['id']).count() == 0


def test_reorder_updates_positions(admin_client, app):
    a = _make_item(admin_client)
    b = _make_item(admin_client, title='B')
    c = _make_item(admin_client, title='C')

    resp = admin_client.patch(f'{URL}/reorder', json={
        'status': 'open',
        'ordered_ids': [c['id'], a['id'], b['id']],
    })
    assert resp.get_json() == {'ok': True, 'updated': 3}

    with app.app_context():
        positions = {x.id: x.position for x in BoardItem.query.all()}
        assert positions[c['id']] == 0
        assert positions[a['id']] == 1
        assert positions[b['id']] == 2


def test_reorder_rejects_invalid_status(admin_client):
    resp = admin_client.patch(f'{URL}/reorder', json={
        'status': 'wrong_value', 'ordered_ids': [1],
    })
    assert resp.status_code == 400


def test_reorder_rejects_id_from_other_column(admin_client):
    a = _make_item(admin_client)
    admin_client.patch(f'{URL}/{a["id"]}', json={'status': 'closed'})

    resp = admin_client.patch(f'{URL}/reorder', json={
        'status': 'open', 'ordered_ids': [a['id']],
    })
    assert resp.status_code == 400


def test_add_comment_returns_activity(admin_client):
    item = _make_item(admin_client)
    body = admin_client.post(
        f'{URL}/{item["id"]}/activity', json={'body': 'looks good'},
    ).get_json()
    assert body['type'] == 'comment'
    assert body['body'] == 'looks good'


def test_comment_with_mention_creates_notification(admin_client, app):
    with app.app_context():
        bob_id = make_user('bob@example.com', first_name='Bob').id

    item = _make_item(admin_client)
    admin_client.post(
        f'{URL}/{item["id"]}/activity',
        json={'body': 'Hey @Bob can you take a look'},
    )

    with app.app_context():
        notifs = Notification.query.filter_by(user_id=bob_id).all()
        assert len(notifs) == 1
        assert notifs[0].type == 'mention'
        assert notifs[0].board_item_id == item['id']


def test_comment_without_mention_creates_no_notification(admin_client, app):
    with app.app_context():
        make_user('bob@example.com', first_name='Bob')

    item = _make_item(admin_client)
    admin_client.post(
        f'{URL}/{item["id"]}/activity', json={'body': 'no mention here'},
    )

    with app.app_context():
        assert Notification.query.count() == 0


def test_comment_with_unknown_mention_creates_no_notification(admin_client, app):
    item = _make_item(admin_client)
    admin_client.post(
        f'{URL}/{item["id"]}/activity', json={'body': 'Hey @Nobody'},
    )

    with app.app_context():
        assert Notification.query.count() == 0


def test_empty_comment_returns_400(admin_client):
    item = _make_item(admin_client)
    resp = admin_client.post(f'{URL}/{item["id"]}/activity', json={'body': '   '})
    assert resp.status_code == 400


def test_mentionable_users_returns_active_users(admin_client, app):
    with app.app_context():
        make_user('alice@example.com', first_name='Alice')
        make_user('bob@example.com', first_name='Bob')
        make_user('eve@example.com', first_name='Eve', is_active=False)

    body = admin_client.get('/brain/board/mentionable-users').get_json()
    first_names = {u['first_name'] for u in body['users']}
    assert first_names == {'Alice', 'Bob'}
