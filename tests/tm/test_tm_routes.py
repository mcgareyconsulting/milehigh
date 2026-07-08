"""HTTP tests for native T&M ticket routes (app/brain/tm/routes.py).

Integration layer: real test_client + in-memory DB. The native creation path does
no external calls, so nothing is patched. (The parked vision extractor is covered
by tests/tm/test_tm_extract.py.)
"""
from app.models import TMTicket, db
from tests.conftest import make_release

TICKET_BODY = {
    "job": 580,
    "date_of_work": "2026-06-18",
    "customer": "Alta Metro",
    "location": "Level 3 stair core",
    "gc_company": "Alta Construction",
    "gc_contact_name": "Jane Roe",
    "foreman_name": "Joe Smith",
    "work_description": "Installed misc railings",
    "labor": [{"name": "Joe Smith", "company": "MHMW", "classification": "Welder",
               "hours_reg": 8.0, "hours_ot": 2.0, "hours_dt": None, "notes": None}],
    "materials": [{"description": "1.5C 18Ga decking", "quantity": 45.0, "unit": "sheets",
                   "length": "10ft", "notes": None}],
    "equipment": [{"description": "Man lift", "quantity": 1.0, "hours": 4.5,
                   "operator": "Joe Smith", "notes": None}],
    "signature_present": False,
    "signature_name": None,
}


def _create(client, body=None):
    return client.post("/brain/tm-tickets", json=body if body is not None else TICKET_BODY)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_happy_path_makes_draft(app, admin_client):
    make_release(job=580, release="659", job_name="Alta Metro Job")
    db.session.commit()

    resp = _create(admin_client)
    assert resp.status_code == 201
    body = resp.get_json()
    ticket = body["ticket"]
    assert ticket["status"] == "draft"
    assert ticket["job"] == 580
    assert ticket["date_of_work"] == "2026-06-18"
    assert ticket["customer"] == "Alta Metro"
    assert ticket["location"] == "Level 3 stair core"
    assert ticket["gc_company"] == "Alta Construction"
    assert ticket["gc_contact_name"] == "Jane Roe"
    assert ticket["foreman_name"] == "Joe Smith"
    assert ticket["work_description"] == "Installed misc railings"
    assert ticket["labor"] == TICKET_BODY["labor"]
    assert ticket["materials"] == TICKET_BODY["materials"]
    assert ticket["equipment"] == TICKET_BODY["equipment"]
    assert ticket["created_by"] == "test_admin"

    row = db.session.get(TMTicket, ticket["id"])
    assert row is not None
    assert row.status == "draft"

    candidates = body["release_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["job"] == 580
    assert candidates[0]["release"] == "659"


def test_create_empty_body_makes_blank_draft(app, admin_client):
    resp = _create(admin_client, body={})
    assert resp.status_code == 201
    ticket = resp.get_json()["ticket"]
    assert ticket["status"] == "draft"
    assert ticket["job"] is None
    assert ticket["labor"] == []


def test_create_with_release_id_links_release(app, admin_client):
    release = make_release(job=580, release="659")
    db.session.commit()

    resp = _create(admin_client, body={**TICKET_BODY, "release_id": release.id})
    assert resp.status_code == 201
    ticket = resp.get_json()["ticket"]
    assert ticket["release_id"] == release.id
    assert ticket["release"]["id"] == release.id


def test_create_with_unknown_release_id_returns_400(app, admin_client):
    resp = _create(admin_client, body={**TICKET_BODY, "release_id": 999999})
    assert resp.status_code == 400
    assert TMTicket.query.count() == 0


def test_create_with_bad_date_returns_400(app, admin_client):
    resp = _create(admin_client, body={"date_of_work": "06/18/2026"})
    assert resp.status_code == 400
    assert TMTicket.query.count() == 0


def test_create_with_bad_job_returns_400(app, admin_client):
    resp = _create(admin_client, body={"job": "not-a-number"})
    assert resp.status_code == 400


def test_create_with_non_list_labor_returns_400(app, admin_client):
    resp = _create(admin_client, body={"labor": "eight hours"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# List / detail
# ---------------------------------------------------------------------------


def test_list_tm_tickets(app, admin_client):
    _create(admin_client)
    _create(admin_client, body={"customer": "Second"})

    resp = admin_client.get("/brain/tm-tickets")
    assert resp.status_code == 200
    assert len(resp.get_json()["tickets"]) == 2


def test_list_tm_tickets_filtered_by_status(app, admin_client):
    resp = _create(admin_client)
    ticket_id = resp.get_json()["ticket"]["id"]
    _create(admin_client, body={"customer": "Second"})

    resp = admin_client.get("/brain/tm-tickets?status=draft")
    assert len(resp.get_json()["tickets"]) == 2

    admin_client.post(f"/brain/tm-tickets/{ticket_id}/void")
    resp = admin_client.get("/brain/tm-tickets?status=void")
    tickets = resp.get_json()["tickets"]
    assert len(tickets) == 1
    assert tickets[0]["id"] == ticket_id


def test_get_tm_ticket_detail_includes_release_candidates(app, admin_client):
    make_release(job=580, release="659")
    db.session.commit()

    ticket_id = _create(admin_client).get_json()["ticket"]["id"]
    resp = admin_client.get(f"/brain/tm-tickets/{ticket_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ticket"]["id"] == ticket_id
    assert len(body["release_candidates"]) == 1


def test_get_tm_ticket_detail_404_for_missing(app, admin_client):
    resp = admin_client.get("/brain/tm-tickets/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update (draft-only)
# ---------------------------------------------------------------------------


def test_update_draft_applies_edits(app, admin_client):
    release = make_release(job=580, release="659")
    db.session.commit()
    ticket_id = _create(admin_client).get_json()["ticket"]["id"]

    resp = admin_client.put(
        f"/brain/tm-tickets/{ticket_id}",
        json={"customer": "Corrected Customer", "date_of_work": "2026-06-19",
              "release_id": release.id},
    )
    assert resp.status_code == 200
    ticket = resp.get_json()["ticket"]
    assert ticket["customer"] == "Corrected Customer"
    assert ticket["date_of_work"] == "2026-06-19"
    assert ticket["release_id"] == release.id


def test_update_voided_ticket_returns_400(app, admin_client):
    ticket_id = _create(admin_client).get_json()["ticket"]["id"]
    admin_client.post(f"/brain/tm-tickets/{ticket_id}/void")

    resp = admin_client.put(f"/brain/tm-tickets/{ticket_id}", json={"customer": "X"})
    assert resp.status_code == 400


def test_update_unknown_release_id_returns_400(app, admin_client):
    ticket_id = _create(admin_client).get_json()["ticket"]["id"]
    resp = admin_client.put(f"/brain/tm-tickets/{ticket_id}", json={"release_id": 999999})
    assert resp.status_code == 400


def test_update_missing_ticket_returns_404(app, admin_client):
    resp = admin_client.put("/brain/tm-tickets/999999", json={"customer": "X"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Void
# ---------------------------------------------------------------------------


def test_void_keeps_row_never_deletes(app, admin_client):
    ticket_id = _create(admin_client).get_json()["ticket"]["id"]

    resp = admin_client.post(f"/brain/tm-tickets/{ticket_id}/void")
    assert resp.status_code == 200
    assert resp.get_json()["ticket"]["status"] == "void"

    row = db.session.get(TMTicket, ticket_id)
    assert row is not None
    assert row.status == "void"
    assert row.reviewed_by == "test_admin"


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
# Permissions
# ---------------------------------------------------------------------------


def test_non_admin_cannot_create(app, non_admin_client):
    resp = _create(non_admin_client)
    assert resp.status_code == 403


def test_non_admin_cannot_update(app, non_admin_client):
    from app.brain.tm import service
    ticket, _ = service.create_ticket(dict(TICKET_BODY), "test_admin")
    db.session.commit()

    resp = non_admin_client.put(f"/brain/tm-tickets/{ticket.id}", json={"customer": "X"})
    assert resp.status_code == 403


def test_non_admin_cannot_void(app, non_admin_client):
    from app.brain.tm import service
    ticket, _ = service.create_ticket(dict(TICKET_BODY), "test_admin")
    db.session.commit()

    resp = non_admin_client.post(f"/brain/tm-tickets/{ticket.id}/void")
    assert resp.status_code == 403


def test_non_admin_can_list(app, non_admin_client):
    resp = non_admin_client.get("/brain/tm-tickets")
    assert resp.status_code == 200
