"""Load the real 6/18 production standup transcript into sandbox and run the live
extraction + to-do MATCHING against the real releases/submittals already in that DB,
then print a match report.

This is the realistic test for the description-matching work: the 6/18 transcript is
dense with garbled, conversational job names ("Last Creek" → Sand Creek Flats, "Camp
Logan" → Logan, etc.), so it exercises fuzzy + Haiku matching against real candidates.

Safety:
  - Additive only: creates ONE Meeting + its ChecklistItems. Reads releases/submittals
    but never writes them. Idempotent on the meeting title (re-running resets it).
  - Refuses to run against production.

  ENVIRONMENT=sandbox python scripts/seed_prod_meeting.py             # seed + extract + report
  ENVIRONMENT=sandbox python scripts/seed_prod_meeting.py --seed-only # just load the meeting
  ENVIRONMENT=sandbox python scripts/seed_prod_meeting.py --report    # re-print last report, no LLM
  ENVIRONMENT=sandbox python scripts/seed_prod_meeting.py --clean     # remove the fixture
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

FIXTURE = os.path.join(ROOT_DIR, "tests", "brain", "fixtures",
                       "meeting_6_production_6_18.txt")
TITLE = "Production Standup — 6/18 [PROD-FIXTURE]"


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _get_meeting(Meeting):
    return Meeting.query.filter_by(title=TITLE).order_by(Meeting.id.desc()).first()


def _delete_meeting(db, Meeting, ChecklistItem):
    for old in Meeting.query.filter_by(title=TITLE).all():
        ChecklistItem.query.filter_by(meeting_id=old.id).delete()
        db.session.delete(old)
    db.session.commit()


def _candidate_pool(Releases, Submittals):
    """Mirror owner_match.build_candidates() scope: active releases (deduped to one per
    job) + open submittals. Just for a sanity readout of what matching can hit."""
    rel_jobs = {r.job for r in Releases.query.filter(Releases.is_archived.is_(False)).all()}
    subs = Submittals.query.filter(~Submittals.status.ilike("%closed%")).count()
    return len(rel_jobs), subs


def _report(db, Meeting, ChecklistItem, Releases, User):
    meeting = _get_meeting(Meeting)
    if not meeting:
        print("✗ No seeded meeting found. Run without --report first.")
        return False
    items = ChecklistItem.query.filter_by(meeting_id=meeting.id).order_by(
        ChecklistItem.id).all()
    users = {u.id: f"{u.first_name} {u.last_name}".strip() for u in User.query.all()}
    rel_label = {}
    for it in items:
        if it.release_id and it.release_id not in rel_label:
            r = db.session.get(Releases, it.release_id)
            rel_label[it.release_id] = f"{r.job}-{r.release}" if r else f"#{it.release_id}"

    n_rel = sum(1 for it in items if it.match_source == "release")
    n_sub = sum(1 for it in items if it.match_source == "submittal")
    n_none = sum(1 for it in items if not it.match_source)
    n_linked = sum(1 for it in items if it.release_id or it.submittal_id)

    print(f"\n{'='*78}\n  {TITLE}  (meeting id {meeting.id})")
    print(f"  {len(items)} to-dos · matched: {n_rel} release / {n_sub} submittal / "
          f"{n_none} none · {n_linked} hard-linked to a row")
    print(f"  extract model: {meeting.extract_model}  cost: "
          f"${meeting.extract_cost_usd or 0:.4f}\n{'='*78}")

    for it in items:
        src = it.match_source or "—"
        conf = f"{round((it.confidence or 0)*100)}%" if it.confidence is not None else "—"
        if it.match_source == "submittal":
            anchor = f"sub {it.submittal_id}"
        elif it.release_id:
            anchor = f"rel {rel_label.get(it.release_id)}"
        else:
            anchor = "(name only)" if it.matched_job_number else "—"
        owner = users.get(it.owner_user_id or it.proposed_owner_user_id, "—")
        flags = "".join(f for f, on in (
            (" 🔗linked", bool(it.release_id or it.submittal_id)),
            (" ✎name", it.name_corrected),
            (" ⚠drift", it.brain_update_pending),
            (" GC", it.gc_facing)) if on)
        print(f"\n  [{it.item_type}] {it.title}")
        print(f"      match: {src} · {it.matched_job_name or '—'} · {conf} · {anchor}")
        print(f"      owner: {owner}{' (inferred)' if it.owner_inferred else ''}{flags}")
    print()
    return True


def run(*, seed_only=False, report_only=False, clean=False):
    from app import create_app
    from app.models import (db, Meeting, ChecklistItem, Releases, Submittals, User)
    app = create_app()
    with app.app_context():
        if clean:
            _delete_meeting(db, Meeting, ChecklistItem)
            print(f"✓ Removed seeded meeting '{TITLE}'.")
            return True
        if report_only:
            return _report(db, Meeting, ChecklistItem, Releases, User)

        n_rel_jobs, n_subs = _candidate_pool(Releases, Submittals)
        print(f"Candidate pool in this DB: {n_rel_jobs} active jobs (releases), "
              f"{n_subs} open submittals.")
        if n_rel_jobs == 0:
            print("✗ No active releases here — matching has nothing to hit. "
                  "Populate releases (e.g. scripts/copy_releases_to_sandbox.py) first.")
            return False

        _delete_meeting(db, Meeting, ChecklistItem)
        now = datetime.utcnow()
        meeting = Meeting(
            title=TITLE, meeting_type="gc_pm", source="manual",
            project_number=None,            # multi-job standup: context seeds nothing, includes all
            transcript=_read(FIXTURE),
            occurred_at=now - timedelta(minutes=90), ended_at=now,
            extract_status="idle",
        )
        db.session.add(meeting)
        db.session.commit()
        print(f"✓ Seeded meeting id {meeting.id} ({len(meeting.transcript)} char transcript).")

        if seed_only:
            print("Seed-only: open it in the UI and click 'Generate to-do list', or "
                  "re-run without --seed-only.")
            return True

        from app.brain.meetings.service import extract_into_meeting
        print("Running live extraction + matching (real Opus call)…")
        created = extract_into_meeting(meeting, regenerate=True, notify=False)
        print(f"✓ Extracted {created} to-dos.")
        return _report(db, Meeting, ChecklistItem, Releases, User)


def main():
    p = argparse.ArgumentParser(description="Seed + extract the 6/18 prod meeting in sandbox.")
    p.add_argument("--seed-only", action="store_true", help="Load the meeting, don't extract.")
    p.add_argument("--report", action="store_true", help="Re-print the match report only.")
    p.add_argument("--clean", action="store_true", help="Remove the seeded meeting.")
    args = p.parse_args()
    if os.environ.get("ENVIRONMENT") == "production":
        print("✗ Refusing to touch production. Set ENVIRONMENT=sandbox.")
        return False
    return run(seed_only=args.seed_only, report_only=args.report, clean=args.clean)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
