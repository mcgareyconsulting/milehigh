"""BB review workspace — per-submittal-document endpoints (Track B).

Covers the /procore-submittals/<id>/documents surface: the merged document listing, the
enqueue-and-background review (202 + pending row) plus the worker job that persists a
submittal-keyed BBDrawingReview (release/version null), the review_only cache gate, and
submittal-keyed feedback. Procore + the Claude call are mocked.
"""
from unittest.mock import patch

import pytest

from app.models import db, Submittals, BBDrawingReview, BBReviewFeedback


VIOLATION_FINDINGS = [
    {"rule_id": "stair-terminal-rise-over-max", "verdict": "violation", "severity": "high",
     "issue": "terminal rise > 7\""},
    {"rule_id": "guard-opening-limits", "verdict": "needs_field_verification", "severity": "high",
     "issue": "landing guard opening"},
]

# Two drawing refs on one submittal: an originating copy and an approver markup.
REFS = [
    {"source": "originating", "name": "S-1.pdf", "item_id": 111, "item_type": "SubmittalLog",
     "attachment_id": 5001, "project_id": 42, "company_id": "18521"},
    {"source": "approver", "name": "S-1-markup.pdf", "item_id": 111,
     "item_type": "SubmittalLogApprover", "attachment_id": 5002, "project_id": 42,
     "company_id": "18521"},
]


def _seed_submittal(app, *, sid="9001", type_="For Construction"):
    with app.app_context():
        s = Submittals(
            submittal_id=sid, procore_project_id="42", project_number="590",
            project_name="Test", title="Stair pack", status="Open", type=type_,
            ball_in_court="Katie", rel=674,
        )
        db.session.add(s)
        db.session.commit()
        return sid


def _docs_url(sid):
    return f"/brain/procore-submittals/{sid}/documents"


def test_documents_lists_refs_with_cache_and_review(app, admin_client, tmp_path):
    app.config["PDF_STORAGE_ROOT"] = str(tmp_path)
    sid = _seed_submittal(app)
    # A complete review already exists for the first attachment (5001).
    with app.app_context():
        db.session.add(BBDrawingReview(
            submittal_id=sid, attachment_id=5001, status="complete",
            findings=VIOLATION_FINDINGS, model="test",
        ))
        db.session.commit()

    with patch("app.brain.pdf_review.routes.find_submittal_drawing_refs", return_value=REFS):
        resp = admin_client.get(_docs_url(sid))
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["submittal"]["phase"] == "FC"
    assert body["submittal"]["rel"] == 674
    assert "companies/18521" in body["submittal"]["procore_url"]

    docs = {d["attachment_id"]: d for d in body["documents"]}
    assert set(docs) == {5001, 5002}
    assert docs[5001]["source"] == "originating"
    assert docs[5001]["downloaded"] is False  # nothing cached on disk
    assert docs[5001]["review"]["tally"]["critical"] == 1
    assert docs[5001]["review"]["hold_recommended"] is True
    assert docs[5002]["review"] is None  # no review for the approver markup


def test_bb_review_enqueues_pending_row_and_backgrounds(app, admin_client, tmp_path):
    """POST returns 202 with a pending submittal-keyed row and hands the (multi-minute)
    Claude call to the background worker — it never runs inline (that tripped the gunicorn
    worker timeout in prod). The endpoint still pulls + caches the drawing synchronously."""
    app.config["PDF_STORAGE_ROOT"] = str(tmp_path)
    sid = _seed_submittal(app)

    with patch("app.brain.pdf_review.routes.find_submittal_drawing_refs", return_value=REFS), \
         patch("app.brain.pdf_review.routes.download_markup_pdf", return_value=b"%PDF-1.7 fake"), \
         patch("app.brain.pdf_review.routes.start_submittal_review") as mock_start, \
         patch("app.brain.pdf_review.service.review") as mock_review:
        resp = admin_client.post(
            f"/brain/procore-submittals/{sid}/documents/5001/bb-review?model=sonnet")
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["ok"] is True
    assert body["status"] == "pending"
    # The review call is NOT made inline — the worker makes it off-request.
    mock_review.assert_not_called()
    mock_start.assert_called_once()

    with app.app_context():
        rows = BBDrawingReview.query.filter_by(submittal_id=sid, attachment_id=5001).all()
        assert len(rows) == 1
        assert rows[0].status == "pending"
        assert rows[0].id == body["review_id"]


def test_bb_review_returns_existing_pending_row(app, admin_client, tmp_path):
    """A second POST while a review is running returns the existing pending row (202)
    instead of stacking a second Claude call (mirrors the per-version dedup gate)."""
    from app.brain.pdf_review import cache as procore_pdf_cache

    app.config["PDF_STORAGE_ROOT"] = str(tmp_path)
    sid = _seed_submittal(app)
    with app.app_context():
        pending = BBDrawingReview(submittal_id=sid, attachment_id=5001, status="pending")
        db.session.add(pending)
        db.session.commit()
        pending_id = pending.id
        procore_pdf_cache.save(sid, 5001, b"%PDF-1.7 fake")

    with patch("app.brain.pdf_review.routes.start_submittal_review") as mock_start:
        resp = admin_client.post(
            f"/brain/procore-submittals/{sid}/documents/5001/bb-review?review_only=true")
    assert resp.status_code == 202
    assert resp.get_json()["review_id"] == pending_id
    mock_start.assert_not_called()

    with app.app_context():
        assert BBDrawingReview.query.filter_by(submittal_id=sid, attachment_id=5001).count() == 1


def test_worker_completes_submittal_review(app, admin_client, tmp_path):
    """The background job reads the cached drawing, runs the review, and flips the row to
    complete with findings + token usage."""
    from app.brain.pdf_review import cache as procore_pdf_cache
    from app.brain.pdf_review.worker import _run_submittal_review_job

    app.config["PDF_STORAGE_ROOT"] = str(tmp_path)
    sid = _seed_submittal(app)
    with app.app_context():
        review = BBDrawingReview(submittal_id=sid, attachment_id=5001, status="pending")
        db.session.add(review)
        db.session.commit()
        review_id = review.id
        procore_pdf_cache.save(sid, 5001, b"%PDF-1.7 fake")

    with patch("app.brain.pdf_review.service.review", return_value={
            "findings": VIOLATION_FINDINGS, "model": "claude-test",
            "input_tokens": 10, "output_tokens": 20,
    }) as mock_review:
        _run_submittal_review_job(app, review_id, sid, 5001, "590-674", "sonnet")
    mock_review.assert_called_once()

    with app.app_context():
        r = db.session.get(BBDrawingReview, review_id)
        assert r.status == "complete"
        assert r.release_id is None
        assert r.drawing_version_id is None
        assert r.model == "claude-test"
        assert r.input_tokens == 10 and r.output_tokens == 20


def test_worker_records_error_when_review_fails(app, tmp_path):
    """A None result (no key / API error) flips the pending row to error, not a crash."""
    from app.brain.pdf_review import cache as procore_pdf_cache
    from app.brain.pdf_review.worker import _run_submittal_review_job

    app.config["PDF_STORAGE_ROOT"] = str(tmp_path)
    sid = _seed_submittal(app)
    with app.app_context():
        review = BBDrawingReview(submittal_id=sid, attachment_id=5001, status="pending")
        db.session.add(review)
        db.session.commit()
        review_id = review.id
        procore_pdf_cache.save(sid, 5001, b"%PDF-1.7 fake")

    with patch("app.brain.pdf_review.service.review", return_value=None):
        _run_submittal_review_job(app, review_id, sid, 5001, "590-674", None)

    with app.app_context():
        r = db.session.get(BBDrawingReview, review_id)
        assert r is not None and r.status == "error"


def test_review_only_409_when_not_cached(app, admin_client, tmp_path):
    app.config["PDF_STORAGE_ROOT"] = str(tmp_path)
    sid = _seed_submittal(app)
    resp = admin_client.post(
        f"/brain/procore-submittals/{sid}/documents/5001/bb-review?review_only=true")
    assert resp.status_code == 409


def test_get_review_and_feedback_roundtrip(app, admin_client, tmp_path):
    app.config["PDF_STORAGE_ROOT"] = str(tmp_path)
    sid = _seed_submittal(app)
    with app.app_context():
        review = BBDrawingReview(
            submittal_id=sid, attachment_id=5001, status="complete",
            findings=VIOLATION_FINDINGS, model="test",
        )
        db.session.add(review)
        db.session.commit()
        review_id = review.id

    # Save feedback on finding 0 (submittal-keyed; release/version stay null).
    fb_url = (f"/brain/procore-submittals/{sid}/documents/5001/bb-review/"
              f"{review_id}/feedback")
    resp = admin_client.post(fb_url, json={
        "finding_index": 0, "decision": "accepted", "notes": "BB right, rise is 8\"",
        "rule_id": "stair-terminal-rise-over-max", "finding": VIOLATION_FINDINGS[0],
    })
    assert resp.status_code == 200

    with app.app_context():
        rows = BBReviewFeedback.query.filter_by(review_id=review_id).all()
        assert len(rows) == 1
        assert rows[0].submittal_id == sid
        assert rows[0].attachment_id == 5001
        assert rows[0].release_id is None

    # GET the review carries the tally + feedback keyed by finding_index.
    resp = admin_client.get(f"/brain/procore-submittals/{sid}/documents/5001/bb-review")
    assert resp.status_code == 200
    review_payload = resp.get_json()["review"]
    assert review_payload["review_id"] == review_id
    assert review_payload["tally"]["critical"] == 1
    assert review_payload["feedback"]["0"]["decision"] == "accepted"


def test_documents_404_for_unknown_submittal(app, admin_client):
    resp = admin_client.get(_docs_url("does-not-exist"))
    assert resp.status_code == 404
