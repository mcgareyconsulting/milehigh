"""
Tests for the "+ Verbal Release" form:
  - GET /brain/job-log/release/next-number (prefills the form's Release # field;
    open to any logged-in user, unlike the DWL's drafter/admin-gated equivalent)
  - the duplicate guard on POST /brain/job-log/release (the form submits a single
    CSV row through the same endpoint the "+ Release" button uses; a colliding
    (job, release) pair is blocked and a suggested_next is returned, never silently
    overwritten or reassigned)

Uses the real in-memory SQLite DB; external services are not involved.
"""
import json

from app.models import db, Releases
from app.procore.procore import REL_MIN


_RELEASE_HEADER = "Job #,Release #,Job,Description,Fab Hrs,Install HRS,Paint color,PM,BY,Released,Fab Order"


def _release_csv(job, release):
    return f"{_RELEASE_HEADER}\n{job},{release},Test Job,Desc,40,8,Black,PM1,BY1,,10"


def _make_release(job, release):
    return Releases(job=int(job), release=str(release), job_name="Test Job", is_active=True, is_archived=False)


class TestNextReleaseNumber:
    def test_first_suggestion_is_rel_min(self, non_admin_client):
        resp = non_admin_client.get("/brain/job-log/release/next-number")

        assert resp.status_code == 200
        assert json.loads(resp.data)["next_release"] == str(REL_MIN)

    def test_available_to_a_plain_non_admin_non_drafter_user(self, non_admin_client, mock_non_admin_user):
        # A PM pushing a verbal release through has no admin/drafter role -- unlike
        # the DWL's gated GET /drafting-work-load/rel/next, this endpoint must not 403.
        assert mock_non_admin_user.is_admin is False
        assert mock_non_admin_user.is_drafter is False

        resp = non_admin_client.get("/brain/job-log/release/next-number")

        assert resp.status_code == 200

    def test_requires_login(self, client):
        resp = client.get("/brain/job-log/release/next-number")
        assert resp.status_code == 401

    def test_suggestion_climbs_past_an_active_release(self, app, non_admin_client):
        with app.app_context():
            db.session.add(_make_release(900, REL_MIN))
            db.session.commit()

        resp = non_admin_client.get("/brain/job-log/release/next-number")

        assert resp.status_code == 200
        assert json.loads(resp.data)["next_release"] == str(REL_MIN + 1)


class TestVerbalReleaseDuplicateGuard:
    """The form always submits a concrete Release # (the prefilled suggestion or a
    user-edited value) through the same endpoint "+ Release" uses -- so a collision
    on submit is blocked exactly the way a duplicate paste already is, with a
    suggested_next the user can accept instead of silently reassigning anything."""

    def test_colliding_release_is_blocked_not_overwritten(self, app, non_admin_client):
        with app.app_context():
            db.session.add(_make_release(910, 500))
            db.session.commit()

        resp = non_admin_client.post(
            "/brain/job-log/release",
            json={"csv_data": _release_csv(910, 500)},
        )

        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["created_count"] == 0
        assert body["collision_count"] == 1
        collision = body["collisions"][0]
        assert collision["job"] == 910
        assert collision["release"] == "500"
        assert collision["suggested_next"] == "501"
        # Only the original row exists -- the collision did not create a second one.
        assert Releases.query.filter_by(job=910).count() == 1

    def test_non_colliding_release_is_created(self, non_admin_client):
        resp = non_admin_client.post(
            "/brain/job-log/release",
            json={"csv_data": _release_csv(911, 501)},
        )

        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["created_count"] == 1
        assert Releases.query.filter_by(job=911, release="501").first() is not None


class TestNearDuplicateGuard:
    """Same job with matching job name & description under a different release #
    is a soft warning, not a hard block like the (job, release) collision above --
    the row is withheld until the user confirms via confirm_duplicates=true."""

    def test_matching_job_name_and_description_is_flagged_not_created(self, app, non_admin_client):
        with app.app_context():
            db.session.add(Releases(
                job=920, release="600", job_name="Test Job", description="Desc",
                is_active=True, is_archived=False,
            ))
            db.session.commit()

        resp = non_admin_client.post(
            "/brain/job-log/release",
            json={"csv_data": _release_csv(920, 601)},
        )

        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["created_count"] == 0
        assert body["near_duplicate_count"] == 1
        dup = body["near_duplicates"][0]
        assert dup["job"] == 920
        assert dup["attempted_release"] == "601"
        assert dup["matched_release"] == "600"
        assert Releases.query.filter_by(job=920, release="601").first() is None

    def test_confirm_duplicates_bypasses_and_creates(self, app, non_admin_client):
        with app.app_context():
            db.session.add(Releases(
                job=921, release="600", job_name="Test Job", description="Desc",
                is_active=True, is_archived=False,
            ))
            db.session.commit()

        resp = non_admin_client.post(
            "/brain/job-log/release",
            json={"csv_data": _release_csv(921, 601), "confirm_duplicates": True},
        )

        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["created_count"] == 1
        assert body["near_duplicate_count"] == 0
        assert Releases.query.filter_by(job=921, release="601").first() is not None

    def test_blank_job_name_and_description_does_not_false_positive(self, non_admin_client):
        blank_row = (
            "Job #,Release #,Job,Description,Fab Hrs,Install HRS,Paint color,PM,BY,Released,Fab Order\n"
            "922,{release},,,40,8,Black,PM1,BY1,,10"
        )

        first = non_admin_client.post(
            "/brain/job-log/release",
            json={"csv_data": blank_row.format(release=600)},
        )
        assert json.loads(first.data)["created_count"] == 1

        second = non_admin_client.post(
            "/brain/job-log/release",
            json={"csv_data": blank_row.format(release=601)},
        )
        body = json.loads(second.data)
        assert body["created_count"] == 1
        assert body["near_duplicate_count"] == 0
