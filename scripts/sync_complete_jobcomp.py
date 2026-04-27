"""
Reconcile drift between Stage and Job Comp on releases.

Rule: Stage='Complete' iff job_comp='X'.

What this script does:
  - Bucket 3a (auto-fix): Stage='Complete' but job_comp != 'X' →
    set job_comp='X'. Stage is treated as authoritative.
  - Bucket 3b (manual review only): job_comp='X' but Stage != 'Complete' →
    write to CSV, do NOT auto-promote stage. Promoting stage has Trello sync
    side effects, so the user reviews each case by hand.

Dry-run by default. Pass --commit to apply 3a changes.

Usage:
    python scripts/sync_complete_jobcomp.py            # dry-run
    python scripts/sync_complete_jobcomp.py --commit   # apply 3a fixes
"""
import csv
import os
import sys
from urllib.parse import urlparse, urlunparse

# Allow running as `python scripts/sync_complete_jobcomp.py` from project root.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import or_

from app import create_app
from app.models import Releases, db


COMPLETE_VARIANTS = ["Complete"]


def redact_uri(uri):
    try:
        parsed = urlparse(uri)
        if parsed.password:
            replaced = parsed._replace(
                netloc=f"{parsed.username}:***@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(replaced)
    except Exception:
        pass
    return uri


def active_filter():
    return (
        (Releases.is_archived == False)  # noqa: E712
        & ((Releases.is_active == True) | (Releases.is_active.is_(None)))  # noqa: E712
    )


def is_x(job_comp):
    return (job_comp or "").strip().upper() == "X"


def main():
    commit = "--commit" in sys.argv
    mode = "COMMIT" if commit else "DRY-RUN"

    app = create_app()
    with app.app_context():
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis")
        out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)

        print("=" * 70)
        print(f"SYNC STAGE / JOB COMP — {mode}")
        print("=" * 70)
        print(f"  Environment : {environment}")
        print(f"  Database URI: {redact_uri(db_uri)}")

        # Bucket 3a: stage=Complete but job_comp != 'X' → auto-fix
        candidates_3a = (
            Releases.query
            .filter(active_filter())
            .filter(Releases.stage.in_(COMPLETE_VARIANTS))
            .all()
        )
        b3a = [r for r in candidates_3a if not is_x(r.job_comp)]

        print("\n" + "-" * 70)
        print(f"[3a] stage=Complete, job_comp != 'X'  —  count: {len(b3a)}")
        print("    action: set job_comp = 'X'")
        for r in b3a[:20]:
            print(f"    {r.job}-{r.release:<6} stage={r.stage!r} job_comp={r.job_comp!r} -> 'X'")
        if len(b3a) > 20:
            print(f"    ... ({len(b3a) - 20} more)")

        if commit and b3a:
            for r in b3a:
                r.job_comp = "X"
            db.session.commit()
            print(f"\n  COMMITTED: updated job_comp on {len(b3a)} release(s)")
        elif b3a:
            db.session.rollback()
            print("\n  DRY-RUN: no changes written (use --commit to apply)")

        # Bucket 3b: job_comp='X' but stage != Complete → CSV only, no auto-fix
        candidates_3b = (
            Releases.query
            .filter(active_filter())
            .filter(or_(Releases.stage.notin_(COMPLETE_VARIANTS), Releases.stage.is_(None)))
            .all()
        )
        b3b = [r for r in candidates_3b if is_x(r.job_comp)]

        b3b_csv = os.path.join(out_dir, "jobcomp_x_without_complete.csv")
        with open(b3b_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["job", "release", "pm", "stage", "stage_group", "fab_order", "job_comp", "invoiced"])
            for r in b3b:
                w.writerow([r.job, r.release, r.pm, r.stage, r.stage_group, r.fab_order, r.job_comp, r.invoiced])

        print("\n" + "-" * 70)
        print(f"[3b] job_comp='X', stage != Complete  —  count: {len(b3b)}")
        print("    action: NONE (manual review — Trello sync side effects)")
        print(f"    wrote: {b3b_csv}")
        for r in b3b[:20]:
            print(f"    {r.job}-{r.release:<6} stage={r.stage!r} job_comp={r.job_comp!r}")
        if len(b3b) > 20:
            print(f"    ... ({len(b3b) - 20} more)")

        print("\n" + "=" * 70)
        print(f"Summary ({mode})")
        print("=" * 70)
        print(f"  [3a] auto-fixed (or would fix): {len(b3a)}")
        print(f"  [3b] surfaced for manual review: {len(b3b)}")


if __name__ == "__main__":
    main()
