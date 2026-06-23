"""Tests for v3 drift detection — the read-only pass that surfaces where a meeting's
spoken reality diverges from the Brain (job log / DWL).

Covers the three v3 fixes that let the 480-625 miss be caught: additive/release-aware
scoping (the named release is always in context), job_comp visibility in the state line,
and the BrainDrift detect → sanitize → persist path. All LLM calls are patched off so
tests stay hermetic (the autouse _hermetic_brain_delta fixture forces the API hop to fail).
"""
import os
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models import db, Meeting, BrainDrift
from app.brain.meetings import context, brain_delta, service
from tests.conftest import make_release

FIXTURES = Path(__file__).parent / "fixtures"

# The ACTUAL drift output the live model returned for prod meeting id=6 (Production Meeting
# 6-18-26) — the run that motivated v3. Recorded verbatim so the no-op guard's effect on
# real data is a committed regression: only the genuine 480-625 contradiction must survive;
# the two same-value rows (which the model emitted at low confidence) must be dropped.
REAL_MEETING_6_DRIFTS = [
    {"target": "release", "ref": "480-625", "field": "job_comp",
     "stated_value": "25%", "brain_value": "20%", "kind": "contradiction", "confidence": 0.78,
     "quote": "mark that 25% because Garrett gave us the blessing yesterday to actually "
              "install those canopies"},
    {"target": "release", "ref": "550-556", "field": "start_install",
     "stated_value": "2026-07-06", "brain_value": "2026-07-06", "kind": "agreed_change",
     "confidence": 0.2},
    {"target": "release", "ref": "480-684", "field": "job_comp",
     "stated_value": "X", "brain_value": "X", "kind": "contradiction", "confidence": 0.1},
]


# --------------------------------------------------------------------------- #
# Pillar C — the snapshot state line now exposes job_comp + invoiced
# --------------------------------------------------------------------------- #
def test_release_state_line_includes_job_comp_and_invoiced(app):
    r = make_release(480, "625", job_name="Wood Partners - Alta Flatirons",
                     description="P3 canopies", stage="Install Start",
                     job_comp="20%", invoiced=None)
    line = context._release_state_line(r)
    assert "job_comp=20%" in line       # the field the 480-625 contradiction lives on
    assert "invoiced=—" in line
    assert "480-625" in line


# --------------------------------------------------------------------------- #
# Pillar A — additive, release-aware scoping
# --------------------------------------------------------------------------- #
def _tokens(releases):
    return {f"{r.job}-{r.release}" for r in releases}


def test_scoping_is_additive_seed_does_not_exclude_transcript_jobs(app):
    # The exact 480-625 failure shape: a standup pinned to project 550 that also discusses
    # 480-625. v2 short-circuited on project_number and dropped 480 entirely.
    make_release(480, "625", job_name="Alta Flatirons", description="P3 canopies",
                 job_comp="20%")
    make_release(550, "100", job_name="Seed Project")
    db.session.commit()
    m = Meeting(title="Production standup", meeting_type="other", project_number="550",
                transcript="Mark that 25% on 480-625, the P3 canopies.")
    db.session.add(m); db.session.commit()

    releases, _ = context.relevant_entities(m)
    toks = _tokens(releases)
    assert "480-625" in toks   # the transcript-named release is no longer excluded
    assert "550-100" in toks   # the project seed is still present


def test_scoping_always_includes_the_explicitly_named_release(app):
    # Job 480 with several releases — only the named one is guaranteed; siblings fill in.
    make_release(480, "625", job_name="Alta", description="P3 canopies", job_comp="20%")
    for rel in ("299", "389", "408", "430", "431", "432", "433"):
        make_release(480, rel, job_name="Alta", description=f"Area {rel}")
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop",
                transcript="Need to talk about 480-625 specifically.")
    db.session.add(m); db.session.commit()

    releases, _ = context.relevant_entities(m)
    assert "480-625" in _tokens(releases)


# --------------------------------------------------------------------------- #
# sanitize_drift — only well-formed, allowlisted drifts survive
# --------------------------------------------------------------------------- #
def test_sanitize_accepts_valid_release_drift():
    out = brain_delta.sanitize_drift({
        "target": "release", "ref": "480-625", "field": "job_comp",
        "stated_value": "25%", "brain_value": "20%", "kind": "contradiction",
        "quote": "mark that 25%", "confidence": 0.9,
    })
    assert out["field"] == "job_comp"
    assert out["target"] == "release"
    assert out["stated_value"] == "25%"
    assert out["kind"] == "contradiction"


def test_sanitize_rejects_bad_field_target_or_missing_ref():
    # field not in the release allowlist
    assert brain_delta.sanitize_drift(
        {"target": "release", "ref": "480-625", "field": "job_name",
         "stated_value": "x"}) is None
    # release field under a submittal target
    assert brain_delta.sanitize_drift(
        {"target": "submittal", "ref": "S1", "field": "job_comp",
         "stated_value": "x"}) is None
    # missing ref
    assert brain_delta.sanitize_drift(
        {"target": "release", "field": "job_comp", "stated_value": "x"}) is None
    assert brain_delta.sanitize_drift("nope") is None


def test_sanitize_defaults_unknown_kind_to_contradiction():
    out = brain_delta.sanitize_drift({
        "target": "release", "ref": "480-625", "field": "stage",
        "stated_value": "shipped", "kind": "weird-kind",
    })
    assert out["kind"] == "contradiction"


# --------------------------------------------------------------------------- #
# _is_noop — drop a "drift" whose stated value doesn't actually differ
# --------------------------------------------------------------------------- #
def test_is_noop_drops_identical_values_but_keeps_real_differences():
    assert brain_delta._is_noop("X", "X") is True
    assert brain_delta._is_noop("2026-07-06", "2026-07-06") is True   # equal as dates
    assert brain_delta._is_noop("20%", "20%") is True
    assert brain_delta._is_noop("25%", "20%") is False                # the 480-625 drift stays
    assert brain_delta._is_noop("2%", "20%") is False                 # no containment suppression
    assert brain_delta._is_noop("Ship Complete", "Fabrication") is False
    assert brain_delta._is_noop(None, "20%") is False


def test_sanitize_drops_noop_drift():
    # stated == Brain → not a drift at all (the false positives the live run produced).
    assert brain_delta.sanitize_drift({
        "target": "release", "ref": "480-684", "field": "job_comp",
        "stated_value": "X", "brain_value": "X", "kind": "contradiction"}) is None


# --------------------------------------------------------------------------- #
# Golden: the REAL recorded model output for prod meeting id=6
# --------------------------------------------------------------------------- #
def test_real_meeting_6_recorded_output_keeps_only_the_genuine_drift():
    kept = [d for d in (brain_delta.sanitize_drift(x) for x in REAL_MEETING_6_DRIFTS) if d]
    assert len(kept) == 1                       # the two same-value rows are dropped
    d = kept[0]
    assert d["ref"] == "480-625" and d["field"] == "job_comp"
    assert d["stated_value"] == "25%" and d["brain_value"] == "20%"
    assert d["kind"] == "contradiction"


# --------------------------------------------------------------------------- #
# Live eval (excluded by default; `pytest -m live` with ANTHROPIC_API_KEY set).
# Runs the REAL prod meeting id=6 transcript through the actual prompt and asserts the
# 480-625 job_comp drift (said 25% / Brain 20%) is caught — the v3 acceptance test.
# --------------------------------------------------------------------------- #
@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"),
                    reason="live LLM eval — export ANTHROPIC_API_KEY to run")
def test_live_real_transcript_catches_480_625_drift(app):
    transcript = (FIXTURES / "meeting_6_production_6_18.txt").read_text()
    # The real 480-625 state at meeting time: the room said 25%, the Brain held 20%.
    make_release(480, "625", job_name="Wood Partners - Alta Flatirons",
                 description="Pergola Structures", stage="Install Start",
                 job_comp="20%", invoiced="MF")
    db.session.commit()
    m = Meeting(title="Production Meeting 6-18-26", meeting_type="other",
                project_number="550", transcript=transcript,
                occurred_at=datetime(2026, 6, 18))
    db.session.add(m); db.session.commit()

    out = brain_delta.detect_drifts(m, today=date(2026, 6, 18))
    kept = [d for d in (brain_delta.sanitize_drift(x) for x in out["drifts"]) if d]
    hits = [d for d in kept if d["ref"] == "480-625" and d["field"] == "job_comp"]
    assert hits, f"expected a 480-625 job_comp drift; got {kept}"
    assert "25" in str(hits[0]["stated_value"])
    assert "20" in str(hits[0]["brain_value"])


# --------------------------------------------------------------------------- #
# detect_drifts — hermetic: no key / API failure yields no drifts (never a guess)
# --------------------------------------------------------------------------- #
def test_detect_drifts_returns_empty_when_llm_unavailable(app):
    make_release(480, "625", job_name="Alta", job_comp="20%")
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop",
                transcript="mark 480-625 at 25%")
    db.session.add(m); db.session.commit()

    # autouse _hermetic_brain_delta forces _call_anthropic to raise → no drifts, stub usage.
    out = brain_delta.detect_drifts(m)
    assert out["drifts"] == []
    assert out["usage"]["model"] == "stub"


def test_detect_drifts_returns_llm_drifts_on_success(app):
    make_release(480, "625", job_name="Alta", description="P3 canopies", job_comp="20%")
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop",
                transcript="mark 480-625 at 25%")
    db.session.add(m); db.session.commit()

    drift = {"target": "release", "ref": "480-625", "field": "job_comp",
             "stated_value": "25%", "brain_value": "20%", "kind": "contradiction",
             "quote": "mark that 25%", "confidence": 0.9}
    usage = {"input_tokens": 10, "output_tokens": 5, "model": "claude-opus-4-8",
             "cost_usd": 0.01}
    with patch("app.brain.meetings.brain_delta._call_anthropic",
               return_value=([drift], usage)):
        out = brain_delta.detect_drifts(m)
    assert len(out["drifts"]) == 1
    assert out["drifts"][0]["field"] == "job_comp"
    assert out["usage"]["model"] == "claude-opus-4-8"


# --------------------------------------------------------------------------- #
# persistence — detect → sanitize → store, anchoring + validation enforced
# --------------------------------------------------------------------------- #
def test_detect_and_store_persists_anchored_drift_drops_the_rest(app):
    r = make_release(480, "625", job_name="Wood Partners - Alta Flatirons",
                     description="P3 canopies", job_comp="20%")
    db.session.commit()
    m = Meeting(title="Production standup", meeting_type="other",
                transcript="mark 480-625 at 25%")
    db.session.add(m); db.session.commit()

    fake = {"drifts": [
        # real, anchored contradiction → stored
        {"target": "release", "ref": "480-625", "field": "job_comp",
         "stated_value": "25%", "brain_value": "20%", "kind": "contradiction",
         "quote": "mark that 25%", "confidence": 0.9},
        # unanchored (release doesn't exist) → dropped
        {"target": "release", "ref": "999-000", "field": "stage",
         "stated_value": "shipped", "kind": "contradiction"},
        # bad field → dropped by sanitize
        {"target": "release", "ref": "480-625", "field": "job_name",
         "stated_value": "x"},
    ], "usage": {"input_tokens": 0, "output_tokens": 0, "model": "stub", "cost_usd": 0.0}}

    with patch("app.brain.meetings.brain_delta.detect_drifts", return_value=fake):
        service._detect_and_store_drifts(m)

    drifts = BrainDrift.query.filter_by(meeting_id=m.id).all()
    assert len(drifts) == 1
    d = drifts[0]
    assert d.field == "job_comp"
    assert d.stated_value == "25%"
    assert d.brain_value == "20%"
    assert d.kind == "contradiction"
    assert d.release_id == r.id                      # anchored to the system-of-record row
    assert d.entity_name == "Wood Partners - Alta Flatirons"
    assert d.status == "open"                         # the only state v3 sets


def test_detect_and_store_is_regenerate_safe(app):
    r = make_release(480, "625", job_name="Alta", job_comp="20%")
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", transcript="x")
    db.session.add(m); db.session.commit()
    db.session.add(BrainDrift(meeting_id=m.id, target="release", ref="480-625",
                              field="stage", kind="contradiction", release_id=r.id,
                              status="open"))
    db.session.commit()

    fake = {"drifts": [], "usage": {"model": "stub", "cost_usd": 0.0,
                                    "input_tokens": 0, "output_tokens": 0}}
    with patch("app.brain.meetings.brain_delta.detect_drifts", return_value=fake):
        service._detect_and_store_drifts(m)

    # The prior drift is cleared and not replaced (LLM found none this run).
    assert BrainDrift.query.filter_by(meeting_id=m.id).count() == 0


# --------------------------------------------------------------------------- #
# End-to-end — extract_into_meeting runs the drift pass and stores rows
# --------------------------------------------------------------------------- #
def test_extract_into_meeting_stores_drifts(app):
    make_release(480, "625", job_name="Alta Flatirons", description="P3 canopies",
                 stage="Install Start", job_comp="20%", pm="WO")
    db.session.commit()
    m = Meeting(title="Production standup", meeting_type="other", project_number="480",
                agenda_text="Cover 480-625", transcript="(stub)",
                occurred_at=datetime(2026, 6, 18))
    db.session.add(m); db.session.commit()

    def fake_extract(transcript, today=None, people=None, context=None):
        return {"items": [], "usage": {"input_tokens": 0, "output_tokens": 0,
                                       "model": "stub", "cost_usd": 0.0}}

    drift = {"target": "release", "ref": "480-625", "field": "job_comp",
             "stated_value": "25%", "brain_value": "20%", "kind": "contradiction",
             "quote": "mark that 25%", "confidence": 0.9}
    drift_result = {"drifts": [drift], "usage": {"input_tokens": 0, "output_tokens": 0,
                                                 "model": "stub", "cost_usd": 0.0}}

    with patch("app.brain.meetings.service.extract", side_effect=fake_extract), \
         patch("app.brain.meetings.brain_delta.detect_drifts", return_value=drift_result):
        service.extract_into_meeting(m, notify=False)

    drifts = BrainDrift.query.filter_by(meeting_id=m.id).all()
    assert len(drifts) == 1
    assert drifts[0].field == "job_comp" and drifts[0].stated_value == "25%"
