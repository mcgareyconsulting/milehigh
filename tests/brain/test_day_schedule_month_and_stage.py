"""Month mode and the stage lane on the day-row schedule (the phone Job Log's filters).

Month mode is history-browsing, not triage: every day of the month is emitted and
nothing is bucketed as past due. The stage filter is the phone's "Shipping Planning"
lane — every crew's releases sitting in one stage — and composes with month.
"""
from datetime import date

from app.brain.install_schedule.service import build_day_schedule, build_month_schedule
from tests.conftest import make_release

TODAY = date(2026, 9, 10)


def _rel(job, release, day, **kw):
    kw.setdefault('stage', 'Ship Planning')
    kw.setdefault('installer', 'Octavio')
    return make_release(job, release, start_install=day, start_install_formulaTF=False, **kw)


def test_month_emits_every_day_and_never_triages(app):
    _rel(1, 'A', date(2026, 9, 2))            # before TODAY: still on its own day
    _rel(1, 'B', date(2026, 9, 25))
    _rel(1, 'C', date(2026, 10, 1))           # next month: excluded
    env = build_month_schedule(2026, 9, today=TODAY)
    assert env['window'] == {'start': '2026-09-01', 'end': '2026-09-30', 'today': '2026-09-10',
                             'month': '2026-09', 'installer': None, 'stage': None}
    assert len(env['days']) == 30 and env['past_due'] == []
    assert [d['date'] for d in env['days'] if d['card_count']] == ['2026-09-02', '2026-09-25']
    assert sum(1 for d in env['days'] if d['is_today']) == 1
    assert env['summary']['scheduled'] == 2


def test_stage_lane_crosses_crews_and_composes_with_installer(app):
    _rel(1, 'A', TODAY, stage='Ship Planning', installer='Octavio')
    _rel(1, 'B', TODAY, stage='Ship Planning', installer='Saul 2')
    _rel(1, 'C', TODAY, stage='Cut Start', installer='Octavio')
    lane = build_day_schedule(today=TODAY, stage='Ship Planning')
    assert sorted(c['code'] for d in lane['days'] for c in d['cards']) == ['1-A', '1-B']
    assert lane['window']['stage'] == 'Ship Planning'
    both = build_day_schedule(today=TODAY, stage='Ship Planning', installer='Saul 2')
    assert [c['code'] for d in both['days'] for c in d['cards']] == ['1-B']
    month = build_month_schedule(2026, 9, today=TODAY, stage='Cut Start')
    assert [c['code'] for d in month['days'] for c in d['cards']] == ['1-C']


def test_cards_carry_description_for_the_phone_card(app):
    _rel(1, 'A', TODAY, description='Bldg C steel')
    card = next(c for d in build_day_schedule(today=TODAY)['days'] for c in d['cards'])
    assert card['description'] == 'Bldg C steel'


def test_route_validates_month_and_accepts_stage(admin_client):
    assert admin_client.get('/brain/install-schedule/by-day?month=2026-13').status_code == 400
    assert admin_client.get('/brain/install-schedule/by-day?month=sept').status_code == 400
    ok = admin_client.get('/brain/install-schedule/by-day?month=2026-09&stage=Ship%20Planning')
    assert ok.status_code == 200
    assert ok.get_json()['window']['month'] == '2026-09' and ok.get_json()['window']['stage'] == 'Ship Planning'
