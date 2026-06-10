"""Seed a fake meeting fixture so you can exercise the live extraction + summary path.

Sets up a coherent, COLLISION-SAFE scenario for the Wood Partners agenda/transcript
artifacts. It uses deliberately fake identifiers (job 9099, submittal SEED-SD-1) so it will
NOT touch real releases/submittals — important when seeding into sandbox, which holds real
data. Re-running resets the fixture; `--clean` removes it entirely.

  - two fake releases (9099-146, 9099-150) + one fake submittal (SEED-SD-1)
  - release/submittal events stamped INSIDE the meeting window (so the summary's
    "events during meeting" block has real activity to weave in)
  - a manual Meeting with the agenda (.md) and transcript already attached, its window
    [occurred_at, ended_at] bracketing the seeded events

Then open the printed meeting in the UI and click "Generate to-do list" — that runs the
real Opus extraction (grounded by the agenda + job state) AND the Haiku summary (grounded
by the during-meeting events).

Idempotent. Refuses to run against production.

PREREQ: the meeting context/summary migrations must already be applied to the target DB:
    ENVIRONMENT=sandbox python migrations/add_meeting_context_and_learnings.py
    ENVIRONMENT=sandbox python migrations/add_meeting_summary_and_ended_at.py

Run with:
    ENVIRONMENT=sandbox python scripts/seed_fake_meeting.py            # seed / reset
    ENVIRONMENT=sandbox python scripts/seed_fake_meeting.py --clean    # remove the fixture
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

ARTIFACTS = os.path.join(ROOT_DIR, "test_artifacts")
AGENDA_FILE = os.path.join(ARTIFACTS, "wood_partners_agenda.md")
TRANSCRIPT_FILE = os.path.join(ARTIFACTS, "wood_partners_transcript.txt")

SEED_TITLE = "Wood Partners — Alta Flatirons Weekly Coordination [SEED]"
SEED_TAG = "seed-fake-meeting"        # payload_hash prefix so we can find/replace our events
SEED_JOB = 9099                       # fake job # — will not collide with real releases
SEED_SUBMITTAL_ID = "SEED-SD-1"       # fake submittal id — will not collide with Procore ids
PROJECT = str(SEED_JOB)


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _upsert_release(db, Releases, *, job, release, **fields):
    row = Releases.query.filter_by(job=job, release=release).first()
    if row is None:
        row = Releases(job=job, release=release, job_name=fields.get("job_name", ""))
        db.session.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    row.is_active = True
    row.is_archived = False
    return row


def _upsert_submittal(db, Submittals, *, submittal_id, **fields):
    row = Submittals.query.filter_by(submittal_id=submittal_id).first()
    if row is None:
        row = Submittals(submittal_id=submittal_id)
        db.session.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    return row


def _delete_seed_meetings(db, Meeting, ChecklistItem, MeetingLearning):
    for old in Meeting.query.filter_by(title=SEED_TITLE).all():
        ChecklistItem.query.filter_by(meeting_id=old.id).delete()
        MeetingLearning.query.filter_by(meeting_id=old.id).delete()
        db.session.delete(old)


def _delete_seed_events(db, ReleaseEvents, SubmittalEvents):
    ReleaseEvents.query.filter(
        ReleaseEvents.payload_hash.like(f"{SEED_TAG}%")).delete(synchronize_session=False)
    SubmittalEvents.query.filter(
        SubmittalEvents.payload_hash.like(f"{SEED_TAG}%")).delete(synchronize_session=False)


def clean():
    from app import create_app
    from app.models import (
        db, Meeting, ChecklistItem, MeetingLearning,
        Releases, Submittals, ReleaseEvents, SubmittalEvents,
    )
    app = create_app()
    with app.app_context():
        _delete_seed_meetings(db, Meeting, ChecklistItem, MeetingLearning)
        _delete_seed_events(db, ReleaseEvents, SubmittalEvents)
        Releases.query.filter_by(job=SEED_JOB).delete(synchronize_session=False)
        Submittals.query.filter_by(submittal_id=SEED_SUBMITTAL_ID).delete(synchronize_session=False)
        db.session.commit()
        print(f"✓ Removed the seed fixture (meeting, events, job {SEED_JOB}, {SEED_SUBMITTAL_ID}).")
        return True


def seed():
    from app import create_app
    from app.models import (
        db, Meeting, ChecklistItem, MeetingLearning,
        Releases, Submittals, ReleaseEvents, SubmittalEvents,
    )

    agenda = _read(AGENDA_FILE)
    transcript = _read(TRANSCRIPT_FILE)

    app = create_app()
    with app.app_context():
        now = datetime.utcnow()
        start = now - timedelta(minutes=60)
        end = now + timedelta(minutes=60)

        # 1. Fake releases + submittal the meeting talks about.
        _upsert_release(db, Releases, job=SEED_JOB, release="146",
                        job_name="Wood Partners - Alta Flatirons (SEED)",
                        description="Building A stairs & rails", stage="Ready to Ship",
                        stage_group="SHIPPING", pm="WO",
                        start_install=(now + timedelta(days=35)).date())
        _upsert_release(db, Releases, job=SEED_JOB, release="150",
                        job_name="Wood Partners - Alta Flatirons (SEED)",
                        description="Building B embeds", stage="Detailing",
                        stage_group="DRAFTING", pm="WO")
        _upsert_submittal(db, Submittals, submittal_id=SEED_SUBMITTAL_ID,
                          project_number=PROJECT, project_name="Wood Partners - Alta Flatirons (SEED)",
                          title="Stair shop drawings", type="Shop Drawings",
                          status="Approved as Noted", ball_in_court="Mile High Metal Works",
                          due_date=(now + timedelta(days=5)).date())
        db.session.commit()

        # 2. Replace any prior seeded events, then stamp fresh ones INSIDE the window.
        _delete_seed_events(db, ReleaseEvents, SubmittalEvents)
        db.session.commit()

        rel_events = [
            ("update_stage", "146", {"to": "Ready to Ship"}, start + timedelta(minutes=10)),
            ("update_start_install", "146",
             {"field": "start_install", "new_value": (now + timedelta(days=35)).date().isoformat()},
             start + timedelta(minutes=20)),
            ("update_stage", "150", {"to": "Detailing"}, start + timedelta(minutes=30)),
        ]
        for action, release, payload, created in rel_events:
            db.session.add(ReleaseEvents(
                job=SEED_JOB, release=release, action=action, payload=payload,
                payload_hash=f"{SEED_TAG}-{action}-{SEED_JOB}-{release}", source="Trello",
                is_system_echo=False, created_at=created,
            ))

        db.session.add(SubmittalEvents(
            submittal_id=SEED_SUBMITTAL_ID, action="updated",
            payload={"status": {"old": "Open", "new": "Approved as Noted"},
                     "ball_in_court": {"old": "Architect", "new": "Mile High Metal Works"}},
            payload_hash=f"{SEED_TAG}-updated-{SEED_SUBMITTAL_ID}", source="Procore",
            is_system_echo=False, created_at=start + timedelta(minutes=15),
        ))
        db.session.commit()

        # 3. Fresh meeting (drop any prior seed run so re-running gives a clean slate).
        _delete_seed_meetings(db, Meeting, ChecklistItem, MeetingLearning)
        db.session.commit()

        meeting = Meeting(
            title=SEED_TITLE, meeting_type="gc_pm", source="manual",
            project_number=PROJECT, agenda_text=agenda, transcript=transcript,
            occurred_at=start, ended_at=end, extract_status="idle",
        )
        db.session.add(meeting)
        db.session.commit()

        print("✓ Seeded fake meeting fixture.")
        print(f"  meeting id    : {meeting.id}")
        print(f"  title         : {SEED_TITLE}")
        print(f"  project       : {PROJECT}  (releases {SEED_JOB}-146, {SEED_JOB}-150; submittal {SEED_SUBMITTAL_ID})")
        print(f"  window        : {start:%H:%M} – {end:%H:%M} UTC  (events stamped inside)")
        print(f"  agenda        : {len(agenda)} chars from wood_partners_agenda.md")
        print(f"  transcript    : {len(transcript)} chars from wood_partners_transcript.txt")
        print()
        print("Next: open the Meetings page, click into this meeting, and hit")
        print('"Generate to-do list" to run the live extraction + summary.')
        print(f"Teardown when done: ENVIRONMENT=$ENVIRONMENT python {os.path.relpath(__file__, ROOT_DIR)} --clean")
        return True


def main():
    parser = argparse.ArgumentParser(description="Seed (or clean) a fake meeting fixture.")
    parser.add_argument("--clean", action="store_true",
                        help="Remove the seed fixture instead of creating it.")
    args = parser.parse_args()

    if os.environ.get("ENVIRONMENT") == "production":
        print("✗ Refusing to touch production. Set ENVIRONMENT=sandbox (or local).")
        return False
    return clean() if args.clean else seed()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
