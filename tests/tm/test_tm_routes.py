"""HTTP tests for T&M ticket ingestion routes (app/brain/tm/routes.py).

Integration layer: real test_client + in-memory DB. The extraction call
(service.tm_extract.extract) is patched so no network call is made.
"""
import io
from unittest.mock import patch

import pytest

from app.models import RawSourceRecord, TMTicket, db
from tests.conftest import make_release

PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\nfake pdf content\n%%EOF\n"

CANNED_EXTRACTION = {
    "job": 580,
    "date_of_work": "2026-06-18",
    "customer": "Alta Metro",
    "work_description": "Installed misc railings",
    "labor": [{"name": "Joe Smith", "company": "MHMW", "classification": "Welder",
               "hours_reg": 8.0, "hours_ot": 2.0, "hours_dt": None, "notes": None}],
    "materials": [{"description": "1.5C 18Ga decking", "quantity": 45.0, "unit": "sheets",
                   "length": "10ft", "notes": None}],
    "equipment": [{"description": "Man lift", "quantity": 1.0, "hours": 4.5,
                   "operator": "Joe Smith", "notes": None}],
    "signature_present": True,
    "signature_name": "John Doe",
    "confidence": {"job_number": 1.0},
    "raw": {"job_number": 580, "customer": "Alta Metro"},
}


def _upload(client, data=PDF_BYTES, filename="ticket.pdf", mimetype="application/pdf"):
    payload = {}
    if data is not None:
        payload["file"] = (io.BytesIO(data), filename, mimetype)
    return client.post("/brain/tm-tickets", data=payload, content_type="multipart/form-data")


def _patched_extract(return_value=None, side_effect=None):
    if side_effect is not None:
        return patch("app.brain.tm.service.tm_extract.extract", side_effect=side_effect)
    return patch("app.brain.tm.service.tm_extract.extract", return_value=return_value)


# ---------------------------------------------------------------------------
# Upload — happy path
# ---------------------------------------------------------------------------


def test_upload_happy_path_creates_ticket(app, admin_client):
    make_release(job=580, release="659", job_name="Alta Metro Job")
    db.session.commit()

    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp = _upload(admin_client)

    assert resp.status_code == 201
    body = resp.get_json()
    ticket = body["ticket"]
    assert ticket["status"] == "pending_review"
    assert ticket["job"] == 580
    assert ticket["date_of_work"] == "2026-06-18"
    assert ticket["customer"] == "Alta Metro"
    assert ticket["work_description"] == "Installed misc railings"
    assert ticket["labor"] == CANNED_EXTRACTION["labor"]
    assert ticket["materials"] == CANNED_EXTRACTION["materials"]
    assert ticket["equipment"] == CANNED_EXTRACTION["equipment"]
    assert ticket["signature_present"] is True
    assert ticket["signature_name"] == "John Doe"
    assert ticket["raw_extraction"] == CANNED_EXTRACTION["raw"]
    assert ticket["extract_error"] is None

    row = db.session.get(TMTicket, ticket["id"])
    assert row is not None
    assert row.status == "pending_review"

    records = RawSourceRecord.query.all()
    assert len(records) == 1
    assert records[0].source == "upload"
    assert records[0].record_type == "tm_ticket_scan"

    candidates = body["release_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["job"] == 580
    assert candidates[0]["release"] == "659"


def test_upload_extraction_failure_still_creates_ticket(app, admin_client):
    with _patched_extract(side_effect=RuntimeError("boom")):
        resp = _upload(admin_client)

    assert resp.status_code == 201
    ticket = resp.get_json()["ticket"]
    assert ticket["extract_error"] == "boom"
    assert ticket["job"] is None
    assert ticket["customer"] is None
    assert ticket["labor"] == []
    assert ticket["materials"] == []
    assert ticket["equipment"] == []

    row = db.session.get(TMTicket, ticket["id"])
    assert row.status == "pending_review"


def test_upload_same_bytes_twice_creates_two_tickets_one_raw_source_record(app, admin_client):
    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp1 = _upload(admin_client)
        resp2 = _upload(admin_client)

    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.get_json()["ticket"]["id"] != resp2.get_json()["ticket"]["id"]
    assert TMTicket.query.count() == 2
    assert RawSourceRecord.query.count() == 1


def test_upload_unsupported_mimetype_returns_400(app, admin_client):
    resp = _upload(admin_client, data=b"plain text", filename="notes.txt", mimetype="text/plain")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_upload_missing_file_returns_400(app, admin_client):
    resp = _upload(admin_client, data=None)
    assert resp.status_code == 400


def test_upload_empty_file_returns_400(app, admin_client):
    resp = _upload(admin_client, data=b"")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# List / detail / file
# ---------------------------------------------------------------------------


def test_list_tm_tickets(app, admin_client):
    with _patched_extract(return_value=CANNED_EXTRACTION):
        _upload(admin_client)
    with _patched_extract(side_effect=RuntimeError("boom")):
        _upload(admin_client, data=PDF_BYTES + b"more", filename="t2.pdf")

    resp = admin_client.get("/brain/tm-tickets")
    assert resp.status_code == 200
    tickets = resp.get_json()["tickets"]
    assert len(tickets) == 2


def test_list_tm_tickets_filtered_by_status(app, admin_client):
    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp = _upload(admin_client)
    ticket_id = resp.get_json()["ticket"]["id"]

    with _patched_extract(side_effect=RuntimeError("boom")):
        _upload(admin_client, data=PDF_BYTES + b"more", filename="t2.pdf")

    resp = admin_client.get("/brain/tm-tickets?status=pending_review")
    tickets = resp.get_json()["tickets"]
    assert len(tickets) == 2

    admin_client.post(f"/brain/tm-tickets/{ticket_id}/reject")
    resp = admin_client.get("/brain/tm-tickets?status=rejected")
    tickets = resp.get_json()["tickets"]
    assert len(tickets) == 1
    assert tickets[0]["id"] == ticket_id


def test_get_tm_ticket_detail_includes_release_candidates(app, admin_client):
    make_release(job=580, release="659")
    db.session.commit()

    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp = _upload(admin_client)
    ticket_id = resp.get_json()["ticket"]["id"]

    resp = admin_client.get(f"/brain/tm-tickets/{ticket_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ticket"]["id"] == ticket_id
    assert len(body["release_candidates"]) == 1


def test_get_tm_ticket_detail_404_for_missing(app, admin_client):
    resp = admin_client.get("/brain/tm-tickets/999999")
    assert resp.status_code == 404


def test_get_tm_ticket_file_returns_original_bytes(app, admin_client):
    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp = _upload(admin_client)
    ticket_id = resp.get_json()["ticket"]["id"]

    resp = admin_client.get(f"/brain/tm-tickets/{ticket_id}/file")
    assert resp.status_code == 200
    assert resp.data == PDF_BYTES
    assert resp.mimetype == "application/pdf"


def test_get_tm_ticket_file_404_for_missing_ticket(app, admin_client):
    resp = admin_client.get("/brain/tm-tickets/999999/file")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Release candidates picker
# ---------------------------------------------------------------------------


def test_release_candidates_only_active_non_archived_matching_job(app, admin_client):
    matching = make_release(job=580, release="659")
    make_release(job=580, release="998", is_archived=True)
    make_release(job=581, release="100")
    db.session.commit()

    resp = admin_client.get("/brain/tm-tickets/release-candidates?job=580")
    assert resp.status_code == 200
    candidates = resp.get_json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["id"] == matching.id


# ---------------------------------------------------------------------------
# Confirm / reject
# ---------------------------------------------------------------------------


def test_confirm_with_edited_fields_and_release_id(app, admin_client):
    release = make_release(job=580, release="659")
    db.session.commit()

    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp = _upload(admin_client)
    ticket_id = resp.get_json()["ticket"]["id"]

    resp = admin_client.post(
        f"/brain/tm-tickets/{ticket_id}/confirm",
        json={
            "release_id": release.id,
            "customer": "Corrected Customer",
            "date_of_work": "2026-06-19",
        },
    )
    assert resp.status_code == 200
    ticket = resp.get_json()["ticket"]
    assert ticket["status"] == "confirmed"
    assert ticket["customer"] == "Corrected Customer"
    assert ticket["date_of_work"] == "2026-06-19"
    assert ticket["reviewed_by"] == "test_admin"
    assert ticket["release_id"] == release.id
    assert ticket["release"]["id"] == release.id


def test_confirm_with_unknown_release_id_returns_400(app, admin_client):
    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp = _upload(admin_client)
    ticket_id = resp.get_json()["ticket"]["id"]

    resp = admin_client.post(
        f"/brain/tm-tickets/{ticket_id}/confirm",
        json={"release_id": 999999},
    )
    assert resp.status_code == 400


def test_confirm_on_rejected_ticket_returns_400(app, admin_client):
    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp = _upload(admin_client)
    ticket_id = resp.get_json()["ticket"]["id"]

    admin_client.post(f"/brain/tm-tickets/{ticket_id}/reject")
    resp = admin_client.post(f"/brain/tm-tickets/{ticket_id}/confirm", json={"customer": "X"})
    assert resp.status_code == 400


def test_confirm_with_bad_date_string_returns_400(app, admin_client):
    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp = _upload(admin_client)
    ticket_id = resp.get_json()["ticket"]["id"]

    resp = admin_client.post(
        f"/brain/tm-tickets/{ticket_id}/confirm",
        json={"date_of_work": "06/19/2026"},
    )
    assert resp.status_code == 400


def test_reject_keeps_row_never_deletes(app, admin_client):
    with _patched_extract(return_value=CANNED_EXTRACTION):
        resp = _upload(admin_client)
    ticket_id = resp.get_json()["ticket"]["id"]

    resp = admin_client.post(f"/brain/tm-tickets/{ticket_id}/reject")
    assert resp.status_code == 200
    assert resp.get_json()["ticket"]["status"] == "rejected"

    row = db.session.get(TMTicket, ticket_id)
    assert row is not None
    assert row.status == "rejected"


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_non_admin_cannot_upload(app, non_admin_client):
    resp = _upload(non_admin_client)
    assert resp.status_code == 403


def test_non_admin_cannot_confirm(app, non_admin_client):
    # Create the ticket directly through the service layer so the fixture setup
    # doesn't need a second, conflicting auth patch active in the same test
    # (admin_client and non_admin_client both patch the same get_current_user
    # targets, so only one can be "active" at a time).
    from app.brain.tm import service
    with _patched_extract(return_value=CANNED_EXTRACTION):
        ticket = service.create_from_upload(PDF_BYTES, "application/pdf", "ticket.pdf", "test_admin")
    db.session.commit()

    resp = non_admin_client.post(f"/brain/tm-tickets/{ticket.id}/confirm", json={})
    assert resp.status_code == 403


def test_non_admin_cannot_reject(app, non_admin_client):
    from app.brain.tm import service
    with _patched_extract(return_value=CANNED_EXTRACTION):
        ticket = service.create_from_upload(PDF_BYTES, "application/pdf", "ticket.pdf", "test_admin")
    db.session.commit()

    resp = non_admin_client.post(f"/brain/tm-tickets/{ticket.id}/reject")
    assert resp.status_code == 403


def test_non_admin_can_list(app, non_admin_client):
    resp = non_admin_client.get("/brain/tm-tickets")
    assert resp.status_code == 200
