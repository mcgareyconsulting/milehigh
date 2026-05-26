"""Tests for resolve_member_users (member→User chips) and the /brain/pickup/board endpoint."""
from app.config import Config
from app.models import Releases, PickupOrder, User, db
from app.brain.job_log.features.pickup.members import resolve_member_users


def _set_member_config(monkeypatch):
    # Always-on: Luis, Doug, + a junk id with no linked user (mirrors the real config).
    monkeypatch.setattr(Config, "PICKUP_TRELLO_MEMBER_IDS", "tid_luis,tid_doug,tid_junk")
    monkeypatch.setattr(Config, "PICKUP_PM_TRELLO_IDS", "RL:tid_rich,GA:tid_gary")


def _make_user(username, first, last, trello_id):
    u = User(username=username, first_name=first, last_name=last,
             password_hash="x", trello_id=trello_id)
    db.session.add(u)
    db.session.commit()
    return u


def test_resolve_member_users_orders_and_skips_unlinked(app, monkeypatch):
    with app.app_context():
        _set_member_config(monkeypatch)
        _make_user("lsolano@x", "Luis", "Solano", "tid_luis")
        _make_user("dferrin@x", "Doug", "Ferrin", "tid_doug")
        _make_user("rlosasso@x", "Rich", "Losasso", "tid_rich")
        # tid_junk → no user → silently skipped (no blank chip)

        out = resolve_member_users("RL")
        # always-on order (Luis, Doug) then the PM (Rich); junk dropped
        assert [u["name"] for u in out] == ["Luis Solano", "Doug Ferrin", "Rich Losasso"]
        assert [u["initials"] for u in out] == ["LS", "DF", "RL"]


def test_resolve_member_users_unknown_pm_yields_always_on_only(app, monkeypatch):
    with app.app_context():
        _set_member_config(monkeypatch)
        _make_user("lsolano@x", "Luis", "Solano", "tid_luis")
        out = resolve_member_users("WO")  # WO has no mapping
        assert [u["initials"] for u in out] == ["LS"]


def test_resolve_member_users_initials_fall_back_to_username(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(Config, "PICKUP_TRELLO_MEMBER_IDS", "tid_fab")
        monkeypatch.setattr(Config, "PICKUP_PM_TRELLO_IDS", "")
        # No first/last name → initials come from username.
        u = User(username="fabshop@x", password_hash="x", trello_id="tid_fab")
        db.session.add(u); db.session.commit()
        out = resolve_member_users(None)
        assert out[0]["initials"] == "FA"
        assert out[0]["name"] == "fabshop@x"


def test_pickup_board_returns_cards_with_assignees(admin_client, app, monkeypatch):
    with app.app_context():
        _set_member_config(monkeypatch)
        _make_user("lsolano@x", "Luis", "Solano", "tid_luis")
        _make_user("rlosasso@x", "Rich", "Losasso", "tid_rich")  # PM RL
        rel = Releases(job=410, release="698", job_name="Lennar", stage="Ship Planning", pm="RL")
        db.session.add(rel); db.session.commit()
        db.session.add(PickupOrder(release_id=rel.id, job=410, release="698",
                                   vendor="Dencol", status="received"))
        db.session.commit()

    resp = admin_client.get("/brain/pickup/board")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    card = data["pickups"][0]
    assert card["name"] == "PU Dencol: 410-698"
    assert card["trello_list"] == "Shipping planning"
    assert any(a["name"] == "Luis Solano" for a in card["assignees"])
    assert any(a["name"] == "Rich Losasso" for a in card["assignees"])  # PM RL


def test_pickup_board_requires_auth(client, app):
    resp = client.get("/brain/pickup/board")
    assert resp.status_code == 401
