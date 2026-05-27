"""Tests for the reschedule proposal + pickup tools and the chat surfacing path."""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.banana_boy.tools import get_release_pickup, propose_reschedule_install
from app.models import PickupOrder, db
from tests.conftest import make_release


# --- propose_reschedule_install (read-only) -------------------------------------


def test_propose_no_conflict_preserves_duration_and_team(app):
    with app.app_context():
        make_release(500, "1", start_install=date(2026, 6, 1), comp_eta=date(2026, 6, 3),
                     installer="Saul 2", install_hrs=48)
        db.session.commit()
        out = propose_reschedule_install(500, "1", "2026-06-10")
        assert out["has_conflict"] is False
        assert out["proposed"]["start_install"] == "2026-06-10"
        assert out["proposed"]["comp_eta"] == "2026-06-12"   # 2-day window preserved
        assert out["proposed"]["installer"] == "Saul 2"      # current team kept
        assert "Saul 2" in out["free_teams"]


def test_propose_detects_conflict_and_lists_free_teams(app):
    with app.app_context():
        # An existing install sitting on Saul 2 in mid-June.
        make_release(600, "1", start_install=date(2026, 6, 10), comp_eta=date(2026, 6, 13),
                     installer="Saul 2", install_hrs=48)
        # The release we want to move into that window.
        make_release(600, "2", start_install=date(2026, 7, 1), comp_eta=date(2026, 7, 2),
                     installer="Saul 3", install_hrs=24)
        db.session.commit()
        out = propose_reschedule_install(600, "2", "2026-06-11", requested_installer="Saul 2")
        assert out["has_conflict"] is True
        assert out["conflicts"][0]["identifier"] == "600-1"
        assert out["requested_installer"] == "Saul 2"
        assert "Saul 2" not in out["free_teams"]
        assert "Saul 3" in out["free_teams"]            # user can pick this instead
        assert "600-1" in [c["identifier"] for c in out["busy_teams"]["Saul 2"]]


def test_propose_does_not_conflict_with_self(app):
    with app.app_context():
        make_release(700, "1", start_install=date(2026, 6, 1), comp_eta=date(2026, 6, 4),
                     installer="Saul 2", install_hrs=48)
        db.session.commit()
        out = propose_reschedule_install(700, "1", "2026-06-02", requested_installer="Saul 2")
        assert out["has_conflict"] is False


def test_propose_explicit_comp_eta(app):
    with app.app_context():
        make_release(705, "1", start_install=date(2026, 6, 1), installer="Saul 2", install_hrs=24)
        db.session.commit()
        out = propose_reschedule_install(705, "1", "2026-06-10", new_comp_eta="2026-06-20")
        assert out["proposed"]["comp_eta"] == "2026-06-20"


def test_propose_unknown_release_errors(app):
    with app.app_context():
        assert "error" in propose_reschedule_install(999, "9", "2026-06-01")


def test_propose_bad_date_errors(app):
    with app.app_context():
        make_release(710, "1", start_install=date(2026, 6, 1), installer="Saul 2", install_hrs=24)
        db.session.commit()
        assert "error" in propose_reschedule_install(710, "1", "June 1st")


# --- get_release_pickup ---------------------------------------------------------


def test_get_pickup_returns_email_body(app):
    with app.app_context():
        r = make_release(800, "1", job_name="Acme Tower")
        db.session.flush()
        db.session.add(PickupOrder(
            release_id=r.id, job=800, release="1", vendor="Dencol",
            email_message_id="m1", email_subject="800-1 PU request",
            email_from="vendor@dencol.com", email_to="us@mhmw.com",
            email_received_at=datetime(2026, 5, 26, 15, 0, 0),
            email_body="Pick up 3 stair stringers and 2 rails.",
            status="card_created", trello_list_name="Shipping planning",
        ))
        db.session.commit()
        out = get_release_pickup(800, "1")
        assert out["pickup_count"] == 1
        p = out["pickups"][0]
        assert p["email_subject"] == "800-1 PU request"
        assert "stringers" in p["email_body"]
        assert p["body_truncated"] is False


def test_get_pickup_none_when_absent(app):
    with app.app_context():
        make_release(810, "1")
        db.session.commit()
        out = get_release_pickup(810, "1")
        assert out["pickup_count"] == 0
        assert out["pickups"] == []


def test_get_pickup_unknown_release_errors(app):
    with app.app_context():
        out = get_release_pickup(820, "1")
        assert "error" in out


# --- chat surfaces the proposal to the frontend ---------------------------------


def _usage():
    return SimpleNamespace(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0, cache_creation_input_tokens=0)


def _tool_use_response(name, tool_input):
    block = SimpleNamespace(type="tool_use", id="tu1", name=name, input=tool_input)
    return SimpleNamespace(content=[block], stop_reason="tool_use", usage=_usage())


def _text_response(text="Saul 2 is open that week — here's the rundown."):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block], stop_reason="end_turn", usage=_usage())


def test_chat_surfaces_reschedule_proposed_action(app, client, logged_in_user):
    with app.app_context():
        make_release(900, "1", start_install=date(2026, 6, 1), comp_eta=date(2026, 6, 3),
                     installer="Saul 2", install_hrs=48)
        db.session.commit()

    with patch("app.banana_boy.client._get_client") as gc:
        gc.return_value.messages.create.side_effect = [
            _tool_use_response("propose_reschedule_install",
                               {"job": 900, "release": "1", "new_start_install": "2026-06-10"}),
            _text_response(),
        ]
        resp = client.post("/banana-boy/chat", json={"message": "move 900-1 to next week"})

    assert resp.status_code == 200
    pa = resp.get_json()["message"]["proposed_action"]
    assert pa is not None
    assert pa["type"] == "reschedule_install"
    assert pa["data"]["proposed"]["start_install"] == "2026-06-10"
    assert pa["data"]["identifier"] == "900-1"


def test_chat_no_proposed_action_for_plain_reply(app, client, logged_in_user):
    with patch("app.banana_boy.client._get_client") as gc:
        gc.return_value.messages.create.return_value = _text_response("Hi there.")
        resp = client.post("/banana-boy/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.get_json()["message"]["proposed_action"] is None
