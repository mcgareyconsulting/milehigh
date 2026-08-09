"""The read-only tools: ball-in-court submittal search, to-dos by owner, lifecycle."""
from datetime import date, datetime
from unittest.mock import patch

from app.brain.carmen_chat import tools
from app.models import ChecklistItem, Meeting, ReleaseEvents, Submittals, TMTicket, db

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


def test_get_project_pipeline_and_lookahead_tools(app):
    with app.app_context():
        make_release(
            500, "615", stage="Weld Complete", job_name="Novel Flatiron",
            description="SE Canopy", fab_hrs=40.0, install_hrs=8.0, fab_order=4.0,
            start_install=date(2026, 8, 12), start_install_formulaTF=False,
            ship_date=date(2026, 8, 11), comp_eta=date(2026, 8, 13),
            is_active=True, is_archived=False,
            start_install_asap=False, start_install_no_color=False,
        )
        _submittal(
            "drr-500", "500", project_name="Novel Flatiron", title="Open DRR",
            status="Open", type="Drafting Release Review",
            rel=400, due_date=date(2026, 8, 5),
        )

        pipe = tools.execute_tool("get_project_pipeline", {"job": 500})
        assert pipe["found"] is True
        assert pipe["job"] == 500
        assert len(pipe["releases"]) == 1
        assert len(pipe["drafting"]) == 1

        schedule = tools.execute_tool(
            "build_project_lookahead",
            {"job": 500, "weeks": 3},
            context={"user_id": 1},
        )
        assert schedule["found"] is True
        assert schedule["audience"] == "gc"
        assert schedule["window"]["weeks"] == 3
        assert schedule["summary"]["release_count"] == 1
        assert schedule["summary"]["drafting_count"] == 1
        kinds = {r["kind"] for r in schedule["rows"]}
        assert "release" in kinds and "drafting" in kinds
        # PDF is on by default so the chat card can appear even if the model
        # only called build_project_lookahead (not render_*).
        assert schedule.get("pdf_included") is True
        assert schedule.get("download_path", "").startswith("/brain/lookahead/artifacts/")


def test_project_lookahead_tool_missing_job(app):
    with app.app_context():
        out = tools.execute_tool("build_project_lookahead", {"job": 99999})
        assert out["found"] is False


def test_build_project_lookahead_can_skip_pdf(app, tmp_path):
    with app.app_context():
        app.config["LOOKAHEAD_PDF_STORAGE_ROOT"] = str(tmp_path)
        make_release(
            500, "1", stage="Released", job_name="Novel Flatiron",
            description="X", fab_hrs=10.0, install_hrs=8.0, fab_order=3.0,
            start_install=date(2026, 8, 12), start_install_formulaTF=False,
            is_active=True, is_archived=False,
            start_install_asap=False, start_install_no_color=False,
        )
        out = tools.execute_tool(
            "build_project_lookahead",
            {"job": 500, "weeks": 3, "include_pdf": False},
            context={"user_id": 1},
        )
        assert out["found"] is True
        assert out.get("pdf_included") is False
        assert "download_path" not in out


def test_render_project_lookahead_pdf_tool(app, tmp_path):
    with app.app_context():
        app.config["LOOKAHEAD_PDF_STORAGE_ROOT"] = str(tmp_path)
        make_release(
            500, "615", stage="Weld Complete", job_name="Novel Flatiron",
            description="SE Canopy", fab_hrs=40.0, install_hrs=8.0, fab_order=4.0,
            start_install=date(2026, 8, 12), start_install_formulaTF=False,
            ship_date=date(2026, 8, 11), comp_eta=date(2026, 8, 13),
            is_active=True, is_archived=False,
            start_install_asap=False, start_install_no_color=False,
        )
        out = tools.execute_tool(
            "render_project_lookahead_pdf",
            {"job": 500, "weeks": 3},
            context={"user_id": 1},
        )
        assert out["found"] is True
        assert out["artifact_id"]
        assert out["download_path"].startswith("/brain/lookahead/artifacts/")
        assert out["page_size"] == "letter-landscape"
        # File actually on disk
        from app.brain.lookahead.artifacts import read_lookahead_pdf
        pdf = read_lookahead_pdf(out["artifact_id"])
        assert pdf[:4] == b"%PDF"


def test_mon_sun_week_bounds():
    # 2026-08-05 is a Wednesday → Mon Aug 3 – Sun Aug 9
    monday, sunday = tools.mon_sun_week_bounds(date(2026, 8, 5))
    assert monday == date(2026, 8, 3)
    assert sunday == date(2026, 8, 9)
    # Already Monday / Sunday stay in the same week
    assert tools.mon_sun_week_bounds(date(2026, 8, 3)) == (date(2026, 8, 3), date(2026, 8, 9))
    assert tools.mon_sun_week_bounds(date(2026, 8, 9)) == (date(2026, 8, 3), date(2026, 8, 9))


def test_hours_released_to_production_weekly_aggregate(app):
    """David's EOS metric: count releases + sum fab_hrs by released Mon–Sun week."""
    with app.app_context():
        # Week of Aug 3–9 2026
        make_release(410, "1", job_name="A", fab_hrs=100.0, released=date(2026, 8, 3),
                     is_active=True, is_archived=False)
        make_release(410, "2", job_name="A", fab_hrs=50.5, released=date(2026, 8, 7),
                     is_active=True, is_archived=False)
        # Zero / null fab_hrs still count as releases
        make_release(411, "1", job_name="B", fab_hrs=0.0, released=date(2026, 8, 5),
                     is_active=True, is_archived=False)
        make_release(412, "1", job_name="C", fab_hrs=None, released=date(2026, 8, 9),
                     is_active=True, is_archived=False)
        # Archived ignored for first fab-hours pass
        make_release(413, "1", job_name="D", fab_hrs=24.0, released=date(2026, 8, 4),
                     is_active=True, is_archived=True)
        # Outside week — excluded
        make_release(414, "1", job_name="E", fab_hrs=999.0, released=date(2026, 8, 2),
                     is_active=True, is_archived=False)
        make_release(415, "1", job_name="F", fab_hrs=999.0, released=date(2026, 8, 10),
                     is_active=True, is_archived=False)
        # Soft-deleted — excluded
        make_release(416, "1", job_name="G", fab_hrs=40.0, released=date(2026, 8, 6),
                     is_active=False, is_archived=False)
        # No released date — excluded
        make_release(417, "1", job_name="H", fab_hrs=40.0, released=None,
                     is_active=True, is_archived=False)

        out = tools.get_hours_released_to_production(week_of="2026-08-05")
        assert out["week"]["start"] == "2026-08-03"
        assert out["week"]["end"] == "2026-08-09"
        assert out["week"]["label"] == "Aug 3 – Aug 9"
        assert out["release_count"] == 4  # 410-1, 410-2, 411-1, 412-1 (not archived 413-1)
        assert out["total_fab_hrs"] == 150.5  # 100 + 50.5 + 0 + 0
        ids = {r["identifier"] for r in out["releases"]}
        assert ids == {"410-1", "410-2", "411-1", "412-1"}
        assert out["rules"]["includes_archived"] is False


def test_hours_released_weeks_back_and_dispatch(app):
    with app.app_context():
        make_release(500, "1", job_name="X", fab_hrs=40.0, released=date(2026, 7, 28),
                     is_active=True, is_archived=False)
        # Pin "today" so weeks_back=1 lands on Jul 27 – Aug 2
        with patch.object(tools.eos_metrics, "mountain_today", return_value=date(2026, 8, 5)):
            out = tools.execute_tool(
                "get_hours_released_to_production",
                {"weeks_back": 1},
            )
        assert out["week"]["start"] == "2026-07-27"
        assert out["week"]["end"] == "2026-08-02"
        assert out["release_count"] == 1
        assert out["total_fab_hrs"] == 40.0


def test_yellow_dates_bill(app):
    with app.app_context():
        # Past hard date → yellow
        make_release(
            1, "1", job_name="Y", released=date(2026, 7, 1),
            start_install=date(2026, 8, 1), start_install_formulaTF=False,
            start_install_asap=False, start_install_no_color=False,
            is_active=True, is_archived=False,
        )
        # Future hard date → not yellow
        make_release(
            1, "2", job_name="Y", released=date(2026, 7, 1),
            start_install=date(2026, 12, 1), start_install_formulaTF=False,
            start_install_asap=False, start_install_no_color=False,
            is_active=True, is_archived=False,
        )
        # Formula date → not yellow
        make_release(
            1, "3", job_name="Y", released=date(2026, 7, 1),
            start_install=date(2026, 8, 1), start_install_formulaTF=True,
            start_install_asap=False, start_install_no_color=False,
            is_active=True, is_archived=False,
        )
        with patch.object(tools.eos_metrics, "mountain_today", return_value=date(2026, 8, 5)):
            out = tools.execute_tool("get_eos_metric", {
                "metric": "yellow_dates", "week_of": "2026-08-05",
            })
        assert out["scorecard_owner"] == "Bill O'Neill"
        assert out["yellow_count"] == 1
        assert out["releases"][0]["identifier"] == "1-1"
        assert out["goal_met"] is False


def test_fabrication_hours_luis(app):
    with app.app_context():
        make_release(
            10, "1", job_name="Shop", fab_hrs=100.0, stage="Cut Start",
            is_active=True, is_archived=False,
        )
        # Released (100% remaining) → Cut Complete (90%) = 10 hrs completed
        db.session.add(ReleaseEvents(
            job=10, release="1", action="update_stage",
            payload={"from": "Released", "to": "Cut Complete"},
            payload_hash="eos-fab-test-1",
            source="Brain",
            created_at=datetime(2026, 8, 4, 18, 0, 0),  # UTC during Aug 3–9 MT
            is_system_echo=False,
        ))
        db.session.flush()
        out = tools.execute_tool("get_eos_metric", {
            "metric": "fabrication_hours", "week_of": "2026-08-05",
        })
        assert out["scorecard_owner"] == "Luis Solano"
        assert out["total_fab_hrs_completed"] == 10.0
        assert out["transitions_credited"] == 1


def test_tm_hours_doug(app):
    with app.app_context():
        db.session.add(TMTicket(
            status="submitted",
            job=200,
            date_of_work=date(2026, 8, 4),
            labor=[
                {"name": "A", "hours_reg": 8, "hours_ot": 2, "hours_dt": 0},
                {"name": "B", "hours_reg": 4, "hours_ot": 0, "hours_dt": 0},
            ],
        ))
        db.session.add(TMTicket(
            status="void",
            job=200,
            date_of_work=date(2026, 8, 4),
            labor=[{"hours_reg": 99}],
        ))
        db.session.flush()
        out = tools.execute_tool("get_eos_metric", {
            "metric": "tm_hours", "week_of": "2026-08-05",
        })
        assert out["scorecard_owner"] == "Doug Ferrin"
        assert out["ticket_count"] == 1
        assert out["total_tm_hours"] == 14.0


def test_eos_metrics_for_owner_david_and_session_user(app):
    with app.app_context():
        make_release(9, "9", job_name="Z", fab_hrs=20.0, released=date(2026, 8, 4),
                     is_active=True, is_archived=False)
        david = make_user("david@mhmw.com", first_name="David", last_name="Servold")
        out = tools.execute_tool(
            "get_eos_metrics_for_owner",
            {"owner": "David", "week_of": "2026-08-05"},
        )
        assert out["scorecard_owner"] == "David Servold"
        assert out["metric_ids"] == ["hours_released_to_production"]
        assert out["metrics"][0]["release_count"] == 1

        # Session user match when owner omitted
        mine = tools.execute_tool(
            "get_eos_metrics_for_owner",
            {"week_of": "2026-08-05"},
            context={"user_id": david.id},
        )
        assert mine["owner_key"] == "david"
        assert mine["metrics"][0]["total_fab_hrs"] == 20.0
