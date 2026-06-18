"""
Tests for the DWL start-install feature:
  - PUT /drafting-work-load/start-install (set/clear, DRR+Rel gate, DDD derivation,
    PendingStartInstall upsert/delete)
  - the start-install handoff inside POST /brain/job-log/release (a pasted Release #
    that matches a pending Rel stamps the date onto the new release and consumes it)

Uses the real in-memory SQLite DB; external services are not involved. setup_auth
(autouse in tests/dwl/conftest.py) authenticates as admin.
"""
import json
from datetime import date

import pytest

from app.models import db, Submittals, Releases, PendingStartInstall
from app.procore.procore import DRR_TYPE
from app.trello.utils import calculate_business_days_before


def _make_submittal(sid, *, type_=DRR_TYPE, rel=None, project_number="100", status="Open", due_date=None):
    s = Submittals(
        submittal_id=str(sid),
        procore_project_id="1",
        project_number=project_number,
        type=type_,
        status=status,
        rel=rel,
        due_date=due_date,
    )
    db.session.add(s)
    db.session.commit()
    return s


# --- PUT /drafting-work-load/start-install -----------------------------------------

class TestUpdateStartInstall:
    def test_set_overwrites_due_date_and_creates_pending(self, app, client):
        _make_submittal("S1", rel=201, project_number="100")
        si = date(2026, 9, 1)

        resp = client.put(
            "/brain/drafting-work-load/start-install",
            json={"submittal_id": "S1", "start_install": si.isoformat()},
        )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        # Due date is overwritten with the drawings-due date: 15 business days before.
        expected_due = calculate_business_days_before(si, 15)
        assert data["start_install"] == si.isoformat()
        assert data["due_date"] == expected_due.isoformat()

        s = Submittals.query.filter_by(submittal_id="S1").first()
        assert s.start_install == si
        assert s.due_date == expected_due

        pending = PendingStartInstall.query.filter_by(rel=201).first()
        assert pending is not None
        assert pending.start_install == si
        assert pending.job_number == "100"
        assert pending.submittal_id == "S1"
        assert pending.consumed_at is None

    def test_explicit_due_date_overrides_computed_default(self, app, client):
        # The modal sends a (possibly tweaked) due date; the backend uses it verbatim.
        _make_submittal("S1c", rel=211)
        si = date(2026, 9, 1)
        tweaked = date(2026, 8, 14)  # not the 15-business-day default

        resp = client.put(
            "/brain/drafting-work-load/start-install",
            json={"submittal_id": "S1c", "start_install": si.isoformat(), "due_date": tweaked.isoformat()},
        )

        assert resp.status_code == 200
        assert json.loads(resp.data)["due_date"] == tweaked.isoformat()
        s = Submittals.query.filter_by(submittal_id="S1c").first()
        assert s.start_install == si
        assert s.due_date == tweaked

    def test_set_overwrites_existing_due_date(self, app, client):
        # Even a manually-entered due date is overwritten when a start install is set.
        _make_submittal("S1b", rel=210, due_date=date(2026, 8, 20))
        si = date(2026, 9, 1)

        client.put(
            "/brain/drafting-work-load/start-install",
            json={"submittal_id": "S1b", "start_install": si.isoformat()},
        )

        s = Submittals.query.filter_by(submittal_id="S1b").first()
        assert s.due_date == calculate_business_days_before(si, 15)  # not 2026-08-20

    def test_clear_removes_start_install_due_date_and_pending(self, app, client):
        _make_submittal("S2", rel=202)
        si = date(2026, 9, 1)
        client.put(
            "/brain/drafting-work-load/start-install",
            json={"submittal_id": "S2", "start_install": si.isoformat()},
        )
        computed_due = calculate_business_days_before(si, 15)
        assert Submittals.query.filter_by(submittal_id="S2").first().due_date == computed_due
        assert PendingStartInstall.query.filter_by(rel=202).first() is not None

        resp = client.put(
            "/brain/drafting-work-load/start-install",
            json={"submittal_id": "S2", "start_install": None},
        )

        assert resp.status_code == 200
        s = Submittals.query.filter_by(submittal_id="S2").first()
        assert s.start_install is None
        assert s.due_date is None  # clearing the start install wipes the derived due date too
        assert PendingStartInstall.query.filter_by(rel=202).first() is None

    def test_reject_non_drr(self, app, client):
        _make_submittal("S3", type_="Submittal for GC Approval", rel=203)

        resp = client.put(
            "/brain/drafting-work-load/start-install",
            json={"submittal_id": "S3", "start_install": "2026-09-01"},
        )

        assert resp.status_code == 400
        assert json.loads(resp.data)["code"] == "drr_rel_required"
        assert PendingStartInstall.query.filter_by(rel=203).first() is None

    def test_reject_drr_without_rel(self, app, client):
        _make_submittal("S4", rel=None)

        resp = client.put(
            "/brain/drafting-work-load/start-install",
            json={"submittal_id": "S4", "start_install": "2026-09-01"},
        )

        assert resp.status_code == 400
        assert json.loads(resp.data)["code"] == "drr_rel_required"

    def test_resetting_date_reopens_consumed_pending(self, app, client):
        _make_submittal("S5", rel=205)
        client.put(
            "/brain/drafting-work-load/start-install",
            json={"submittal_id": "S5", "start_install": "2026-09-01"},
        )
        pending = PendingStartInstall.query.filter_by(rel=205).first()
        pending.consumed_at = date(2026, 1, 1)  # simulate prior consumption
        pending.consumed_job = 1
        db.session.commit()

        client.put(
            "/brain/drafting-work-load/start-install",
            json={"submittal_id": "S5", "start_install": "2026-10-01"},
        )

        pending = PendingStartInstall.query.filter_by(rel=205).first()
        assert pending.start_install == date(2026, 10, 1)
        assert pending.consumed_at is None
        assert pending.consumed_job is None


# --- handoff inside POST /brain/job-log/release ------------------------------------

_RELEASE_HEADER = "Job #,Release #,Job,Description,Fab Hrs,Install HRS,Paint color,PM,BY,Released,Fab Order"


def _release_csv(job, release, *, install_hrs="8"):
    # Header row + one data row (the endpoint auto-detects and skips the header).
    return f"{_RELEASE_HEADER}\n{job},{release},Test Job,Desc,40,{install_hrs},Black,PM1,BY1,,10"


class TestReleaseCreationHandoff:
    def test_pending_date_transfers_and_is_consumed(self, app, client):
        si = date(2026, 9, 1)
        db.session.add(PendingStartInstall(
            rel=300, job_number="700", submittal_id="SX", start_install=si,
        ))
        db.session.commit()

        resp = client.post(
            "/brain/job-log/release",
            json={"csv_data": _release_csv(700, 300, install_hrs="8")},
        )

        assert resp.status_code == 200
        assert json.loads(resp.data)["created_count"] == 1

        rel_row = Releases.query.filter_by(job=700, release="300").first()
        assert rel_row is not None
        assert rel_row.start_install == si
        assert rel_row.start_install_formulaTF is False
        # install_hrs=8, default num_guys=2 -> capacity 16 -> 1 install day -> comp_eta == start.
        assert rel_row.comp_eta == si

        pending = PendingStartInstall.query.filter_by(rel=300).first()
        assert pending.consumed_at is not None
        assert pending.consumed_job == 700
        assert pending.consumed_release == "300"

    def test_no_pending_is_noop(self, app, client):
        resp = client.post(
            "/brain/job-log/release",
            json={"csv_data": _release_csv(701, 301)},
        )

        assert resp.status_code == 200
        rel_row = Releases.query.filter_by(job=701, release="301").first()
        assert rel_row is not None
        assert rel_row.start_install is None

    def test_non_numeric_release_does_not_match_or_crash(self, app, client):
        db.session.add(PendingStartInstall(
            rel=302, job_number="702", submittal_id="SY", start_install=date(2026, 9, 1),
        ))
        db.session.commit()

        resp = client.post(
            "/brain/job-log/release",
            json={"csv_data": _release_csv(702, "V2")},
        )

        assert resp.status_code == 200
        rel_row = Releases.query.filter_by(job=702, release="V2").first()
        assert rel_row is not None
        assert rel_row.start_install is None
        # Pending row for a different (numeric) rel is untouched.
        assert PendingStartInstall.query.filter_by(rel=302).first().consumed_at is None
