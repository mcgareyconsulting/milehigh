"""Subcontractor accounts as to-do owners and mention targets (T3).

Two nullable columns did the work — ChecklistItem.owner_subcontractor_id and
Notification.subcontractor_id — so the tests pin the invariants around them:
exactly one owner column set, pings routed to whichever owner is set, mentions
resolved by the first word of contact_name on the release-linked producers only,
and the staff views that must keep working (admin scoping by 'sub:<id>', the
events feed naming a sub actor).
"""
from contextlib import ExitStack
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.brain.meetings import service as meetings
from app.brain.mentions import mention_targets, resolve_mentioned_subcontractors
from app.models import ChecklistItem, Meeting, Notification, db
from tests.conftest import make_release, make_subcontractor, make_user

# These route modules bind get_current_user themselves; the brain conftest does not
# cover them, so this module patches the extra sites for its own admin client.
_EXTRA_TARGETS = (
    'app.auth.utils.get_current_user',
    'app.brain.todos_routes.get_current_user',
    'app.brain.notification_routes.get_current_user',
    'app.brain.meetings.routes.get_current_user',
    'app.brain.job_log.routes.get_current_user',
    'app.brain.job_log.pdf_markup_routes.get_current_user',
)


@pytest.fixture
def admin(app):
    return make_user('bill', is_admin=True, first_name='Bill', last_name='ONeill')


@pytest.fixture
def admin_http(app, admin):
    with ExitStack() as stack:
        for t in _EXTRA_TARGETS:
            stack.enter_context(patch(t, return_value=admin))
        yield app.test_client()


@pytest.fixture
def sam(app):
    return make_subcontractor('sam@acme.test', accepted=True, contact_name='Sam Sub',
                              company_name='Acme Install', installer_team='Saul 2')


@pytest.fixture
def meeting(app):
    m = Meeting(title='Standup', meeting_type='standup', transcript='x')
    db.session.add(m)
    db.session.commit()
    return m


def _item(meeting, **kw):
    it = ChecklistItem(meeting_id=meeting.id, title=kw.pop('title', 'Bring the lift'), **kw)
    db.session.add(it)
    db.session.commit()
    return it


# ---- owner columns -----------------------------------------------------------------

def test_assignable_users_lists_subs_after_staff_with_a_prefixed_id(admin_http, admin, sam):
    rows = admin_http.get('/brain/meetings/assignable-users').get_json()['users']
    assert rows[0]['id'] == admin.id and rows[0]['kind'] == 'user'
    assert rows[-1] == {'id': f'sub:{sam.id}', 'first_name': 'Sam Sub', 'last_name': '(Acme Install)', 'kind': 'subcontractor'}


def test_assigning_a_sub_clears_the_user_owner_and_pings_the_sub(app, admin, sam, meeting):
    item = _item(meeting, status='proposed', owner_user_id=admin.id)
    meetings.review_item(item.id, action='accept', fields={'owner_subcontractor_id': sam.id}, reviewer=admin)
    db.session.refresh(item)
    assert item.owner_subcontractor_id == sam.id and item.owner_user_id is None
    assert item.status == 'accepted'
    ping = Notification.query.filter_by(type='checklist_assigned').one()
    assert ping.subcontractor_id == sam.id and ping.user_id is None
    assert item.to_dict()['owner_name'] == 'Sam Sub (Acme Install)'


def test_assigning_a_user_clears_the_sub_owner(app, admin, sam, meeting):
    item = _item(meeting, status='accepted', owner_subcontractor_id=sam.id)
    meetings.review_item(item.id, fields={'owner_user_id': admin.id}, reviewer=admin)
    db.session.refresh(item)
    assert item.owner_user_id == admin.id and item.owner_subcontractor_id is None


def test_due_pings_reach_a_sub_owner(app, sam, meeting):
    _item(meeting, status='accepted', owner_subcontractor_id=sam.id, due_date=date.today() - timedelta(days=1))
    assert meetings.notify_due_items(today=date.today()) == 1
    ping = Notification.query.filter_by(type='checklist_due').one()
    assert ping.subcontractor_id == sam.id and 'overdue' in ping.message


def test_admin_todo_list_includes_sub_owned_and_scopes_by_prefixed_owner(admin_http, admin, sam, meeting):
    _item(meeting, title='Mine', status='accepted', owner_user_id=admin.id)
    _item(meeting, title='Sams', status='accepted', owner_subcontractor_id=sam.id)
    everyone = admin_http.get('/brain/todos').get_json()['todos']
    assert {t['title'] for t in everyone} == {'Mine', 'Sams'}
    only_sam = admin_http.get(f'/brain/todos?owner=sub:{sam.id}').get_json()['todos']
    assert [t['title'] for t in only_sam] == ['Sams']


# ---- mentions ----------------------------------------------------------------------

def test_mentions_resolve_by_first_word_of_contact_name_active_only(app, sam):
    make_subcontractor('gone@acme.test', accepted=True, contact_name='Sam Gone', is_active=False)
    assert [s.id for s in resolve_mentioned_subcontractors({'sam'})] == [sam.id]
    assert resolve_mentioned_subcontractors({'nobody'}) == []


def test_a_staffer_and_a_sub_sharing_a_first_name_are_both_targets(app, sam):
    staff_sam = make_user('samstaff', first_name='Sam', last_name='Staff')
    users, subs = mention_targets({'sam'})
    assert [u.id for u in users] == [staff_sam.id]
    assert [s.id for s in subs] == [sam.id]


def test_drawing_comment_mention_notifies_the_sub(admin_http, admin, sam, app, tmp_path):
    from app.models import ReleaseDrawingVersion
    app.config['PDF_STORAGE_ROOT'] = str(tmp_path)
    release = make_release(560, '923', installer='Saul 2', job_name='Alta')
    version = ReleaseDrawingVersion(release_id=release.id, version_number=1, storage_key='x.pdf',
                                    mime_type='application/pdf', file_size_bytes=1, uploaded_by_user_id=admin.id)
    db.session.add(version)
    db.session.commit()
    r = admin_http.post(f'/brain/releases/{release.id}/drawing/versions/{version.id}/comments',
                        json={'body': '@Sam please check the base plate'})
    assert r.status_code == 201, r.get_json()
    n = Notification.query.filter_by(type='mention').one()
    assert n.subcontractor_id == sam.id and n.user_id is None
    assert n.drawing_version_comment_id is not None


def test_mentionable_users_includes_subs(admin_http, sam):
    rows = admin_http.get('/brain/mentionable-users').get_json()['users']
    assert {'id': f'sub:{sam.id}', 'first_name': 'Sam', 'last_name': 'Acme Install · sub', 'kind': 'subcontractor'} in rows


def test_admin_can_view_a_subs_inbox_but_the_bell_stays_self_scoped(admin_http, admin, sam):
    db.session.add_all([
        Notification(subcontractor_id=sam.id, type='mention', message='for sam'),
        Notification(user_id=admin.id, type='mention', message='for bill'),
    ])
    db.session.commit()
    own = admin_http.get('/brain/notifications').get_json()
    assert [n['message'] for n in own['notifications']] == ['for bill'] and own['scoped_to_self'] is True
    sams = admin_http.get(f'/brain/notifications?owner=sub:{sam.id}').get_json()
    assert [n['message'] for n in sams['notifications']] == ['for sam']
    assert sams['notifications'][0]['owner_name'] == 'Sam Sub' and sams['scoped_to_self'] is False


def test_staff_events_feed_names_a_sub_actor(admin_http, sam):
    from app.brain.job_log.features.notes.command import UpdateNotesCommand
    make_release(560, '923', installer='Saul 2', job_name='Alta')
    db.session.commit()
    UpdateNotesCommand(job_id=560, release='923', notes='from the field', external_user_id=f'sub:{sam.id}').execute()
    rows = admin_http.get('/brain/events?job=560&release=923&limit=5').get_json()['events']
    assert [(e['action'], e['user_name']) for e in rows] == [('update_notes', 'Sam Sub (Acme Install)')]
