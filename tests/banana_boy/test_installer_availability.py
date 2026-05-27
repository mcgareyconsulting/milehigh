"""Unit tests for the installer-team conflict/availability service."""
from datetime import date

from app.brain.job_log.scheduling.installer_availability import (
    default_window_days,
    find_conflicts,
    free_teams,
    release_window,
    team_availability,
    windows_overlap,
)
from app.models import db
from tests.conftest import make_release


def _rel(job, release, start, *, installer="Saul 2", install_hrs=24, comp_eta=None, **extra):
    return make_release(
        job, release,
        start_install=start, installer=installer,
        install_hrs=install_hrs, comp_eta=comp_eta, **extra,
    )


def test_default_window_days():
    assert default_window_days(None) == 1
    assert default_window_days(0) == 1
    assert default_window_days(24) == 1   # ceil(24/24)=1
    assert default_window_days(25) == 2
    assert default_window_days(48) == 2


def test_release_window_prefers_comp_eta(app):
    with app.app_context():
        r = _rel(100, "1", date(2026, 6, 1), comp_eta=date(2026, 6, 5), install_hrs=24)
        db.session.commit()
        assert release_window(r) == (date(2026, 6, 1), date(2026, 6, 5))


def test_release_window_defaults_from_hours(app):
    with app.app_context():
        r = _rel(100, "2", date(2026, 6, 1), install_hrs=48, comp_eta=None)
        db.session.commit()
        assert release_window(r) == (date(2026, 6, 1), date(2026, 6, 3))  # +2 days


def test_windows_overlap_inclusive():
    assert windows_overlap(date(2026, 6, 1), date(2026, 6, 3),
                           date(2026, 6, 3), date(2026, 6, 5))  # touch = overlap
    assert not windows_overlap(date(2026, 6, 1), date(2026, 6, 2),
                               date(2026, 6, 3), date(2026, 6, 5))


def test_find_conflicts_same_team_overlap_only(app):
    with app.app_context():
        _rel(200, "1", date(2026, 6, 1), installer="Saul 2", comp_eta=date(2026, 6, 4))
        db.session.commit()
        assert len(find_conflicts("Saul 2", date(2026, 6, 3), date(2026, 6, 6))) == 1
        assert find_conflicts("Saul 2", date(2026, 6, 10), date(2026, 6, 12)) == []
        assert find_conflicts("Saul 3", date(2026, 6, 3), date(2026, 6, 6)) == []


def test_find_conflicts_excludes_self(app):
    with app.app_context():
        _rel(200, "1", date(2026, 6, 1), installer="Saul 2", comp_eta=date(2026, 6, 4))
        db.session.commit()
        assert find_conflicts("Saul 2", date(2026, 6, 1), date(2026, 6, 4),
                              exclude_job=200, exclude_release="1") == []


def test_ineligible_releases_ignored(app):
    with app.app_context():
        # formula-driven date -> not on the timeline
        _rel(300, "1", date(2026, 6, 1), installer="Saul 2", comp_eta=date(2026, 6, 4),
             start_install_formulaTF=True)
        # zero install hours -> not on the timeline
        _rel(300, "2", date(2026, 6, 1), installer="Saul 2", comp_eta=date(2026, 6, 4),
             install_hrs=0)
        # wrong stage group
        _rel(300, "3", date(2026, 6, 1), installer="Saul 2", comp_eta=date(2026, 6, 4),
             stage_group="DRAFTING")
        db.session.commit()
        assert find_conflicts("Saul 2", date(2026, 6, 1), date(2026, 6, 4)) == []


def test_team_availability_and_free_teams(app):
    with app.app_context():
        _rel(400, "1", date(2026, 6, 1), installer="Saul 2", comp_eta=date(2026, 6, 4))
        db.session.commit()
        teams = ["Saul 2", "Saul 3"]
        avail = team_availability(date(2026, 6, 2), date(2026, 6, 3), teams=teams)
        assert len(avail["Saul 2"]) == 1
        assert avail["Saul 3"] == []
        assert free_teams(date(2026, 6, 2), date(2026, 6, 3), teams=teams) == ["Saul 3"]
