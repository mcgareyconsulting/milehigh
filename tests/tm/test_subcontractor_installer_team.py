from app.models import Subcontractor, db


def _sub(app, **kw):
    s = Subcontractor(company_name='Acme', contact_name='Sam', email='s@a.test', **kw)
    db.session.add(s); db.session.commit()
    return s


def test_options_exclude_mhmw_crew(app, admin_client):
    r = admin_client.get('/brain/subcontractors/installer-teams')
    assert r.status_code == 200
    teams = r.get_json()['installer_teams']
    assert 'Octavio' in teams and 'Saul 2' in teams
    assert 'Oscar' not in teams


def test_set_clear_and_reject(app, admin_client):
    s = _sub(app)
    r = admin_client.patch(f'/brain/subcontractors/{s.id}/installer-team',
                           json={'installer_team': 'saul 2'})
    assert r.status_code == 200
    assert r.get_json()['installer_team'] == 'Saul 2'   # canonical casing stored

    r = admin_client.patch(f'/brain/subcontractors/{s.id}/installer-team',
                           json={'installer_team': None})
    assert r.status_code == 200 and r.get_json()['installer_team'] is None

    for bad in ('Oscar', 'Sual 2'):
        r = admin_client.patch(f'/brain/subcontractors/{s.id}/installer-team',
                               json={'installer_team': bad})
        assert r.status_code == 400, bad

    r = admin_client.patch(f'/brain/subcontractors/{s.id}/installer-team', json={})
    assert r.status_code == 400


def test_requires_admin(app, client):
    s = _sub(app)
    r = client.patch(f'/brain/subcontractors/{s.id}/installer-team',
                     json={'installer_team': 'Octavio'})
    assert r.status_code in (401, 403)
