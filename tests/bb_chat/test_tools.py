"""The read-only tools: ball-in-court submittal search, to-dos by owner, lifecycle."""
from datetime import date

from app.brain.bb_chat import tools
from app.models import ChecklistItem, Meeting, Submittals, db

from tests.conftest import make_release, make_user


def _submittal(sid, project_number, **extra):
    s = Submittals(submittal_id=sid, project_number=project_number,
                   submittal_drafting_status="", **extra)
    db.session.add(s)
    db.session.flush()
    return s


def test_search_submittals_by_ball_in_court(app):
    with app.app_context():
        _submittal("S1", "290", ball_in_court="Colton Reyes", status="Open", title="A")
        _submittal("S2", "291", ball_in_court="Daniel M, Colton Reyes", status="Open", title="B")
        _submittal("S3", "292", ball_in_court="Katie H", status="Open", title="C")

        out = tools.search_submittals(ball_in_court="Colton")
        ids = {r["submittal_id"] for r in out["results"]}
        assert ids == {"S1", "S2"}          # matches the comma-separated multi-assignee field
        assert out["result_count"] == 2


def test_search_submittals_requires_a_filter(app):
    with app.app_context():
        out = tools.search_submittals()
        assert "error" in out


def test_search_submittals_urgent_only(app):
    with app.app_context():
        _submittal("U1", "290", ball_in_court="Colton", order_number=0.2, title="urgent")
        _submittal("U2", "290", ball_in_court="Colton", order_number=5.0, title="not urgent")
        out = tools.search_submittals(ball_in_court="Colton", urgent_only=True)
        assert [r["submittal_id"] for r in out["results"]] == ["U1"]


def test_search_todos_by_owner(app):
    with app.app_context():
        colton = make_user("colton@mhmw.com", first_name="Colton", last_name="Reyes")
        r = make_release(290, "153")
        m = Meeting(title="Standup")
        db.session.add(m)
        db.session.flush()
        db.session.add(ChecklistItem(meeting_id=m.id, release_id=r.id, owner_user_id=colton.id,
                                     title="Order steel", status="accepted", item_type="action"))
        db.session.add(ChecklistItem(meeting_id=m.id, owner_user_id=colton.id,
                                     title="Rejected item", status="rejected", item_type="action"))
        db.session.flush()

        out = tools.search_todos(owner="Colton")
        titles = [t["title"] for t in out["results"]]
        assert "Order steel" in titles          # accepted, owned by Colton
        assert "Rejected item" not in titles     # rejected excluded
        assert out["results"][0]["owner"] == "Colton"
        assert out["results"][0]["job_release"] == "290-153"


def test_search_todos_unknown_owner(app):
    with app.app_context():
        out = tools.search_todos(owner="Nobody")
        assert out["result_count"] == 0 and "note" in out


def test_get_release_lifecycle_wraps_assembler(app):
    with app.app_context():
        make_release(290, "153", stage="Cut Start", job_name="Acme")
        _submittal("S1", "290", ball_in_court="Colton", status="Open", title="sub")
        out = tools.get_release_lifecycle(290, "153")
        assert out["found"] is True
        assert out["counts"]["releases"] == 1
        assert out["releases"][0]["job_release"] == "290-153"


def test_execute_tool_dispatch_and_unknown(app):
    with app.app_context():
        _submittal("S1", "290", ball_in_court="Colton", status="Open", title="x")
        ok = tools.execute_tool("search_submittals", {"ball_in_court": "Colton"})
        assert ok["result_count"] == 1
        assert "error" in tools.execute_tool("does_not_exist", {})
