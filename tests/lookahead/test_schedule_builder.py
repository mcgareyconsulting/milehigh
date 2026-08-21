"""GC-facing multi-phase lookahead schedule builder (pure + DB convenience)."""
from datetime import date

from app.brain.lookahead.schedule_builder import (
    PAINT_BUSINESS_DAYS,
    PHASE_DRAFTING,
    PHASE_FABRICATION,
    PHASE_INSTALLATION,
    PHASE_PAINT,
    PHASE_SHIPPING,
    SOURCE_ESTIMATED,
    SOURCE_HARD,
    build_lookahead_schedule,
    build_project_lookahead,
)
from app.brain.lookahead.pipeline import get_project_pipeline
from app.models import Releases, Submittals, db
from app.trello.utils import CALENDAR_FIELD, CALENDAR_SHOP, calculate_business_days_before


TODAY = date(2026, 7, 25)


def _pipeline(**kw):
    base = {
        "found": True,
        "job": 500,
        "project_name": "Novel Flatiron",
        "releases": [],
        "drafting": [],
        "gc_approvals": [],
        "flags": [],
    }
    base.update(kw)
    return base


def _release_row(**kw):
    base = {
        "kind": "release",
        "release_id": 1,
        "job": 500,
        "release": "100",
        "code": "500-100",
        "project_name": "Novel Flatiron",
        "description": "Bld A Structural Steel",
        "stage": "Released",
        "stage_group": "FABRICATION",
        "is_complete": False,
        "fab_hrs": 80.0,
        "install_hrs": 16.0,
        "num_guys": 2.0,
        "fab_order": 10.0,
        "unqueued": False,
        "paint_color": None,
        "released": "2026-07-01",
        "start_install": "2026-08-10",
        "start_install_formulaTF": False,
        "start_install_asap": False,
        "start_install_no_color": False,
        "date_kind": "hard",
        "ship_date": None,
        "comp_eta": "2026-08-11",
        "installer": None,
        "pm": "Bill",
        "drafter": None,
        "job_comp": None,
        "invoiced": None,
        "notes": None,
    }
    base.update(kw)
    return base


def test_not_found_pipeline():
    out = build_lookahead_schedule(
        {"found": False, "job": 500, "project_name": None, "flags": []},
        weeks=3,
        today=TODAY,
    )
    assert out["found"] is False
    assert out["rows"] == []
    assert out["window"]["weeks"] == 3
    assert out["audience"] == "gc"


def test_hard_date_release_builds_full_cascade():
    """Hard install → estimated ship (−1bd) → 3-day paint → fab back-chain."""
    out = build_lookahead_schedule(
        _pipeline(releases=[_release_row()]),
        weeks=3,
        today=TODAY,
    )
    assert out["found"] is True
    assert out["job"] == 500
    assert out["summary"]["release_count"] == 1
    assert out["assumptions"]["paint_business_days"] == PAINT_BUSINESS_DAYS

    row = out["rows"][0]
    assert row["kind"] == "release"
    assert row["code"] == "500-100"
    assert row["stage_label"] == "In fabrication"

    by_phase = {p["phase"]: p for p in row["phases"]}
    assert PHASE_INSTALLATION in by_phase
    assert by_phase[PHASE_INSTALLATION]["start"] == "2026-08-10"
    assert by_phase[PHASE_INSTALLATION]["end"] == "2026-08-11"
    assert by_phase[PHASE_INSTALLATION]["date_source"] == SOURCE_HARD

    # Ship = 1 *field* business day before 2026-08-10 (Mon) → Fri 2026-08-07
    expected_ship = calculate_business_days_before(
        date(2026, 8, 10), 1, calendar=CALENDAR_FIELD
    )
    assert by_phase[PHASE_SHIPPING]["start"] == expected_ship.isoformat()
    assert by_phase[PHASE_SHIPPING]["date_source"] == SOURCE_ESTIMATED

    # Paint: 3 *shop* days (Mon–Thu) ending the shop day before ship
    paint_end = calculate_business_days_before(
        expected_ship, 1, calendar=CALENDAR_SHOP
    )
    paint_start = calculate_business_days_before(
        expected_ship, PAINT_BUSINESS_DAYS, calendar=CALENDAR_SHOP
    )
    assert by_phase[PHASE_PAINT]["start"] == paint_start.isoformat()
    assert by_phase[PHASE_PAINT]["end"] == paint_end.isoformat()
    assert by_phase[PHASE_PAINT]["date_source"] == SOURCE_ESTIMATED
    assert "provisional" in by_phase[PHASE_PAINT]["note"].lower()
    # Shop calendar never lands paint bars on Friday
    assert date.fromisoformat(by_phase[PHASE_PAINT]["start"]).weekday() < 4
    assert date.fromisoformat(by_phase[PHASE_PAINT]["end"]).weekday() < 4

    assert PHASE_FABRICATION in by_phase
    assert by_phase[PHASE_FABRICATION]["end"] <= by_phase[PHASE_PAINT]["start"]
    # Back-chained fab is estimated, never "projected from production schedule".
    assert by_phase[PHASE_FABRICATION]["date_source"] == SOURCE_ESTIMATED
    assert out["assumptions"]["shop_calendar"].startswith("Mon")


def test_hard_ship_date_used_when_present():
    out = build_lookahead_schedule(
        _pipeline(releases=[_release_row(
            ship_date="2026-08-06",
            start_install="2026-08-10",
            comp_eta="2026-08-12",
        )]),
        weeks=3,
        today=TODAY,
    )
    by_phase = {p["phase"]: p for p in out["rows"][0]["phases"]}
    assert by_phase[PHASE_SHIPPING]["start"] == "2026-08-06"
    assert by_phase[PHASE_SHIPPING]["date_source"] == SOURCE_HARD
    # Even with a hard ship, fab is back-chained → estimated.
    assert by_phase[PHASE_FABRICATION]["date_source"] == SOURCE_ESTIMATED


def test_missing_install_does_not_invent_cascade():
    """No stored install/ship → no optimistic queue-projected install or paint/ship."""
    out = build_lookahead_schedule(
        _pipeline(releases=[_release_row(
            start_install=None,
            comp_eta=None,
            ship_date=None,
            date_kind="missing",
            start_install_formulaTF=None,
            fab_hrs=200.0,
        )]),
        weeks=3,
        today=TODAY,
    )
    phases = {p["phase"] for p in out["rows"][0]["phases"]}
    assert PHASE_INSTALLATION not in phases
    assert PHASE_SHIPPING not in phases
    assert PHASE_PAINT not in phases
    assert PHASE_FABRICATION not in phases
    assert "missing_install_date" in out["rows"][0]["flags"]


def test_paint_complete_stage_omits_fab_and_paint():
    out = build_lookahead_schedule(
        _pipeline(releases=[_release_row(
            stage="Paint Complete",
            stage_group="READY_TO_SHIP",
            ship_date="2026-08-06",
            start_install="2026-08-10",
            start_install_formulaTF=False,
            date_kind="hard",
        )]),
        weeks=3,
        today=TODAY,
    )
    phases = {p["phase"] for p in out["rows"][0]["phases"]}
    assert PHASE_FABRICATION not in phases
    assert PHASE_PAINT not in phases
    assert PHASE_SHIPPING in phases
    assert PHASE_INSTALLATION in phases


def test_complete_release_lands_in_past_rows_not_the_look_ahead():
    """A release installed in June is history on a July look-ahead (BUG-12).

    It stays in the envelope for provenance, but out of ``rows`` — leaving it there
    is what made Carmen open a Novel Flatirons look-ahead with a May date.
    """
    out = build_lookahead_schedule(
        _pipeline(releases=[_release_row(
            release="50",
            code="500-50",
            description="Already installed embeds",
            stage="Complete",
            is_complete=True,
            start_install="2026-06-01",
            comp_eta="2026-06-03",
            date_kind="neutral",
            start_install_no_color=True,
            start_install_formulaTF=False,
        )]),
        weeks=3,
        today=TODAY,
    )
    assert out["summary"]["release_count"] == 1
    assert out["rows"] == []
    assert out["summary"]["row_count"] == 0
    assert out["summary"]["past_row_count"] == 1
    assert out["summary"]["next_activity"] is None

    row = out["past_rows"][0]
    assert row["stage_label"] == "Complete"
    assert row["is_complete"] is True
    assert row["next_activity"] is None
    assert all(p["status"] == "past" for p in row["phases"])


def test_active_bar_reports_next_date_not_its_start():
    """Work under way since before today reports when it *next* matters."""
    out = build_lookahead_schedule(
        _pipeline(releases=[_release_row(
            release="615",
            code="500-615",
            description="SE Canopy",
            stage="Released",
            released="2026-05-01",
            fab_hrs=1600.0,  # long enough that the fab bar opened before today
            start_install="2026-08-10",
            comp_eta="2026-08-11",
        )]),
        weeks=3,
        today=TODAY,
    )
    row = out["rows"][0]
    fab = next(p for p in row["phases"] if p["phase"] == PHASE_FABRICATION)
    assert fab["start"] < TODAY.isoformat()   # long fab bar opened before today
    assert fab["status"] == "active"

    nxt = row["next_activity"]
    assert nxt["phase"] == PHASE_FABRICATION
    assert nxt["label"] == "Fabrication"
    assert nxt["start"] == fab["start"]        # the real bar is not rewritten
    assert nxt["next_date"] == TODAY.isoformat()  # ...but the reported date is forward


def test_past_row_does_not_set_the_headline():
    """The job-level next_activity skips finished work and names the department."""
    done = _release_row(
        release="50",
        code="500-50",
        description="Installed in June",
        stage="Complete",
        is_complete=True,
        start_install="2026-06-01",
        comp_eta="2026-06-03",
        date_kind="neutral",
        start_install_no_color=True,
    )
    upcoming = _release_row(
        release="900",
        code="500-900",
        description="Next package",
        start_install="2026-09-14",
        comp_eta="2026-09-15",
    )
    out = build_lookahead_schedule(
        _pipeline(releases=[done, upcoming]),
        weeks=3,
        today=TODAY,
    )
    assert [r["code"] for r in out["rows"]] == ["500-900"]
    assert [r["code"] for r in out["past_rows"]] == ["500-50"]

    headline = out["summary"]["next_activity"]
    assert headline["code"] == "500-900"
    assert headline["label"] in ("Fabrication", "Paint", "Shipping", "Installation")
    assert headline["next_date"] >= TODAY.isoformat()
    assert out["window"]["today"] == TODAY.isoformat()


def test_undated_row_is_not_treated_as_past():
    """No bars at all means unscheduled, not finished — it must still reach the GC."""
    out = build_lookahead_schedule(
        _pipeline(releases=[_release_row(
            release="700",
            code="500-700",
            description="No install date yet",
            start_install=None,
            comp_eta=None,
            ship_date=None,
            date_kind="missing",
            stage="Paint Complete",  # nothing left to back-chain a bar from
        )]),
        weeks=3,
        today=TODAY,
    )
    assert [r["code"] for r in out["rows"]] == ["500-700"]
    assert out["past_rows"] == []
    row = out["rows"][0]
    assert row["phases"] == []
    assert row["next_activity"] is None
    assert "missing_install_date" in row["flags"]


def test_open_drr_drafting_bar():
    out = build_lookahead_schedule(
        _pipeline(drafting=[{
            "kind": "drafting",
            "submittal_id": "d1",
            "code": "500-DRR-300",
            "title": "Stair Core 3",
            "status": "Open",
            "rel": 300,
            "due_date": "2026-08-08",
            "start_install": "2026-08-20",
            "created_at": "2026-07-10",
        }]),
        weeks=3,
        today=TODAY,
    )
    assert out["summary"]["drafting_count"] == 1
    row = out["rows"][0]
    assert row["kind"] == "drafting"
    assert row["stage_label"] == "In drafting"
    by_phase = {p["phase"]: p for p in row["phases"]}
    assert by_phase[PHASE_DRAFTING]["end"] == "2026-08-08"
    assert by_phase[PHASE_DRAFTING]["date_source"] == SOURCE_HARD
    assert by_phase[PHASE_INSTALLATION]["start"] == "2026-08-20"
    assert "not yet released" in by_phase[PHASE_INSTALLATION]["note"].lower()


def test_old_drr_drafting_bar_is_clamped():
    """Multi-month open DRRs don't paint a year-long drafting bar on the Gantt."""
    out = build_lookahead_schedule(
        _pipeline(drafting=[{
            "kind": "drafting",
            "submittal_id": "d-old",
            "code": "500-DRR-50",
            "title": "Long-lived package",
            "status": "Open",
            "rel": 50,
            "due_date": "2026-08-15",
            "start_install": None,
            "created_at": "2025-01-01",
        }]),
        weeks=3,
        today=TODAY,
    )
    bar = out["rows"][0]["phases"][0]
    assert bar["phase"] == PHASE_DRAFTING
    assert bar["end"] == "2026-08-15"
    # Must start after the ancient created_at.
    assert bar["start"] > "2025-01-01"
    assert bar["start"] <= bar["end"]


def test_unscheduled_drafting_flag():
    out = build_lookahead_schedule(
        _pipeline(drafting=[{
            "kind": "drafting",
            "submittal_id": "d2",
            "code": "500-DRR-301",
            "title": "Mystery package",
            "status": "Open",
            "rel": 301,
            "due_date": None,
            "start_install": None,
            "created_at": "2026-07-01",
        }]),
        weeks=3,
        today=TODAY,
    )
    row = out["rows"][0]
    assert "unscheduled_drafting" in row["flags"]
    by_phase = {p["phase"]: p for p in row["phases"]}
    assert by_phase[PHASE_DRAFTING]["date_source"] == "missing"


def test_all_active_work_included_not_window_filtered():
    """Rows outside the 3-week window still appear (all active work)."""
    far = _release_row(
        release="900",
        code="500-900",
        description="Far-future package",
        start_install="2026-12-01",
        comp_eta="2026-12-03",
        date_kind="hard",
        start_install_formulaTF=False,
    )
    out = build_lookahead_schedule(
        _pipeline(releases=[far]),
        weeks=3,
        today=TODAY,
    )
    assert out["window"]["start"] == "2026-07-25"
    assert out["window"]["end"] == "2026-08-15"  # +21 days
    assert out["rows"][0]["code"] == "500-900"
    assert any(p["phase"] == PHASE_INSTALLATION for p in out["rows"][0]["phases"])
    # Beyond the window is still ahead of us — never filed as past.
    assert out["past_rows"] == []
    assert out["rows"][0]["next_activity"]["next_date"] > out["window"]["end"]


def test_build_project_lookahead_db(app):
    with app.app_context():
        db.session.add(Releases(
            job=500,
            release="615",
            job_name="Novel Flatiron",
            description="SE Canopy",
            stage="Weld Complete",
            stage_group="FABRICATION",
            fab_hrs=40.0,
            install_hrs=8.0,
            fab_order=4.0,
            start_install=date(2026, 8, 12),
            start_install_formulaTF=False,
            start_install_asap=False,
            start_install_no_color=False,
            ship_date=date(2026, 8, 11),
            comp_eta=date(2026, 8, 13),
            is_active=True,
            is_archived=False,
        ))
        db.session.add(Submittals(
            submittal_id="drr-500-1",
            project_number="500",
            project_name="Novel Flatiron",
            title="Open DRR package",
            status="Open",
            type="Drafting Release Review",
            submittal_drafting_status="STARTED",
            rel=400,
            due_date=date(2026, 8, 5),
        ))
        db.session.commit()

        out = build_project_lookahead(500, weeks=3, today=TODAY)
        assert out["found"] is True
        assert out["project_name"] == "Novel Flatiron"
        kinds = {r["kind"] for r in out["rows"]}
        assert "release" in kinds
        assert "drafting" in kinds
        assert out["summary"]["release_count"] == 1
        assert out["summary"]["drafting_count"] == 1
        assert out["legend"]["hard"] == "Committed date"
        assert out["audience"] == "gc"


def test_pipeline_feeds_builder_roundtrip(app):
    with app.app_context():
        db.session.add(Releases(
            job=500,
            release="1",
            job_name="Novel Flatiron",
            description="Embeds",
            stage="Released",
            fab_hrs=20.0,
            install_hrs=8.0,
            fab_order=3.0,
            start_install=date(2026, 8, 4),
            start_install_formulaTF=True,  # projected
            start_install_asap=False,
            start_install_no_color=False,
            is_active=True,
            is_archived=False,
        ))
        db.session.commit()

        pipe = get_project_pipeline(500)
        out = build_lookahead_schedule(pipe, weeks=3, today=TODAY)
        assert out["summary"]["projected_install_dates"] == 1
        by_phase = {p["phase"]: p for p in out["rows"][0]["phases"]}
        assert by_phase[PHASE_INSTALLATION]["date_source"] == "projected"
