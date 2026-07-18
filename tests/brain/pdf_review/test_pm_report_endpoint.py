"""Report endpoint gate + PM notification wiring for BB review.

Covers:
  - GET /brain/releases/<id>/bb-review/report visibility: admin, the release's PM, and
    an unrelated non-admin.
  - worker._notify_pm creates exactly one bb_review Notification for the resolved PM, and
    stays quiet when the PM is unresolved or the review is fully cleared.
"""
from unittest.mock import patch

import pytest

from app.models import db, BBDrawingReview, ReleaseDrawingVersion, Notification
from tests.conftest import make_release


COMPLETE_FINDINGS = [
    {"rule_id": "stair-terminal-rise-over-max", "verdict": "violation", "severity": "high",
     "issue": "terminal rise > 7\""},
    {"rule_id": "guard-opening-limits", "verdict": "needs_field_verification", "severity": "high",
     "issue": "landing guard opening"},
]


def _seed_review(app, *, pm="DR", status="complete", findings=None):
    """A release + one drawing version + one BB review, committed."""
    with app.app_context():
        release = make_release(590, "674", pm=pm)
        db.session.flush()
        version = ReleaseDrawingVersion(
            release_id=release.id, version_number=1, storage_key="k/1.pdf",
            mime_type="application/pdf", file_size_bytes=1, uploaded_by_user_id=1,
        )
        db.session.add(version)
        db.session.flush()
        review = BBDrawingReview(
            drawing_version_id=version.id, release_id=release.id, status=status,
            findings=findings if findings is not None else COMPLETE_FINDINGS,
            model="test",
        )
        db.session.add(review)
        db.session.commit()
        return release.id, version.id, review.id


def _url(release_id):
    return f"/brain/releases/{release_id}/bb-review/report"


def test_admin_sees_report(app, admin_client):
    release_id, _, _ = _seed_review(app)
    resp = admin_client.get(_url(release_id))
    assert resp.status_code == 200
    report = resp.get_json()["report"]
    assert report["tally"]["critical"] == 1
    assert report["hold_recommended"] is True
    assert report["job_release"] == "590-674"


def test_release_pm_sees_report(app, non_admin_client, mock_non_admin_user):
    release_id, _, _ = _seed_review(app)
    # Resolve this release's PM to the (non-admin) current user -> allowed by ownership.
    with patch("app.brain.pdf_review.routes.release_owner_user",
               return_value=mock_non_admin_user.id):
        resp = non_admin_client.get(_url(release_id))
    assert resp.status_code == 200
    assert resp.get_json()["report"]["job_release"] == "590-674"


def test_unrelated_non_admin_forbidden(app, non_admin_client):
    release_id, _, _ = _seed_review(app)
    with patch("app.brain.pdf_review.routes.release_owner_user", return_value=999):
        resp = non_admin_client.get(_url(release_id))
    assert resp.status_code == 403


def test_no_complete_review_returns_null(app, admin_client):
    release_id, _, _ = _seed_review(app, status="pending")
    resp = admin_client.get(_url(release_id))
    assert resp.status_code == 200
    assert resp.get_json()["report"] is None


def test_missing_release_404(app, admin_client):
    resp = admin_client.get(_url(999999))
    assert resp.status_code == 404


# --- worker._notify_pm --------------------------------------------------------

def test_notify_pm_creates_notification(app):
    from app.brain.pdf_review import worker
    from app.models import Releases
    release_id, _, review_id = _seed_review(app)
    with app.app_context():
        review = db.session.get(BBDrawingReview, review_id)
        release = db.session.get(Releases, release_id)
        with patch("app.brain.pdf_review.worker.release_owner_user", return_value=7):
            worker._notify_pm(review, release, review.findings)
        notes = Notification.query.filter_by(type="bb_review").all()
        assert len(notes) == 1
        assert notes[0].user_id == 7
        assert notes[0].bb_drawing_review_id == review_id
        assert "590-674" in notes[0].message


def test_notify_pm_quiet_when_pm_unresolved(app):
    from app.brain.pdf_review import worker
    from app.models import Releases
    release_id, _, review_id = _seed_review(app)
    with app.app_context():
        review = db.session.get(BBDrawingReview, review_id)
        release = db.session.get(Releases, release_id)
        with patch("app.brain.pdf_review.worker.release_owner_user", return_value=None):
            worker._notify_pm(review, release, review.findings)
        assert Notification.query.filter_by(type="bb_review").count() == 0


def test_notify_pm_quiet_when_all_cleared(app):
    from app.brain.pdf_review import worker
    from app.models import Releases
    release_id, _, review_id = _seed_review(
        app, findings=[{"verdict": "ok", "severity": "low", "rule_id": "x"}])
    with app.app_context():
        review = db.session.get(BBDrawingReview, review_id)
        release = db.session.get(Releases, release_id)
        with patch("app.brain.pdf_review.worker.release_owner_user", return_value=7):
            worker._notify_pm(review, release, review.findings)
        assert Notification.query.filter_by(type="bb_review").count() == 0
