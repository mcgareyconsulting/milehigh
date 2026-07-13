"""PM training-loop feedback on BB findings.

Covers POST /brain/releases/<id>/bb-review/<review_id>/feedback:
  - admin can accept/deny with notes; the row lands with the finding snapshot + context
  - re-posting the same finding upserts (no duplicate row)
  - the report GET carries prior feedback keyed by finding_index
  - auth gate (unrelated non-admin 403) and validation (bad decision 400)
"""
from unittest.mock import patch

from app.models import db, BBDrawingReview, BBReviewFeedback, ReleaseDrawingVersion
from tests.conftest import make_release


COMPLETE_FINDINGS = [
    {"rule_id": "stair-terminal-rise-over-max", "verdict": "violation", "severity": "high",
     "issue": "terminal rise > 7\""},
    {"rule_id": "guard-opening-limits", "verdict": "needs_field_verification", "severity": "high",
     "issue": "landing guard opening"},
]


def _seed_review(app, *, pm="DR", findings=None, job=590, rel="674"):
    with app.app_context():
        release = make_release(job, rel, pm=pm)
        db.session.flush()
        version = ReleaseDrawingVersion(
            release_id=release.id, version_number=1, storage_key="k/1.pdf",
            mime_type="application/pdf", file_size_bytes=1, uploaded_by_user_id=1,
        )
        db.session.add(version)
        db.session.flush()
        review = BBDrawingReview(
            drawing_version_id=version.id, release_id=release.id, status="complete",
            findings=findings if findings is not None else COMPLETE_FINDINGS, model="test",
        )
        db.session.add(review)
        db.session.commit()
        return release.id, version.id, review.id


def _fb_url(release_id, review_id):
    return f"/brain/releases/{release_id}/bb-review/{review_id}/feedback"


def _report_url(release_id):
    return f"/brain/releases/{release_id}/bb-review/report"


def test_admin_saves_feedback_with_context(app, admin_client):
    release_id, version_id, review_id = _seed_review(app)
    resp = admin_client.post(_fb_url(release_id, review_id), json={
        "finding_index": 0, "decision": "accepted", "rule_id": "stair-terminal-rise-over-max",
        "notes": "BB nailed it, this rise is 8\"", "finding": COMPLETE_FINDINGS[0],
    })
    assert resp.status_code == 200
    with app.app_context():
        rows = BBReviewFeedback.query.all()
        assert len(rows) == 1
        fb = rows[0]
        assert fb.decision == "accepted"
        assert fb.notes == "BB nailed it, this rise is 8\""
        assert fb.rule_id == "stair-terminal-rise-over-max"
        assert fb.finding_index == 0
        assert fb.release_id == release_id
        assert fb.drawing_version_id == version_id
        assert fb.finding_snapshot["issue"] == "terminal rise > 7\""


def test_resubmit_upserts(app, admin_client):
    release_id, _, review_id = _seed_review(app)
    admin_client.post(_fb_url(release_id, review_id),
                      json={"finding_index": 0, "decision": "accepted"})
    admin_client.post(_fb_url(release_id, review_id),
                      json={"finding_index": 0, "decision": "rejected", "notes": "changed my mind"})
    with app.app_context():
        rows = BBReviewFeedback.query.filter_by(review_id=review_id, finding_index=0).all()
        assert len(rows) == 1
        assert rows[0].decision == "rejected"
        assert rows[0].notes == "changed my mind"


def test_report_carries_feedback(app, admin_client):
    release_id, _, review_id = _seed_review(app)
    admin_client.post(_fb_url(release_id, review_id),
                      json={"finding_index": 1, "decision": "rejected", "notes": "pours into slab"})
    report = admin_client.get(_report_url(release_id)).get_json()["report"]
    assert report["feedback"]["1"] == {"decision": "rejected", "notes": "pours into slab"}


def test_version_panel_get_carries_feedback(app, admin_client):
    release_id, version_id, review_id = _seed_review(app)
    admin_client.post(_fb_url(release_id, review_id),
                      json={"finding_index": 0, "decision": "accepted", "notes": "confirmed 8\""})
    url = f"/brain/releases/{release_id}/drawing/versions/{version_id}/bb-review"
    review = admin_client.get(url).get_json()["review"]
    assert review["feedback"]["0"] == {"decision": "accepted", "notes": "confirmed 8\""}


def test_bad_decision_rejected(app, admin_client):
    release_id, _, review_id = _seed_review(app)
    resp = admin_client.post(_fb_url(release_id, review_id),
                             json={"finding_index": 0, "decision": "maybe"})
    assert resp.status_code == 400


def test_missing_finding_index_rejected(app, admin_client):
    release_id, _, review_id = _seed_review(app)
    resp = admin_client.post(_fb_url(release_id, review_id), json={"decision": "accepted"})
    assert resp.status_code == 400


def test_unrelated_non_admin_forbidden(app, non_admin_client):
    release_id, _, review_id = _seed_review(app)
    with patch("app.brain.pdf_review.routes.release_owner_user", return_value=999):
        resp = non_admin_client.post(_fb_url(release_id, review_id),
                                     json={"finding_index": 0, "decision": "accepted"})
    assert resp.status_code == 403


def test_review_release_mismatch_404(app, admin_client):
    release_id, _, review_id = _seed_review(app)
    other = _seed_review(app, job=591)[0]
    resp = admin_client.post(_fb_url(other, review_id),
                             json={"finding_index": 0, "decision": "accepted"})
    assert resp.status_code == 404
