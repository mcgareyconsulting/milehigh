"""The assembler builds a deterministic lifecycle bundle from real rows + events + to-dos."""
from datetime import datetime

from app.brain.bb_chat import assembler
from app.models import (
    ChecklistItem,
    MaterialOrder,
    Meeting,
    ReleaseEvents,
    Submittals,
    SubmittalEvents,
    db,
)

from tests.conftest import make_release


def _seed_lifecycle():
    r = make_release(290, "153", stage="Cut Start", stage_group="FABRICATION", job_name="Acme Tower")
    s = Submittals(submittal_id="SUB-1234", project_number="290", title="Anchor bolts",
                   type="Submittal for GC Approval", status="Open", ball_in_court="GC",
                   submittal_drafting_status="", order_number=1.0)
    db.session.add(s)
    db.session.add(ReleaseEvents(
        job=290, release="153", action="update_stage",
        payload={"field": "stage", "old_value": "Released", "new_value": "Cut Start"},
        payload_hash="h1", source="Brain", created_at=datetime(2026, 6, 1, 9, 0)))
    db.session.add(SubmittalEvents(
        submittal_id="SUB-1234", action="updated",
        payload={"status": {"old": "Draft", "new": "Open"},
                 "ball_in_court": {"old": "MHMW", "new": "GC"}},
        payload_hash="h2", source="Procore", created_at=datetime(2026, 6, 2, 9, 0)))
    m = Meeting(title="Weekly standup")
    db.session.add(m)
    db.session.flush()
    db.session.add(ChecklistItem(
        meeting_id=m.id, release_id=r.id, title="Order the steel",
        status="accepted", item_type="action"))
    db.session.flush()
    return r, s


def test_assembles_release_bundle(app):
    with app.app_context():
        _seed_lifecycle()
        bundle = assembler.assemble({"kind": "release", "job": 290, "release": "153",
                                     "submittal_id": None, "label": "release 290-153"})

        assert bundle["found"] is True
        assert bundle["counts"]["releases"] == 1
        assert bundle["counts"]["submittals"] == 1
        assert bundle["counts"]["events"] == 2
        assert bundle["counts"]["todos"] == 1

        # Release view carries the key lifecycle fields.
        rel = bundle["releases"][0]
        assert rel["job_release"] == "290-153"
        assert rel["stage"] == "Cut Start"

        # Timeline is merged across both streams and chronological (release event first).
        tl = bundle["timeline"]
        assert [e["kind"] for e in tl] == ["release", "submittal"]
        assert "Released → Cut Start" in tl[0]["change"]
        assert "ball_in_court: MHMW → GC" in tl[1]["change"]

        # To-do surfaced from the linked meeting item.
        assert bundle["todos"][0]["title"] == "Order the steel"


def test_material_orders_surface_in_bundle(app):
    with app.app_context():
        _seed_lifecycle()
        db.session.add(MaterialOrder(
            job=290, release="153", supplier="Drexel Supply", po_number="290-153",
            order_kind="material", event_type="placed", description="1.5C 18Ga Decking",
            quantity=45.0, status="ordered", line_index=0))
        db.session.commit()

        bundle = assembler.assemble({"kind": "release", "job": 290, "release": "153",
                                     "submittal_id": None, "label": "release 290-153"})

        assert bundle["counts"]["material_orders"] == 1
        mo = bundle["material_orders"][0]
        assert mo["supplier"] == "Drexel Supply"
        assert mo["done"] is False
        # Outstanding order, no past hard install date → pending rollup.
        assert bundle["material_order_status"]["153"] == "pending"


def test_submittal_anchor_pulls_job_context(app):
    with app.app_context():
        _seed_lifecycle()
        bundle = assembler.assemble({"kind": "submittal", "job": None,
                                     "release": None, "submittal_id": "SUB-1234",
                                     "label": "submittal SUB-1234"})
        # Named submittal plus the job's release for context.
        assert bundle["counts"]["submittals"] == 1
        assert bundle["counts"]["releases"] == 1
        assert bundle["found"] is True


def test_unknown_anchor_is_empty(app):
    with app.app_context():
        bundle = assembler.assemble({"kind": "release", "job": 999, "release": "999",
                                     "submittal_id": None, "label": "release 999-999"})
        assert bundle["found"] is False
        assert bundle["counts"]["releases"] == 0
