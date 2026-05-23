"""
Migrate rows with stage='Welded' to stage='Weld Complete'.

The plain 'Welded' stage is being retired because it is redundant with the more
specific 'Weld Start' / 'Weld Complete' / 'Welded QC' stages. 'Weld Complete'
carries the same 10% remaining-fab percentage and FABRICATION group as the
old 'Welded', so migrated rows preserve their KPI contribution.

Usage:
    python migrations/drop_welded_stage.py --dry-run
    python migrations/drop_welded_stage.py

The script is idempotent and safe to run multiple times.
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


OLD_STAGE = "Welded"
NEW_STAGE = "Weld Complete"
TARGET_STAGE_GROUP = "FABRICATION"


def migrate(dry_run: bool = False) -> bool:
    """Update stage='Welded' → 'Weld Complete' on the Releases table."""
    from app import create_app
    from app.models import Releases, db

    app = create_app()

    with app.app_context():
        try:
            jobs_to_update = Releases.query.filter(Releases.stage == OLD_STAGE).all()
            total = len(jobs_to_update)
            print(f"Found {total} jobs with stage='{OLD_STAGE}'.")

            if total == 0:
                print("✓ Nothing to migrate.")
                return True

            for job in jobs_to_update:
                print(
                    f"  {'[dry-run] ' if dry_run else ''}"
                    f"job {job.job}-{job.release}: "
                    f"stage '{job.stage}' → '{NEW_STAGE}', "
                    f"stage_group '{job.stage_group}' → '{TARGET_STAGE_GROUP}'"
                )
                if not dry_run:
                    job.stage = NEW_STAGE
                    job.stage_group = TARGET_STAGE_GROUP

            if dry_run:
                print(f"\n✓ Dry-run complete. {total} jobs would be updated.")
                db.session.rollback()
                return True

            db.session.commit()
            print(f"\n✓ Successfully migrated {total} jobs.")
            return True

        except (OperationalError, ProgrammingError) as exc:
            print(f"✗ Database error: {exc}")
            db.session.rollback()
            return False
        except Exception as exc:
            print(f"✗ Unexpected error: {exc}")
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate stage='Welded' to stage='Weld Complete' on Releases."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without committing.",
    )
    args = parser.parse_args()

    success = migrate(dry_run=args.dry_run)
    sys.exit(0 if success else 1)
