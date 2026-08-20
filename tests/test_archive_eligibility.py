"""
Tests for the Job Log archive eligibility rule (_archivable_query).

A release is archivable only when it is fully closed out:
    stage = 'Complete'  AND  job_comp (Install Prog) = 'X'  AND  invoiced = 'X'

Stage matters because setting Install Prog to 'X' cascades the stage to
'Install Complete' — without the stage predicate, every installed-but-not-
closed-out release gets swept into the archive.
"""
import pytest

from app.models import Releases, db
from app.brain.job_log.routes import _archivable_query
from tests.conftest import make_release


@pytest.fixture(autouse=True)
def setup_auth(admin_session):
    yield


def _keys(rows):
    return {(r.job, r.release) for r in rows}


def test_complete_with_both_marks_is_archivable(app):
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", None, job_comp="X", invoiced="X")
        db.session.commit()

        assert _keys(_archivable_query().all()) == {(1, "A")}


def test_install_complete_is_not_archivable(app):
    """The reported bug: Install Complete + Install Prog X + Invoiced X was pulled."""
    with app.app_context():
        make_release(1, "A", "Install Complete", "COMPLETE", None, job_comp="X", invoiced="X")
        db.session.commit()

        assert _archivable_query().all() == []


def test_complete_missing_a_mark_is_not_archivable(app):
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", None, job_comp="X", invoiced=None)
        make_release(2, "A", "Complete", "COMPLETE", None, job_comp=None, invoiced="X")
        make_release(3, "A", "Complete", "COMPLETE", None, job_comp=None, invoiced=None)
        db.session.commit()

        assert _archivable_query().all() == []


def test_stage_and_marks_are_case_and_whitespace_insensitive(app):
    with app.app_context():
        make_release(1, "A", " complete ", "COMPLETE", None, job_comp=" x ", invoiced="x")
        db.session.commit()

        assert _keys(_archivable_query().all()) == {(1, "A")}


def test_already_archived_and_inactive_rows_are_excluded(app):
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", None, job_comp="X", invoiced="X",
                     is_archived=True)
        make_release(2, "A", "Complete", "COMPLETE", None, job_comp="X", invoiced="X",
                     is_active=False)
        make_release(3, "A", "Complete", "COMPLETE", None, job_comp="X", invoiced="X")
        db.session.commit()

        assert _keys(_archivable_query().all()) == {(3, "A")}


def test_archive_preview_endpoint_reports_only_complete(client, app):
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", None, job_comp="X", invoiced="X")
        make_release(2, "A", "Install Complete", "COMPLETE", None, job_comp="X", invoiced="X")
        db.session.commit()

    resp = client.get("/brain/archive-preview")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert data["releases"][0]["job"] == 1
    assert data["releases"][0]["stage"] == "Complete"


def test_archive_confirm_archives_only_complete(client, app):
    with app.app_context():
        make_release(1, "A", "Complete", "COMPLETE", None, job_comp="X", invoiced="X")
        make_release(2, "A", "Install Complete", "COMPLETE", None, job_comp="X", invoiced="X")
        db.session.commit()

    resp = client.post("/brain/archive-confirm")
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 1

    with app.app_context():
        assert Releases.query.filter_by(job=1, release="A").first().is_archived is True
        assert Releases.query.filter_by(job=2, release="A").first().is_archived is not True
