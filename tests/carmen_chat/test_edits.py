"""Spoken release edits: propose, sign, confirm, write.

The whole design rests on one claim — that nothing is written on the strength of a
transcript. These tests try to break that claim from every direction: proposing without
rights, applying without rights, applying a tampered plan, applying a stale one, and
applying one issued to somebody else.
"""
import time
from unittest.mock import patch

import pytest

from app.brain.carmen_chat import edits, live
from app.config import Config
from app.models import ReleaseEvents, Releases, db


@pytest.fixture
def edit_on(monkeypatch):
    monkeypatch.setattr(Config, "CARMEN_VOICE_ENABLED", True)
    monkeypatch.setattr(Config, "CARMEN_LIVE_ENABLED", True)
    monkeypatch.setattr(Config, "CARMEN_EDIT_ENABLED", True)
    monkeypatch.setattr(Config, "XAI_API_KEY", "xai-test-key")
    monkeypatch.setattr(Config, "SECRET_KEY", "test-signing-secret")
    return Config


@pytest.fixture
def release(app):
    """A real release row to edit."""
    row = Releases(job=150, release="893", job_name="Alta Metro", stage="Weld Complete",
                   notes="existing note")
    db.session.add(row)
    db.session.commit()
    return row


def _propose(client, changes, identifier="150-893"):
    return client.post("/brain/carmen-chat/voice/live/tool", json={
        "name": edits.TOOL_PROPOSE_CHANGES,
        "arguments": {"identifier": identifier, "changes": changes},
    })


# --- the tool is not even offered to a read-only user ---------------------------------

def test_propose_tool_is_hidden_from_non_admins(edit_on, bb_user, bb_admin_user):
    assert live.can_edit(bb_user) is False
    assert live.can_edit(bb_admin_user) is True
    names = {t["name"] for t in live.realtime_tools(bb_user)}
    assert edits.TOOL_PROPOSE_CHANGES not in names
    admin_names = {t["name"] for t in live.realtime_tools(bb_admin_user)}
    assert edits.TOOL_PROPOSE_CHANGES in admin_names


def test_edit_capability_can_be_switched_off_entirely(edit_on, bb_admin_user, monkeypatch):
    monkeypatch.setattr(Config, "CARMEN_EDIT_ENABLED", False)
    assert live.can_edit(bb_admin_user) is False
    assert edits.TOOL_PROPOSE_CHANGES not in {t["name"] for t in live.realtime_tools(bb_admin_user)}


def test_admin_prompt_corrects_the_read_only_claim(edit_on, bb_user, bb_admin_user):
    """The base prompt says she is read-only; for an admin that would be a lie."""
    assert "YOU CAN MAKE CHANGES" in live.instructions_for(bb_admin_user)
    assert "YOU CAN MAKE CHANGES" not in live.instructions_for(bb_user)


def test_prompt_forbids_narrating_a_card_that_is_already_on_screen(edit_on, bb_admin_user):
    """Reading the change back out loud duplicates the card — it's noise, not safety."""
    prompt = live.instructions_for(bb_admin_user)
    assert "Ten words at most" in prompt             # she speaks, but briefly
    assert "heard, not written down" in prompt       # and it stays out of the chat pane
    assert "pressing the button" in prompt           # "confirm" is for the card, not a new ask


def test_config_reports_edit_capability_per_user(edit_on, bb_user, bb_admin_user):
    """The header says 'read-only' or 'can edit' off this."""
    assert live.config_summary(bb_admin_user)["can_edit"] is True
    assert live.config_summary(bb_user)["can_edit"] is False
    assert live.config_summary()["can_edit"] is False


def test_non_admin_calling_the_tool_anyway_is_refused(bb_client, release, edit_on):
    """The tool is undeclared for them — but never trust the client to only ask for what it was offered."""
    resp = _propose(bb_client, [{"field": "stage", "value": "Ship Planning"}])
    assert resp.status_code == 200
    assert "cannot make changes" in resp.get_json()["result"]["error"]
    assert "proposal" not in resp.get_json()


# --- proposing writes nothing ---------------------------------------------------------

def test_propose_resolves_changes_without_writing(app, bb_admin_client, release, edit_on):
    resp = _propose(bb_admin_client, [
        {"field": "stage", "value": "ship planning"},                     # case-insensitive
        {"field": "notes", "value": "@Bill hey we need to get this moving"},
    ])
    assert resp.status_code == 200
    proposal = resp.get_json()["proposal"]
    assert proposal["applied"] is False
    plan = proposal["plan"]
    assert plan["job"] == 150 and plan["release"] == "893"

    by_field = {c["field"]: c for c in plan["changes"]}
    assert by_field["stage"]["from"] == "Weld Complete"
    assert by_field["stage"]["to"] == "Ship Planning"
    # Notes overwrite by default — the activity feed carries the old note.
    assert by_field["notes"]["to"] == "@Bill hey we need to get this moving"
    assert by_field["notes"]["mode"] == "replace"
    assert by_field["notes"]["from"] == "existing note"

    # Nothing touched the row or the event log.
    with app.app_context():
        row = Releases.resolve(150, "893")
        assert row.stage == "Weld Complete"
        assert row.notes == "existing note"
        assert ReleaseEvents.query.count() == 0


def test_notes_append_mode_keeps_the_existing_text(bb_admin_client, release, edit_on):
    """Opt-in, for when someone says to add to the note rather than change it."""
    resp = _propose(bb_admin_client, [{"field": "notes", "value": "and paint it", "mode": "append"}])
    change = resp.get_json()["proposal"]["plan"]["changes"][0]
    assert change["to"].startswith("existing note")
    assert "and paint it" in change["to"]
    assert change["from_display"] == "—"        # nothing is being replaced


@pytest.mark.parametrize("changes,fragment", [
    ([{"field": "stage", "value": "Shipping Planning"}], "isn't a stage I recognise"),
    ([{"field": "stage", "value": "Weld Complete"}], "already in"),
    ([{"field": "invoiced", "value": "X"}], "can't change"),
    ([{"field": "ship_date", "value": "next friday"}], "couldn't read"),
    ([], "no changes"),
    ([{"field": "stage", "value": "Hold"}, {"field": "stage", "value": "Complete"}], "two different values"),
])
def test_propose_rejects_bad_input_with_a_speakable_reason(bb_admin_client, release, edit_on,
                                                           changes, fragment):
    resp = _propose(bb_admin_client, changes)
    assert fragment in resp.get_json()["result"]["error"]


def test_propose_rejects_an_unknown_release(bb_admin_client, release, edit_on):
    resp = _propose(bb_admin_client, [{"field": "stage", "value": "Hold"}], identifier="999-111")
    assert "can't find release" in resp.get_json()["result"]["error"]


def test_propose_rejects_a_job_without_a_release(bb_admin_client, release, edit_on):
    """'150' alone is ambiguous — it must not fan out across every release on the job."""
    resp = _propose(bb_admin_client, [{"field": "stage", "value": "Hold"}], identifier="150")
    assert "couldn't work out which release" in resp.get_json()["result"]["error"]


# --- the signature is the gate --------------------------------------------------------

def test_apply_requires_admin(bb_client, edit_on):
    assert bb_client.post("/brain/carmen-chat/voice/live/apply",
                          json={"plan": {}, "token": "x", "issued_at": 0}).status_code == 403


def test_apply_rejects_a_tampered_plan(app, bb_admin_client, release, edit_on):
    proposal = _propose(bb_admin_client, [{"field": "stage", "value": "Ship Planning"}]).get_json()["proposal"]
    # Swap the target release after signing — the classic attack this guards against.
    proposal["plan"]["release"] = "894"
    resp = bb_admin_client.post("/brain/carmen-chat/voice/live/apply", json={
        "plan": proposal["plan"], "token": proposal["token"], "issued_at": proposal["issued_at"],
    })
    assert resp.status_code == 400
    assert "couldn't be verified" in resp.get_json()["error"]
    with app.app_context():
        assert Releases.resolve(150, "893").stage == "Weld Complete"


def test_apply_rejects_an_expired_proposal(bb_admin_client, release, edit_on):
    proposal = _propose(bb_admin_client, [{"field": "stage", "value": "Ship Planning"}]).get_json()["proposal"]
    stale = int(time.time()) - (edits._TTL_SECONDS + 60)
    resp = bb_admin_client.post("/brain/carmen-chat/voice/live/apply", json={
        "plan": proposal["plan"],
        "token": edits._sign(proposal["plan"], _admin_id(bb_admin_client), stale),
        "issued_at": stale,
    })
    assert resp.status_code == 400
    assert "expired" in resp.get_json()["error"]


def test_apply_rejects_a_proposal_issued_to_another_user(bb_admin_client, bb_admin_user, release, edit_on):
    plan = _propose(bb_admin_client, [{"field": "stage", "value": "Ship Planning"}]).get_json()["proposal"]["plan"]
    issued = int(time.time())
    resp = bb_admin_client.post("/brain/carmen-chat/voice/live/apply", json={
        "plan": plan,
        "token": edits._sign(plan, bb_admin_user.id + 12345, issued),   # someone else's
        "issued_at": issued,
    })
    assert resp.status_code == 400


def _admin_id(client):
    from app.models import User
    return User.query.filter_by(username="admin@mhmw.com").first().id


# --- confirmed changes actually land --------------------------------------------------

def test_confirmed_changes_write_through_the_real_commands(app, bb_admin_client, release, edit_on):
    proposal = _propose(bb_admin_client, [
        {"field": "stage", "value": "Ship Planning"},
        {"field": "notes", "value": "@Bill hey we need to get this moving"},
    ]).get_json()["proposal"]

    resp = bb_admin_client.post("/brain/carmen-chat/voice/live/apply", json={
        "plan": proposal["plan"], "token": proposal["token"], "issued_at": proposal["issued_at"],
    })
    assert resp.status_code == 200
    out = resp.get_json()
    assert out["applied"] == 2 and out["failed"] == 0
    assert len(out["event_ids"]) == 2      # every change is undoable

    with app.app_context():
        row = Releases.resolve(150, "893")
        assert row.stage == "Ship Planning"
        assert row.notes == "@Bill hey we need to get this moving"
        # Events are attributed to Carmen, so the audit trail shows where it came from.
        actions = {e.action for e in ReleaseEvents.query.all()}
        assert {"update_stage", "update_notes"} <= actions


def test_one_failed_change_does_not_hide_the_others(app, bb_admin_client, release, edit_on):
    """A broken note must not silently swallow an applied stage move."""
    proposal = _propose(bb_admin_client, [
        {"field": "stage", "value": "Ship Planning"},
        {"field": "notes", "value": "some note"},
    ]).get_json()["proposal"]

    with patch("app.brain.job_log.features.notes.command.UpdateNotesCommand.execute",
               side_effect=RuntimeError("boom")):
        out = bb_admin_client.post("/brain/carmen-chat/voice/live/apply", json={
            "plan": proposal["plan"], "token": proposal["token"],
            "issued_at": proposal["issued_at"],
        }).get_json()

    assert out["applied"] == 1 and out["failed"] == 1
    statuses = {r["field"]: r["status"] for r in out["results"]}
    assert statuses == {"stage": "applied", "notes": "failed"}
    with app.app_context():
        assert Releases.resolve(150, "893").stage == "Ship Planning"
