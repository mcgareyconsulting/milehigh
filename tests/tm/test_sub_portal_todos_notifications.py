"""The subcontractor To-Dos tab: their own checklist items and the rows addressed to them.

Ownership IS the lookup: a to-do owned by someone else 404s rather than 403s, and the
unread count splits into to-do pings vs mentions so the tab badge and the two segment
badges are honest.
"""
from datetime import date

import pytest

from app.models import ChecklistItem, Meeting, Notification, db
from tests.conftest import make_subcontractor, make_user
from tests.tm.conftest import subcontractor_authed_client


@pytest.fixture
def sub(app):
    return make_subcontractor('crew@sub.test', accepted=True, installer_team='Saul 2')


@pytest.fixture
def other(app):
    return make_subcontractor('other@sub.test', accepted=True, installer_team='Octavio')


@pytest.fixture
def meeting(app):
    m = Meeting(title='Standup', meeting_type='standup', transcript='x')
    db.session.add(m)
    db.session.commit()
    return m


def _todo(meeting, owner_sub, title, status='accepted', due=None):
    it = ChecklistItem(meeting_id=meeting.id, title=title, owner_subcontractor_id=owner_sub.id,
                       status=status, due_date=due)
    db.session.add(it)
    db.session.commit()
    return it


@pytest.fixture
def client(app, sub):
    stack, c = subcontractor_authed_client(app, sub)
    with stack:
        yield c


def test_todos_are_the_subs_own_only(client, sub, other, meeting):
    mine = _todo(meeting, sub, 'Bring the lift', due=date.today())
    _todo(meeting, other, 'Not mine')
    _todo(meeting, sub, 'Done already', status='done')
    open_rows = client.get('/brain/subcontractor/todos').get_json()['todos']
    assert [t['title'] for t in open_rows] == ['Bring the lift']
    all_rows = client.get('/brain/subcontractor/todos?status=all').get_json()['todos']
    assert {t['title'] for t in all_rows} == {'Bring the lift', 'Done already'}
    # allowlist: no meeting / reviewer / proposal internals
    assert set(all_rows[0]) == {'id', 'title', 'detail', 'item_type', 'status', 'due_date', 'release_id',
                                'release_code', 'release_job_name', 'release_description', 'created_at'}
    assert mine.id in {t['id'] for t in all_rows}


def test_marking_done_and_reopening_are_owner_only(client, sub, other, meeting):
    mine = _todo(meeting, sub, 'Bring the lift')
    theirs = _todo(meeting, other, 'Not mine')
    assert client.patch(f'/brain/subcontractor/todos/{mine.id}', json={'status': 'done'}).get_json()['status'] == 'done'
    assert client.patch(f'/brain/subcontractor/todos/{mine.id}', json={'status': 'accepted'}).get_json()['status'] == 'accepted'
    assert client.patch(f'/brain/subcontractor/todos/{theirs.id}', json={'status': 'done'}).status_code == 404
    assert client.patch(f'/brain/subcontractor/todos/{mine.id}', json={'status': 'rejected'}).status_code == 400


def test_notifications_are_addressed_rows_only_with_an_allowlist(client, sub, other):
    staff = make_user('bill', first_name='Bill')
    db.session.add_all([
        Notification(subcontractor_id=sub.id, type='mention', message='Bill mentioned you on drawing v2'),
        Notification(subcontractor_id=other.id, type='mention', message='not yours'),
        Notification(user_id=staff.id, type='mention', message='staff row'),
    ])
    db.session.commit()
    body = client.get('/brain/subcontractor/notifications').get_json()
    assert [n['message'] for n in body['notifications']] == ['Bill mentioned you on drawing v2']
    assert body['unread_count'] == 1
    row = body['notifications'][0]
    assert 'user_id' not in row and 'board_item_id' not in row and 'submittal_title' not in row


def test_unread_count_splits_todo_pings_from_mentions_and_read_all_narrows(client, sub):
    db.session.add_all([
        Notification(subcontractor_id=sub.id, type='mention', message='m1'),
        Notification(subcontractor_id=sub.id, type='checklist_assigned', message='New to-do: x'),
        Notification(subcontractor_id=sub.id, type='checklist_due', message='To-do due: x'),
    ])
    db.session.commit()
    assert client.get('/brain/subcontractor/notifications/unread-count').get_json() == {
        'unread_count': 3, 'unread_todos': 2, 'unread_mentions': 1}
    r = client.post('/brain/subcontractor/notifications/read-all?types=checklist_assigned,checklist_due')
    assert r.get_json()['updated'] == 2
    assert client.get('/brain/subcontractor/notifications/unread-count').get_json() == {
        'unread_count': 1, 'unread_todos': 0, 'unread_mentions': 1}
    mention = Notification.query.filter_by(type='mention').one()
    assert client.patch(f'/brain/subcontractor/notifications/{mention.id}/read').get_json()['is_read'] is True
    assert client.get('/brain/subcontractor/notifications/unread-count').get_json()['unread_count'] == 0


def test_cannot_read_another_subs_notification(client, other):
    n = Notification(subcontractor_id=other.id, type='mention', message='not yours')
    db.session.add(n)
    db.session.commit()
    assert client.patch(f'/brain/subcontractor/notifications/{n.id}/read').status_code == 404
    assert n.is_read is False
