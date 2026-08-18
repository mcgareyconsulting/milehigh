"""BUG-8 cross-check: the DWL generator must never hand out a number the job
log will refuse.

The two sides do NOT enforce the same rule, and are not meant to:

  job log  — hard uniqueness on (job, release, normalized job_name), archived
             rows included (`_find_job_release_name_collision`, backed by the
             `uq_releases_job_release_name` constraint). Job numbers wrap, so
             archived 410-108 Columbine may not block a new 410-108 Alta Metro.
  DWL      — a Rel is unique on the VALUE alone across all active releases
             (job-agnostic, deliberately stricter), plus pending DRRs, plus —
             since BUG-8 — every number the submittal's own job has used,
             archived included.

So the property that matters is not equality, it is containment: **anything the
job log would reject, the DWL must already refuse.** That is the direction that
was broken — the DWL issued 108, the job log rejected it later, after the work
was done. These tests pin the containment in both directions, including the
cases where the two deliberately disagree.
"""
import pytest

from app.brain.job_log.routes import _find_job_release_name_collision
from app.models import Releases, Submittals, db
from app.procore.procore import (
    DRR_TYPE,
    RelAssignmentError,
    assign_rel_manual,
    next_rel_number,
)


def _release(job, release, job_name="Columbine Square", **kw):
    r = Releases(job=job, release=str(release), job_name=job_name, **kw)
    db.session.add(r)
    return r


def _drr(sid, project_number, project_name="Columbine Square"):
    s = Submittals(
        submittal_id=sid, procore_project_id="1",
        project_number=str(project_number), project_name=project_name,
        type=DRR_TYPE, status="Open",
    )
    db.session.add(s)
    return s


def _job_log_would_reject(job, release, job_name):
    return _find_job_release_name_collision(job, release, job_name) is not None


def _dwl_would_refuse(submittal, number):
    try:
        assign_rel_manual(submittal, number)
        return False
    except RelAssignmentError:
        return True


# ---------------------------------------------------------------------------
# Containment: job log rejects => DWL already refused
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("archived", [False, True], ids=["active", "archived"])
def test_anything_the_job_log_rejects_the_dwl_refuses(app, archived):
    with app.app_context():
        _release(410, 108, "Columbine Square", is_archived=archived)
        drr = _drr("agree-1", 410, "Columbine Square")
        db.session.commit()

        # Same job, same release, same project name -> the job log's hard key.
        assert _job_log_would_reject(410, "108", "Columbine Square") is True
        assert _dwl_would_refuse(drr, 108) is True


def test_the_archived_case_is_the_one_that_used_to_slip(app):
    """Pre-BUG-8 the DWL saw only ACTIVE releases, so this pair disagreed: the
    job log rejected 108 and the DWL had happily suggested it."""
    with app.app_context():
        _release(410, 107, "Columbine Square")                     # active high-water
        _release(410, 108, "Columbine Square", is_archived=True)   # invisible pre-fix
        _drr("agree-2", 410, "Columbine Square")
        db.session.commit()

        assert _job_log_would_reject(410, "108", "Columbine Square") is True
        # The generator now climbs past it instead of handing it out.
        assert next_rel_number(job_number=410) == 109


# ---------------------------------------------------------------------------
# Where they deliberately differ — documented, not accidental
# ---------------------------------------------------------------------------

def test_dwl_is_stricter_on_a_different_project_reusing_the_job_number(app):
    """The job log ALLOWS archived 410-108 Columbine alongside a new 410-108
    Alta Metro (different project name). The DWL still skips 108 for job 410,
    because it scopes to the job number and ignores the name.

    That asymmetry is intentional: `Submittals.project_name` and
    `Releases.job_name` are populated from different sources, so name-matching
    at suggestion time would miss collisions exactly where the data is fuzzy.
    Being stricter costs a skipped number; being looser costs a rejected
    release after the work is done.
    """
    with app.app_context():
        _release(410, 108, "Columbine Square", is_archived=True)
        drr = _drr("agree-3", 410, "Alta Metro")
        db.session.commit()

        assert _job_log_would_reject(410, "108", "Alta Metro") is False  # JL allows
        assert _dwl_would_refuse(drr, 108) is True                       # DWL still skips
        # Containment still holds — stricter is the safe direction.


def test_dwl_is_stricter_across_jobs_on_active_work(app):
    """Pre-existing design, unchanged by BUG-8: a Rel in use by an ACTIVE
    release on ANY job blocks it everywhere, while the job log only cares about
    the same job + project."""
    with app.app_context():
        _release(500, 108, "Novel Flatirons")       # active, different job
        drr = _drr("agree-4", 410, "Columbine Square")
        db.session.commit()

        assert _job_log_would_reject(410, "108", "Columbine Square") is False
        assert _dwl_would_refuse(drr, 108) is True


def test_another_jobs_archive_does_not_leak_into_this_job(app):
    """The one direction that must stay loose, or the 101-998 range burns down:
    job 500's archived 108 has nothing to do with job 410."""
    with app.app_context():
        _release(500, 108, "Novel Flatirons", is_archived=True)
        drr = _drr("agree-5", 410, "Columbine Square")
        db.session.commit()

        assert _job_log_would_reject(410, "108", "Columbine Square") is False
        assert _dwl_would_refuse(drr, 108) is False  # allowed on both sides


# ---------------------------------------------------------------------------
# The job log's own suggester goes through the same generator
# ---------------------------------------------------------------------------

def test_verbal_release_suggestion_is_job_scoped_too(app, client, admin_session):
    """/job-log/release/next-number shares next_rel_number with the DWL popup.
    It was calling it unscoped, so the verbal form could prefill a number the
    submit guard on the very next click would reject."""
    with app.app_context():
        _release(410, 107, "Columbine Square")
        _release(410, 108, "Columbine Square", is_archived=True)
        db.session.commit()

        scoped = client.get('/brain/job-log/release/next-number', query_string={'job': 410})
        assert scoped.status_code == 200
        assert scoped.get_json()['next_release'] == '109'

        # No job known yet (empty modal) -> unscoped, submit guard is the backstop.
        unscoped = client.get('/brain/job-log/release/next-number')
        assert unscoped.get_json()['next_release'] == '108'
