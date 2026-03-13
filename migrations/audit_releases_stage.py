"""
Audit releases table: compare releases.stage against jobs data.

This script:
1. Matches each release to its Job record by (job, release)
2. Compares releases.stage against job.trello_list_name (authoritative)
3. Also computes XO-derived stage from TrelloListMapper.determine_trello_list_from_db()
4. Reports mismatches in a tabular format
5. Optionally applies fixes (--apply)

Usage:
    # Preview all releases (match + mismatch)
    python migrations/audit_releases_stage.py --preview

    # Preview only mismatches
    python migrations/audit_releases_stage.py --preview --only-mismatches

    # Apply fixes to mismatched releases
    python migrations/audit_releases_stage.py --apply
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

sys.path.insert(0, ROOT_DIR)

load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url: str = None) -> str:
    candidates = [
        cli_url,
        os.environ.get("SANDBOX_DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
    ]

    for value in candidates:
        if not value:
            continue
        value = value.strip()
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql://", 1)
        if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
            return value
        return normalize_sqlite_path(value)

    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def _fmt(val, width):
    """Truncate and left-pad a value to fit column width."""
    s = str(val) if val is not None else ""
    if len(s) > width:
        s = s[: width - 1] + "…"
    return s.ljust(width)


def audit(database_url: str = None, apply: bool = False, only_mismatches: bool = False) -> bool:
    from app import create_app
    from app.models import Releases, Job, db
    from app.api.helpers import get_stage_group_from_stage
    from app.trello.list_mapper import TrelloListMapper

    app = create_app()

    with app.app_context():
        try:
            all_releases = Releases.query.order_by(Releases.job, Releases.release).all()
            total = len(all_releases)
            print(f"Auditing {total} releases...\n")

            # Build job lookup: (job, release) → Job
            all_jobs = Job.query.all()
            job_lookup = {(j.job, j.release): j for j in all_jobs}

            # Table header
            col_job      = 8
            col_rel      = 8
            col_current  = 22
            col_trello   = 22
            col_xo       = 22
            col_expected = 22
            col_match    = 8

            def header():
                print(
                    f"{'job'.ljust(col_job)} | "
                    f"{'release'.ljust(col_rel)} | "
                    f"{'current_stage'.ljust(col_current)} | "
                    f"{'trello_list_name'.ljust(col_trello)} | "
                    f"{'xo_derived'.ljust(col_xo)} | "
                    f"{'expected'.ljust(col_expected)} | "
                    f"{'match?'.ljust(col_match)}"
                )
                sep_width = col_job + col_rel + col_current + col_trello + col_xo + col_expected + col_match + 18
                print("-" * sep_width)

            rows_printed = 0

            # Counters
            matched_count          = 0
            mismatch_count         = 0
            mismatch_trello_source = 0
            mismatch_xo_source     = 0
            mismatch_default       = 0
            no_job_match_count     = 0

            rows = []

            for rel in all_releases:
                job = job_lookup.get((rel.job, rel.release))

                trello_stage = None
                xo_stage     = None

                if job:
                    if job.trello_list_name and job.trello_list_name.strip():
                        trello_stage = job.trello_list_name.strip()
                    try:
                        xo_stage = TrelloListMapper.determine_trello_list_from_db(job)
                    except Exception:
                        xo_stage = None
                else:
                    no_job_match_count += 1

                # Determine expected stage.
                # For fabrication-group stages the XO fields (cut_start, fitup_comp,
                # welded, etc.) are the ground truth, so XO is authoritative when it
                # returns a fabrication stage.  For all other stages (READY_TO_SHIP /
                # COMPLETE) Trello is the authoritative source.
                FABRICATION_STAGES = {
                    "Cut start",
                    "Fit Up Complete.",
                    "Welded",
                    "Released",
                }
                xo_is_fab = xo_stage in FABRICATION_STAGES

                if xo_is_fab:
                    # XO fields win for fabrication stages
                    expected_stage = xo_stage
                    source         = "xo"
                elif trello_stage:
                    expected_stage = trello_stage
                    source         = "trello"
                elif xo_stage:
                    # Non-fab XO stage with no trello fallback
                    expected_stage = xo_stage
                    source         = "xo"
                else:
                    expected_stage = "Released"
                    source         = "default"

                current_stage = rel.stage
                is_match = (current_stage == expected_stage)

                if is_match:
                    matched_count += 1
                else:
                    mismatch_count += 1
                    if source == "trello":
                        mismatch_trello_source += 1
                    elif source == "xo":
                        mismatch_xo_source += 1
                    else:
                        mismatch_default += 1

                rows.append({
                    "rel":            rel,
                    "trello_stage":   trello_stage,
                    "xo_stage":       xo_stage,
                    "expected_stage": expected_stage,
                    "source":         source,
                    "is_match":       is_match,
                })

            # Print table
            header()
            for r in rows:
                rel           = r["rel"]
                is_match      = r["is_match"]
                match_label   = "OK" if is_match else "MISMATCH"

                if only_mismatches and is_match:
                    continue

                print(
                    f"{_fmt(rel.job, col_job)} | "
                    f"{_fmt(rel.release, col_rel)} | "
                    f"{_fmt(rel.stage, col_current)} | "
                    f"{_fmt(r['trello_stage'], col_trello)} | "
                    f"{_fmt(r['xo_stage'], col_xo)} | "
                    f"{_fmt(r['expected_stage'], col_expected)} | "
                    f"{match_label.ljust(col_match)}"
                )
                rows_printed += 1

            if rows_printed == 0 and only_mismatches:
                print("(no mismatches to display)")

            # Summary
            print(f"\n=== Audit Summary ===")
            print(f"Total releases checked:          {total}")
            print(f"Matched (no change needed):      {matched_count}")
            print(f"Mismatched:                      {mismatch_count}")
            print(f"  - trello_list_name was source: {mismatch_trello_source}")
            print(f"  - xo_derived was fallback:     {mismatch_xo_source}")
            print(f"  - defaulted to 'Released':     {mismatch_default}")
            print(f"No matching Job record:          {no_job_match_count}")

            if not apply:
                print("\n(Preview mode — no changes written. Use --apply to fix mismatches.)")
                return True

            # Apply fixes
            if mismatch_count == 0:
                print("\nNothing to fix.")
                return True

            print(f"\nApplying fixes to {mismatch_count} mismatched releases...")
            fixed = 0
            errors = 0
            batch_size = 100
            mismatch_rows = [r for r in rows if not r["is_match"]]

            for batch_start in range(0, len(mismatch_rows), batch_size):
                batch = mismatch_rows[batch_start : batch_start + batch_size]
                for r in batch:
                    rel = r["rel"]
                    try:
                        old_stage       = rel.stage
                        old_stage_group = rel.stage_group
                        rel.stage       = r["expected_stage"]
                        sg              = get_stage_group_from_stage(r["expected_stage"])
                        rel.stage_group = sg if sg else "FABRICATION"
                        print(
                            f"  {rel.job}-{rel.release}: "
                            f"stage '{old_stage}' → '{rel.stage}', "
                            f"stage_group '{old_stage_group}' → '{rel.stage_group}'"
                        )
                        fixed += 1
                    except Exception as e:
                        print(f"  ERROR {rel.job}-{rel.release}: {e}")
                        errors += 1
                db.session.commit()

            print(f"\n=== Apply Summary ===")
            print(f"Fixed:  {fixed}")
            print(f"Errors: {errors}")

            return errors == 0

        except (OperationalError, ProgrammingError) as exc:
            print(f"Database error: {exc}")
            db.session.rollback()
            return False
        except Exception as exc:
            print(f"Unexpected error: {exc}")
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Audit releases.stage against jobs.trello_list_name and XO-derived stage."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preview",
        action="store_true",
        default=True,
        help="Print discrepancy table without writing anything (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Fix releases.stage and releases.stage_group for all mismatches.",
    )
    parser.add_argument(
        "--only-mismatches",
        action="store_true",
        default=False,
        help="In preview, hide rows that already match.",
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = audit(
        database_url=args.database_url,
        apply=args.apply,
        only_mismatches=args.only_mismatches,
    )
    sys.exit(0 if success else 1)
