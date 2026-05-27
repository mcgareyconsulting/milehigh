"""When a hard start_install moves, comp_eta should move with it (never land
before the new start). Covers the UpdateStartInstallCommand window-shift."""
from datetime import date
from unittest.mock import patch

from app.brain.job_log.features.start_install.command import UpdateStartInstallCommand
from app.models import Releases, db
from tests.conftest import make_release


def _run(job, release, new_start):
    with patch("app.brain.job_log.features.start_install.command.update_trello_card"), \
         patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"):
        return UpdateStartInstallCommand(
            job_id=job, release=release, start_install=new_start, push_trello=False,
        ).execute()


def test_comp_eta_shifts_by_same_delta(app):
    with app.app_context():
        make_release(1, "A", start_install=date(2026, 6, 1), comp_eta=date(2026, 6, 5),
                     installer="Saul 2", install_hrs=24)
        db.session.commit()
        _run(1, "A", date(2026, 6, 11))  # +10 days
        r = Releases.query.filter_by(job=1, release="A").first()
        assert r.start_install == date(2026, 6, 11)
        assert r.comp_eta == date(2026, 6, 15)  # 6/5 + 10 days


def test_comp_eta_clamped_when_no_prior_start(app):
    """The reported bug: start jumps forward, stale comp_eta is left behind it."""
    with app.app_context():
        make_release(2, "B", start_install=None, comp_eta=date(2026, 4, 28),
                     installer="Saul 2", install_hrs=24)
        db.session.commit()
        _run(2, "B", date(2026, 6, 1))
        r = Releases.query.filter_by(job=2, release="B").first()
        assert r.comp_eta >= r.start_install          # never before start
        assert r.comp_eta == date(2026, 6, 2)         # start + ceil(24/24)=1 day


def test_comp_eta_none_stays_none(app):
    with app.app_context():
        make_release(3, "C", start_install=date(2026, 6, 1), comp_eta=None,
                     installer="Saul 2", install_hrs=24)
        db.session.commit()
        _run(3, "C", date(2026, 6, 10))
        r = Releases.query.filter_by(job=3, release="C").first()
        assert r.comp_eta is None
