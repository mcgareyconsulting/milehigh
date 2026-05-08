"""
Migration: Canonicalize Releases.stage values.

Collapses every legacy stage variant in the releases table to its canonical
name as defined in app/api/helpers.py STAGE_TO_GROUP. Also merges 'Store at
Shop' into 'Store at MHMW' (lossy — the distinction is gone post-migration).

The new canonical names are:
    Released, Material Ordered, Cut Start, Cut Complete, Fitup Start,
    Fitup Complete, Weld Start, Weld Complete, Hold, Welded QC, Paint Start,
    Paint Complete, Store at MHMW, Ship Planning, Ship Complete,
    Install Start, Install Complete, Complete.

Usage:
    python migrations/canonicalize_release_stages.py            # dry-run, prints counts
    python migrations/canonicalize_release_stages.py --apply    # commit the rename

Idempotent: re-running after --apply is a no-op (counts will be zero).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db, Releases


# Old stage value → canonical replacement. Keys come from a sweep of the
# codebase pre-canonicalization (helpers.py STAGE_TO_GROUP, list_mapper.py,
# scheduling/config.py, hours_summary.py, frontend hooks, seed.py).
STAGE_RENAMES = {
    "Cut start":                  "Cut Start",
    "Fit Up Complete.":           "Fitup Complete",
    "Fit Up Complete":            "Fitup Complete",
    "Fit up Comp":                "Fitup Complete",
    "Fitup comp":                 "Fitup Complete",
    "Paint complete":             "Paint Complete",
    "Paint comp":                 "Paint Complete",
    "Store at Shop":              "Store at MHMW",
    "Store at MHMW for shipping": "Store at MHMW",
    "Shipping planning":          "Ship Planning",
    "Shipping Planning":          "Ship Planning",
    "Shipping completed":         "Ship Complete",
    "Shipping Complete":          "Ship Complete",
    "WeldingQC":                  "Welded QC",
    "Welding QC":                 "Welded QC",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the rename. Without this flag the script is read-only.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        # Step 1: report counts for each old variant present in the table.
        rows = (
            db.session.query(Releases.stage, db.func.count(Releases.id))
            .group_by(Releases.stage)
            .all()
        )
        existing_counts = {stage: count for stage, count in rows}

        # Canonical names from STAGE_TO_GROUP — knowing these lets us label
        # leftover values as "already canonical" vs. truly unknown.
        from app.api.helpers import STAGE_TO_GROUP
        canonical_names = set(STAGE_TO_GROUP.keys())

        rename_plan = []
        already_canonical = []
        unknown = []
        for stage, count in sorted(existing_counts.items(), key=lambda kv: (kv[0] or "")):
            if stage in STAGE_RENAMES:
                rename_plan.append((stage, STAGE_RENAMES[stage], count))
            elif stage in canonical_names:
                already_canonical.append((stage, count))
            elif stage is not None:
                unknown.append((stage, count))

        print("Releases.stage canonicalization")
        print("=" * 60)
        if rename_plan:
            print(f"\nRenames ({sum(c for _, _, c in rename_plan)} rows total):")
            for old, new, count in rename_plan:
                print(f"  {count:>5}  {old!r:<32} -> {new!r}")
        else:
            print("\nNo legacy variants found — table is already canonical.")

        if already_canonical:
            print(f"\nAlready canonical ({sum(c for _, c in already_canonical)} rows, no change):")
            for stage, count in sorted(already_canonical):
                print(f"  {count:>5}  {stage!r}")

        if unknown:
            print("\nUNKNOWN stage values (not in STAGE_TO_GROUP, left untouched — investigate):")
            for stage, count in sorted(unknown):
                print(f"  {count:>5}  {stage!r}")

        if not rename_plan:
            return

        if not args.apply:
            print("\nDry-run. Re-run with --apply to commit.")
            return

        # Step 2: apply renames in a single transaction. Bulk UPDATE per
        # mapping; PostgreSQL plans this efficiently with an index on stage.
        for old, new, _ in rename_plan:
            (
                db.session.query(Releases)
                .filter(Releases.stage == old)
                .update({Releases.stage: new}, synchronize_session=False)
            )
        db.session.commit()
        print(f"\nApplied {len(rename_plan)} rename(s). Commit complete.")


if __name__ == "__main__":
    main()
