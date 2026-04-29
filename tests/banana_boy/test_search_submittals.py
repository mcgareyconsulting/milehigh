"""Unit tests for the search_submittals tool, focused on the urgent_only filter."""
from app.banana_boy.tools import search_submittals
from app.models import Submittals, db


def _make(submittal_id, *, order_number=None, ball_in_court="Daniel",
          project_number="100", project_name="Project A", title=None):
    s = Submittals(
        submittal_id=submittal_id,
        title=title or f"Submittal {submittal_id}",
        status="Open",
        ball_in_court=ball_in_court,
        order_number=order_number,
        project_number=project_number,
        project_name=project_name,
    )
    db.session.add(s)
    return s


def test_urgent_only_filters_to_order_number_below_one(app):
    with app.app_context():
        _make("S1", order_number=0.1)
        _make("S2", order_number=0.5)
        _make("S3", order_number=1.0)
        _make("S4", order_number=2.5)
        _make("S5", order_number=None)
        db.session.commit()

        out = search_submittals(urgent_only=True)
        ids = [r["submittal_id"] for r in out["results"]]
        assert ids == ["S1", "S2"]  # sorted ascending by order_number
        assert out["query"]["urgent_only"] is True


def test_urgent_only_combines_with_ball_in_court(app):
    with app.app_context():
        _make("U1", order_number=0.2, ball_in_court="Daniel")
        _make("U2", order_number=0.3, ball_in_court="Colton")
        _make("U3", order_number=0.4, ball_in_court="Daniel, Colton")  # multi-assignee
        _make("U4", order_number=2.0, ball_in_court="Daniel")  # not urgent
        db.session.commit()

        out = search_submittals(ball_in_court="Daniel", urgent_only=True)
        ids = [r["submittal_id"] for r in out["results"]]
        assert ids == ["U1", "U3"]


def test_no_filter_returns_error(app):
    with app.app_context():
        out = search_submittals()
        assert "error" in out
        assert out["results"] == []


def test_urgent_only_alone_is_a_valid_filter(app):
    with app.app_context():
        _make("X1", order_number=0.5)
        db.session.commit()
        out = search_submittals(urgent_only=True)
        assert "error" not in out
        assert out["result_count"] == 1


def test_non_urgent_search_excludes_urgent_only_field_in_default_sort(app):
    """Default (non-urgent) search still sorts by last_updated desc, not order_number."""
    with app.app_context():
        _make("A1", order_number=0.1, ball_in_court="Daniel")
        _make("A2", order_number=5.0, ball_in_court="Daniel")
        db.session.commit()

        out = search_submittals(ball_in_court="Daniel")
        assert out["query"]["urgent_only"] is False
        # Both rows returned; sort order is by last_updated which is equal here,
        # so just assert both present.
        assert {r["submittal_id"] for r in out["results"]} == {"A1", "A2"}
