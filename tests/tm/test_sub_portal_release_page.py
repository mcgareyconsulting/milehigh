"""The subcontractor release page (T3): activity, notes, stage, photos, files, day schedule.

Every route here is @subcontractor_login_required and crew-scoped. The tests pin the
walls, not the layout:
  * off-crew ids 404 everywhere — the response never confirms an id exists;
  * Activity serves SUB_ACTIVITY_ACTIONS only (fab order never leaves the server);
  * a sub's writes are attributed "sub:<id>" on the event and show the sub's name back;
  * stage changes are limited to SUB_STAGES;
  * uploads land with the account as uploader; a splice sees the original's drawings.
"""
import io
from datetime import date

import pytest

from app.models import Notification, ReleaseEvents, ReleasePhoto, ReleaseDrawingVersion, db
from app.services.job_event_service import JobEventService
from tests.conftest import make_release, make_subcontractor
from tests.tm.conftest import subcontractor_authed_client

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
       b'\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4'
       b'\x00\x00\x00\x00IEND\xaeB`\x82')
PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'


@pytest.fixture
def storage(app, tmp_path):
    app.config['PHOTO_STORAGE_ROOT'] = str(tmp_path / 'photos')
    app.config['PDF_STORAGE_ROOT'] = str(tmp_path / 'pdfs')
    return tmp_path


@pytest.fixture
def sub(app):
    return make_subcontractor('crew@sub.test', accepted=True, contact_name='Sam Sub', installer_team='Saul 2')


@pytest.fixture
def mine(app):
    r = make_release(560, '923', stage='Ship Planning', installer='Saul 2', job_name='Alta Metro',
                     description='Bldg C steel', start_install=date.today(), install_hrs=40,
                     is_active=True, is_archived=False)
    db.session.commit()
    return r


@pytest.fixture
def theirs(app):
    r = make_release(560, '944', stage='Ship Planning', installer='Octavio', job_name='Alta Metro',
                     is_active=True, is_archived=False)
    db.session.commit()
    return r


@pytest.fixture
def client(app, sub):
    stack, c = subcontractor_authed_client(app, sub)
    with stack:
        yield c


# ---- release detail ---------------------------------------------------------------

def test_detail_carries_field_stage_options(client, mine):
    r = client.get(f'/brain/subcontractor/releases/{mine.id}')
    assert r.status_code == 200
    body = r.get_json()
    assert body['release']['Description'] == 'Bldg C steel'
    assert body['stage_options'] == ['Ship Complete', 'Install Start', 'Install Complete', 'Complete']


def test_detail_off_crew_is_404(client, theirs):
    assert client.get(f'/brain/subcontractor/releases/{theirs.id}').status_code == 404


# ---- activity + notes -------------------------------------------------------------

def test_activity_serves_allowed_actions_only(client, sub, mine):
    JobEventService.create_and_close(job=560, release='923', action='update_stage', source='Brain',
                                     payload={'from': 'Cut Complete', 'to': 'Ship Planning'})
    JobEventService.create_and_close(job=560, release='923', action='update_fab_order', source='Brain',
                                     payload={'from': 5, 'to': 3})
    r = client.get(f'/brain/subcontractor/releases/{mine.id}/activity')
    assert r.status_code == 200
    actions = [e['action'] for e in r.get_json()['events']]
    assert 'update_stage' in actions
    assert 'update_fab_order' not in actions


def test_activity_off_crew_is_404(client, theirs):
    assert client.get(f'/brain/subcontractor/releases/{theirs.id}/activity').status_code == 404


def test_note_posts_to_the_thread_attributed_to_the_sub(client, sub, mine):
    r = client.post(f'/brain/subcontractor/releases/{mine.id}/notes', json={'notes': 'Lift is on site'})
    assert r.status_code == 201
    db.session.refresh(mine)
    assert mine.notes == 'Lift is on site'
    ev = ReleaseEvents.query.filter_by(action='update_notes').one()
    assert ev.external_user_id == f'sub:{sub.id}'
    assert ev.internal_user_id is None
    rows = client.get(f'/brain/subcontractor/releases/{mine.id}/activity').get_json()['events']
    note = next(e for e in rows if e['action'] == 'update_notes')
    assert note['user_name'] == 'Sam Sub'
    assert note['actor_kind'] == 'sub'


def test_note_rejects_empty_and_off_crew(client, mine, theirs):
    assert client.post(f'/brain/subcontractor/releases/{mine.id}/notes', json={'notes': '   '}).status_code == 400
    assert client.post(f'/brain/subcontractor/releases/{theirs.id}/notes', json={'notes': 'x'}).status_code == 404


# ---- stage ------------------------------------------------------------------------

def test_stage_change_runs_the_command_and_is_attributed(client, sub, mine):
    r = client.patch(f'/brain/subcontractor/releases/{mine.id}/stage', json={'stage': 'Install Start'})
    assert r.status_code == 200, r.get_json()
    db.session.refresh(mine)
    assert mine.stage == 'Install Start'
    ev = ReleaseEvents.query.filter_by(action='update_stage').one()
    assert ev.external_user_id == f'sub:{sub.id}'


def test_stage_refuses_shop_stages_and_off_crew(client, mine, theirs):
    r = client.patch(f'/brain/subcontractor/releases/{mine.id}/stage', json={'stage': 'Cut Start'})
    assert r.status_code == 400
    db.session.refresh(mine)
    assert mine.stage == 'Ship Planning'
    assert client.patch(f'/brain/subcontractor/releases/{theirs.id}/stage', json={'stage': 'Install Start'}).status_code == 404


# ---- photos + files ---------------------------------------------------------------

def test_photo_upload_lands_with_the_sub_as_uploader(client, sub, mine, storage):
    r = client.post(f'/brain/subcontractor/releases/{mine.id}/photos',
                    data={'file': (io.BytesIO(PNG), 'site.png'), 'note': 'lift set'},
                    content_type='multipart/form-data')
    assert r.status_code == 201, r.get_json()
    photo = db.session.get(ReleasePhoto, r.get_json()['id'])
    assert photo.uploaded_by_subcontractor_id == sub.id
    assert photo.uploaded_by_user_id is None
    assert ReleaseEvents.query.filter_by(action='upload_photo').one().external_user_id == f'sub:{sub.id}'
    listed = client.get(f'/brain/subcontractor/releases/{mine.id}/attachments').get_json()['photos']
    assert [(p['original_filename'], p['uploaded_by_name']) for p in listed] == [('site.png', 'Sam Sub')]
    assert client.get(f'/brain/subcontractor/releases/{mine.id}/photos/{photo.id}/file').status_code == 200


def test_photo_upload_rejects_non_images(client, mine, storage):
    r = client.post(f'/brain/subcontractor/releases/{mine.id}/photos',
                    data={'file': (io.BytesIO(b'not an image'), 'x.txt')}, content_type='multipart/form-data')
    assert r.status_code == 400


def test_pdf_upload_becomes_the_next_drawing_version(client, sub, mine, storage):
    first = client.post(f'/brain/subcontractor/releases/{mine.id}/files',
                        data={'file': (io.BytesIO(PDF), 'pack.pdf')}, content_type='multipart/form-data')
    assert first.status_code == 201, first.get_json()
    assert first.get_json()['version_number'] == 1
    second = client.post(f'/brain/subcontractor/releases/{mine.id}/files',
                         data={'file': (io.BytesIO(PDF), 'pack2.pdf')}, content_type='multipart/form-data')
    assert second.get_json()['version_number'] == 2
    v2 = db.session.get(ReleaseDrawingVersion, second.get_json()['id'])
    assert v2.uploaded_by_subcontractor_id == sub.id and v2.uploaded_by_user_id is None
    assert client.post(f'/brain/subcontractor/releases/{mine.id}/files',
                       data={'file': (io.BytesIO(b'nope'), 'x.txt')}, content_type='multipart/form-data').status_code == 400


def test_a_splice_sees_the_originals_drawings(client, sub, mine, storage):
    client.post(f'/brain/subcontractor/releases/{mine.id}/files',
                data={'file': (io.BytesIO(PDF), 'pack.pdf')}, content_type='multipart/form-data')
    splice = make_release(560, '923.1', stage='Released', installer='Saul 2', job_name='Alta Metro',
                          parent_release_id=mine.id, is_active=True, is_archived=False)
    db.session.commit()
    listed = client.get(f'/brain/subcontractor/releases/{splice.id}/attachments').get_json()['drawings']
    assert [(d['release_label'], d['version_number'], d['is_current']) for d in listed] == [('560-923', 1, True)]
    vid = listed[0]['id']
    assert client.get(f'/brain/subcontractor/releases/{splice.id}/drawing/versions/{vid}/file').status_code == 200


def test_file_streams_404_off_crew_and_unknown(client, mine, theirs, storage):
    client.post(f'/brain/subcontractor/releases/{mine.id}/files',
                data={'file': (io.BytesIO(PDF), 'pack.pdf')}, content_type='multipart/form-data')
    vid = ReleaseDrawingVersion.query.one().id
    assert client.get(f'/brain/subcontractor/releases/{theirs.id}/drawing/versions/{vid}/file').status_code == 404
    assert client.get(f'/brain/subcontractor/releases/{mine.id}/drawing/versions/999/file').status_code == 404
    assert client.get(f'/brain/subcontractor/releases/{mine.id}/photos/999/file').status_code == 404


# ---- day schedule -----------------------------------------------------------------

def test_day_schedule_is_pinned_to_the_crew_and_strips_notes(client, mine, theirs):
    mine.notes = 'internal cell'
    db.session.commit()
    env = client.get('/brain/subcontractor/install-schedule/by-day?installer=Octavio').get_json()
    codes = [c['code'] for d in env['days'] for c in d['cards']]
    assert codes == ['560-923']                     # the installer param cannot widen the crew
    assert all('notes' not in c for d in env['days'] for c in d['cards'])
    assert env['window']['installer'] == 'Saul 2'


def test_day_schedule_month_mode(client, mine):
    t = date.today()
    env = client.get(f'/brain/subcontractor/install-schedule/by-day?month={t:%Y-%m}').get_json()
    assert env['window']['month'] == f'{t:%Y-%m}'
    assert env['past_due'] == []
    assert any(d['is_today'] for d in env['days'])
    assert ['560-923'] == [c['code'] for d in env['days'] for c in d['cards']]
    assert client.get('/brain/subcontractor/install-schedule/by-day?month=2026-13').status_code == 400


def test_unscoped_account_sees_an_empty_window(app, mine):
    unscoped = make_subcontractor('nocrew@sub.test', accepted=True)
    stack, c = subcontractor_authed_client(app, unscoped)
    with stack:
        env = c.get('/brain/subcontractor/install-schedule/by-day').get_json()
        assert env['summary']['scheduled'] == 0 and len(env['days']) == 15
        assert c.get('/brain/subcontractor/releases').get_json()['releases'] == []


# ---- company scoping: email -> account -> company -> crews ------------------------

def _an_account(app):
    # No installer_team on purpose: the company alone must resolve the crews.
    return make_subcontractor('saul@an.test', accepted=True, contact_name='Saul Rodriguez',
                              company_name='A&N Denver Welding Services, LLC')


def test_a_company_login_sees_every_crew_of_that_company(app):
    for rel, crew in (('1', 'Saul 1'), ('2', 'Saul 3'), ('3', 'Octavio'), ('4', 'saul 2')):
        make_release(700, rel, stage='Ship Planning', installer=crew, job_name='J', start_install=date.today(),
                     is_active=True, is_archived=False)
    db.session.commit()
    stack, c = subcontractor_authed_client(app, _an_account(app))
    with stack:
        codes = sorted(f"{r['Job #']}-{r['Release #']}" for r in c.get('/brain/subcontractor/releases').get_json()['releases'])
        assert codes == ['700-1', '700-2', '700-4']          # all Saul crews, any casing; never Octavio
        crews = c.get('/brain/subcontractor/installer-teams').get_json()['installer_teams']
        assert set(crews) >= {'Saul 1', 'Saul 3', 'saul 2'}
        env = c.get('/brain/subcontractor/install-schedule/by-day').get_json()
        assert sorted(x['code'] for d in env['days'] for x in d['cards']) == ['700-1', '700-2', '700-4']
        assert env['window']['crews'] == crews


def test_company_matching_ignores_the_legal_suffix(app):
    make_release(701, '1', stage='Ship Planning', installer='Eduardo', job_name='J', is_active=True, is_archived=False)
    db.session.commit()
    sub = make_subcontractor('e@ss.test', accepted=True, contact_name='Eduardo Saenz', company_name='S&S Construction')
    stack, c = subcontractor_authed_client(app, sub)
    with stack:
        assert [r['Release #'] for r in c.get('/brain/subcontractor/releases').get_json()['releases']] == ['1']


def test_unmapped_company_falls_back_to_the_admin_picked_crew(app):
    make_release(702, '1', stage='Ship Planning', installer='Saul 1', job_name='J', is_active=True, is_archived=False)
    make_release(702, '2', stage='Ship Planning', installer='Saul 2', job_name='J', is_active=True, is_archived=False)
    db.session.commit()
    sub = make_subcontractor('t@test.test', accepted=True, company_name='McGarey Construction', installer_team='Saul 1')
    stack, c = subcontractor_authed_client(app, sub)
    with stack:
        assert [r['Release #'] for r in c.get('/brain/subcontractor/releases').get_json()['releases']] == ['1']
        assert c.get('/brain/subcontractor/installer-teams').get_json()['installer_teams'] == ['Saul 1']
