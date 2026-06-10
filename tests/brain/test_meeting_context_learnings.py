"""Tests for pre-meeting context assembly + the learnings loop.

All LLM calls are patched/forced off so tests stay hermetic.
"""
from datetime import date, datetime, timedelta
from unittest.mock import patch

from app.models import (
    db, Meeting, ChecklistItem, ReleaseEvents, ExtractionSignal, MeetingLearning,
)
from app.brain.meetings import context, learn, service
from tests.conftest import make_user, make_release


REVIEWER = "boneill@mhmw.com"


def _rel_event(job, release, action, payload, *, created_at, source="Trello"):
    db.session.add(ReleaseEvents(
        job=job, release=release, action=action, payload=payload,
        payload_hash=f"{action}-{job}-{release}-{created_at.isoformat()}",
        source=source, is_system_echo=False, created_at=created_at,
    ))


# --------------------------------------------------------------------------- #
# Entity scoping (hybrid)
# --------------------------------------------------------------------------- #
def test_relevant_entities_uses_project_number_when_set(app):
    make_release(480, "146", job_name="Wood Partners - Alta Flatirons")
    make_release(999, "1", job_name="Some Other Job")
    db.session.commit()
    m = Meeting(title="GC call", meeting_type="gc_pm", project_number="480")
    db.session.add(m); db.session.commit()

    releases, _ = context.relevant_entities(m)
    jobs = {r.job for r in releases}
    assert 480 in jobs and 999 not in jobs   # scoped to the pinned project only


def test_relevant_entities_token_scans_transcript_when_no_project(app):
    make_release(480, "146", job_name="Alta Flatirons")
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop",
                transcript="Luis: we still need to refab 480-146 treads by Thursday")
    db.session.add(m); db.session.commit()

    releases, _ = context.relevant_entities(m)
    assert 480 in {r.job for r in releases}   # found via the '480-146' token


# --------------------------------------------------------------------------- #
# EXTRACTION context: agenda + light job state + guidance (NO event history)
# --------------------------------------------------------------------------- #
def test_assemble_extraction_context_has_agenda_state_and_guidance(app):
    make_release(480, "146", job_name="Alta Flatirons", stage="Fabrication")
    db.session.add(ExtractionSignal(signal_type="pattern", key="fyi:x",
                                    value="fyi items are usually noise", count=3))
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", project_number="480",
                agenda_text="Walk the 480-146 fab status", occurred_at=datetime(2026, 6, 9))
    db.session.add(m); db.session.commit()

    out = context.assemble_extraction_context(m)
    assert "PRE-MEETING CONTEXT" in out["combined"]
    assert "JOB STATE" in out["combined"]
    assert "LEARNED GUIDANCE" in out["combined"]
    assert "stage=Fabrication" in out["state"]   # light state line, no event history


# --------------------------------------------------------------------------- #
# SUMMARY context: only events that landed DURING the meeting window
# --------------------------------------------------------------------------- #
def test_build_runtime_events_includes_only_in_window_events(app):
    make_release(480, "146", job_name="Alta Flatirons", stage="Fabrication", pm="WO")
    start = datetime(2026, 6, 9, 9, 0)
    end = datetime(2026, 6, 9, 10, 0)
    _rel_event(480, "146", "update_stage", {"to": "Ready to Ship"},
               created_at=start + timedelta(minutes=30))            # in-window → shown
    _rel_event(480, "146", "update_stage", {"to": "Fabrication"},
               created_at=start - timedelta(days=2))                # before → excluded
    _rel_event(480, "146", "update_notes", {"to": "later note"},
               created_at=end + timedelta(hours=2))                 # after → excluded
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", project_number="480",
                occurred_at=start, ended_at=end)
    db.session.add(m); db.session.commit()

    block = context.build_runtime_events(m)
    assert "480-146" in block and "stage=Fabrication" in block   # state line
    assert "Ready to Ship" in block        # the in-window event summary
    assert "later note" not in block       # the post-meeting event is excluded


# --------------------------------------------------------------------------- #
# Two outputs: agenda grounds extraction; during-meeting events ground the summary
# --------------------------------------------------------------------------- #
def test_extract_into_meeting_grounds_todos_and_builds_summary(app):
    make_user(REVIEWER, first_name="Bill", is_admin=True)
    make_release(480, "146", job_name="Alta Flatirons", stage="Fabrication", pm="WO")
    start = datetime(2026, 6, 9, 9, 0)
    _rel_event(480, "146", "update_stage", {"to": "Ready to Ship"},
               created_at=start + timedelta(minutes=20))   # in-window → summary context
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", project_number="480",
                agenda_text="Cover 480-146", transcript="(stub)",
                occurred_at=start, ended_at=start + timedelta(hours=1))
    db.session.add(m); db.session.commit()

    seen = {}

    def fake_extract(transcript, today=None, people=None, context=None):
        seen["context"] = context
        return {"items": [], "usage": {"input_tokens": 0, "output_tokens": 0,
                                       "model": "stub", "cost_usd": 0.0}}

    # The autouse _hermetic_meeting_summary fixture forces summarize() to its stub, which
    # echoes the during-meeting events — so the summary carries the in-window change.
    with patch("app.brain.meetings.service.extract", side_effect=fake_extract):
        service.extract_into_meeting(m, notify=False)

    # To-do extraction got the agenda + light job state (NOT event history).
    assert "PRE-MEETING CONTEXT" in (seen["context"] or "")
    assert "JOB STATE" in seen["context"]
    assert "Ready to Ship" not in seen["context"]   # event activity is NOT in the to-do context
    # The during-meeting events were stored and fed the summary.
    assert m.context_snapshot and "Ready to Ship" in m.context_snapshot
    assert m.summary and "Ready to Ship" in m.summary


def test_extract_into_meeting_folds_summary_cost_into_meter(app):
    make_user(REVIEWER, first_name="Bill", is_admin=True)
    m = Meeting(title="Shop", meeting_type="internal_shop", transcript="(stub)",
                occurred_at=datetime(2026, 6, 9))
    db.session.add(m); db.session.commit()

    ret = {"items": [], "usage": {"input_tokens": 10, "output_tokens": 5,
                                  "model": "claude-opus-4-8", "cost_usd": 0.001}}
    fake_summary = ("During the call nothing notable changed.",
                    {"input_tokens": 7, "output_tokens": 3, "model": "haiku",
                     "cost_usd": 0.00002})
    with patch("app.brain.meetings.service.extract", return_value=ret), \
         patch("app.brain.meetings.summary._call_anthropic", return_value=fake_summary):
        service.extract_into_meeting(m, notify=False)

    assert m.summary == "During the call nothing notable changed."
    assert "summary" in m.extract_model                 # tagged in the blended meter
    assert m.extract_input_tokens == 17                 # 10 (extract) + 7 (summary)


# --------------------------------------------------------------------------- #
# Learnings: deterministic signals + LLM-distilled signals
# --------------------------------------------------------------------------- #
def _meeting_with_items(items):
    m = Meeting(title="m", meeting_type="internal_shop")
    db.session.add(m); db.session.flush()
    for it in items:
        db.session.add(ChecklistItem(meeting_id=m.id, **it))
    db.session.commit()
    return m


def test_deterministic_owner_map_signal_from_reassignment(app):
    luis = make_user("lsolano@mhmw.com", first_name="Luis", last_name="Solano")
    m = _meeting_with_items([
        dict(title="refab treads", item_type="action", status="accepted",
             matched_job_number="480", proposed_owner_user_id=None, owner_user_id=luis.id),
    ])
    with patch("app.brain.meetings.learn.cfg.ANTHROPIC_API_KEY", None):  # deterministic only
        learn.synthesize_learnings(m)

    sig = ExtractionSignal.query.filter_by(signal_type="owner_map", key="480").first()
    assert sig is not None and sig.value == "Luis Solano"
    assert m.learned_at is not None
    assert MeetingLearning.query.filter_by(meeting_id=m.id).count() == 1


def test_stats_tally_accept_reject_by_item_type(app):
    m = _meeting_with_items([
        dict(title="a", item_type="action", status="accepted"),
        dict(title="b", item_type="fyi", status="rejected"),
        dict(title="c", item_type="fyi", status="rejected"),
    ])
    with patch("app.brain.meetings.learn.cfg.ANTHROPIC_API_KEY", None):
        learning = learn.synthesize_learnings(m)
    by_type = learning.payload["stats"]["by_item_type"]
    assert by_type["action"]["accepted"] == 1
    assert by_type["fyi"]["rejected"] == 2


def test_llm_aliases_and_patterns_upsert_signals(app):
    m = _meeting_with_items([dict(title="x", item_type="fyi", status="rejected")])
    fake = ({
        "summary": "ok",
        "by_outcome": {"rejected": "fyi noise"},
        "aliases": [{"from": "class of Sand Creek", "to": "Sand Creek Flats"}],
        "patterns": [{"item_type": "fyi", "guidance": "fyi items are usually noise"}],
    }, {"input_tokens": 1, "output_tokens": 1, "model": "haiku", "cost_usd": 0.0})
    with patch("app.brain.meetings.learn._llm_synthesize", return_value=fake):
        learn.synthesize_learnings(m)

    alias = ExtractionSignal.query.filter_by(signal_type="alias",
                                             key="class of Sand Creek").first()
    assert alias is not None and alias.value == "Sand Creek Flats"
    assert ExtractionSignal.query.filter_by(signal_type="pattern").count() == 1


def test_upsert_signal_reinforces_count(app):
    learn.upsert_signal("alias", "foo", "Bar")
    learn.upsert_signal("alias", "foo", "Bar")
    db.session.commit()
    sig = ExtractionSignal.query.filter_by(signal_type="alias", key="foo").one()
    assert sig.count == 2   # reinforced, not duplicated


# --------------------------------------------------------------------------- #
# Trigger: learning fires only once the last proposed item is reviewed
# --------------------------------------------------------------------------- #
def test_review_completion_triggers_learning_once(app):
    make_user(REVIEWER, first_name="Bill", is_admin=True)
    m = _meeting_with_items([
        dict(title="a", status="proposed"),
        dict(title="b", status="proposed"),
    ])
    items = m.items.order_by(ChecklistItem.id).all()

    with patch("app.brain.meetings.learn.start_learning") as mock_learn:
        service.review_item(items[0].id, action="accept")
        assert mock_learn.call_count == 0          # one item still proposed
        service.review_item(items[1].id, action="reject")
        assert mock_learn.call_count == 1          # last proposed reviewed → fires once


# --------------------------------------------------------------------------- #
# Alias feedback normalizes a garbled name so the job matches up front
# --------------------------------------------------------------------------- #
def test_active_alias_normalizes_garbled_name_for_matching(app):
    make_release(170, "348", job_name="Sand Creek Flats", pm="WO")
    db.session.add(ExtractionSignal(signal_type="alias", key="class of Sand Creek",
                                    value="Sand Creek Flats", count=2, active=True))
    db.session.commit()
    # apply_aliases swaps the garbled spelling for the canonical job name.
    fixed = context.apply_aliases("follow up on class of Sand Creek pours")
    assert "Sand Creek Flats" in fixed

    m = _meeting_with_items([
        dict(title="follow up on class of Sand Creek pours", item_type="action",
             status="proposed"),
    ])
    with patch("app.brain.meetings.owner_match.cfg.ANTHROPIC_API_KEY", None):  # no Haiku
        from app.brain.meetings import owner_match
        owner_match.infer_owners_for_meeting(m)
    it = m.items.first()
    assert it.matched_job_number == "170"   # matched via the learned alias
