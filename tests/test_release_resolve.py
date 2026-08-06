"""Releases.resolve — canonical-row resolution under job-number wrap.

Uniqueness is (job, release, job_name), so two rows can share the same
digits (archived 410-108 Columbine vs active 410-108 Alta). resolve() is
the single lookup every digits-only consumer (routes, commands, outbox,
scanner) goes through so those paths hit the row a human means.
"""
from app.models import Releases, db
from tests.conftest import make_release


class TestResolve:
    def test_single_row(self, app):
        with app.app_context():
            r = make_release(410, "108", job_name="Alta")
            db.session.commit()
            assert Releases.resolve(410, "108").id == r.id

    def test_missing_returns_none(self, app):
        with app.app_context():
            assert Releases.resolve(999, "X") is None

    def test_prefers_non_archived_over_archived(self, app):
        with app.app_context():
            make_release(410, "108", job_name="Columbine", is_archived=True)
            new = make_release(410, "108", job_name="Alta")
            db.session.commit()
            assert Releases.resolve(410, "108").id == new.id

    def test_prefers_active_over_soft_deleted(self, app):
        with app.app_context():
            make_release(411, "108", job_name="Columbine", is_active=False)
            new = make_release(411, "108", job_name="Alta", is_active=None)
            db.session.commit()
            # NULL is_active counts as active (matches active_releases_filter).
            assert Releases.resolve(411, "108").id == new.id

    def test_exact_name_match_beats_row_preference(self, app):
        with app.app_context():
            old = make_release(412, "108", job_name="Columbine", is_archived=True)
            make_release(412, "108", job_name="Alta")
            db.session.commit()
            # Explicit name pins the archived row, case/whitespace-insensitive.
            assert Releases.resolve(412, "108", job_name="  columbine ").id == old.id

    def test_unknown_name_falls_back_to_row_preference(self, app):
        with app.app_context():
            make_release(413, "108", job_name="Columbine", is_archived=True)
            new = make_release(413, "108", job_name="Alta")
            db.session.commit()
            assert Releases.resolve(413, "108", job_name="No Such Job").id == new.id

    def test_newest_row_is_final_tiebreak(self, app):
        with app.app_context():
            make_release(414, "108", job_name="Columbine")
            newer = make_release(414, "108", job_name="Alta")
            db.session.commit()
            assert Releases.resolve(414, "108").id == newer.id
