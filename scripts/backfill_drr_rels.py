"""
One-off backfill: assign specific Rel numbers to existing DRR submittals.

Each target is pinned to an EXACT submittal_id (resolved by hand from the
provided spreadsheet against production data), so the write path does no fuzzy
title matching. Before writing, every target is verified:
  * the submittal exists,
  * its project_number matches the spreadsheet Job #,
  * its type is exactly "Drafting Release Review" (DRR),
  * it currently has rel = None (won't silently overwrite),
  * the Rel number isn't already held by another submittal.

Dry-run by default. Pass --apply to write.

Usage:
    ENVIRONMENT=sandbox    PYTHONPATH=. python3 scripts/backfill_drr_rels.py
    ENVIRONMENT=production PYTHONPATH=. python3 scripts/backfill_drr_rels.py
    ENVIRONMENT=production PYTHONPATH=. python3 scripts/backfill_drr_rels.py --apply
"""
import os
import sys
from datetime import datetime

from app import create_app
from app.models import Submittals

DRR_TYPE = "Drafting Release Review"

# (job_number, rel, submittal_id, spreadsheet_title)  — resolved against prod.
# submittal_id=None means intentionally skipped (see SKIPS for the reason).
PLAN = [
    ("580", 659, "72129532", "Stair Core 1 -> 'Stair Core 01'"),
    ("500", 224, "69826314", "Garage Entry Steel (newer of 2 closed DRRs)"),
    ("480", 618, "68447032", "Stair Core 5"),
    ("480", 675, "72199053", "Stair Core 1 (Open DRR)"),
    ("580", 676, "72208163", "Stair Core 2 -> 'Stair Core 02'"),
    ("480", 679, "71999616", "Area 3 Stuctural stuff -> 'Area 3 Structural Remaining upper level steel' (Open DRR)"),
    ("500", 671, "72360453", "Stair 02 Vestibule Canopy (Open DRR of 3)"),
    ("480", 678, "72016722", "RFI 93 P6 Deck Assembly L1 Trash -> 'RFI #93: P6 Deck Assembly L1 Trash'"),
    ("410", 670, "72419422", "RFI 353 Steel Column Design Bust"),
    ("410", 669, "72418903", "RFI 352 Sprinkler Penetration Plates"),
    ("530", 661, "72375130", "Ange Iron Ledger Change Order -> 'Angle Iron Ledger Change order'"),
    ("590", 680, None, "Bld 2E Stair Core"),
    ("590", 681, None, "Bld 2W Stair Core"),
]

SKIPS = {
    680: "No East submittal exists on job 590; only one 'Building #2 Stair Cores' DRR (71659480).",
    681: "No West submittal exists on job 590; only one 'Building #2 Stair Cores' DRR (71659480).",
}


def main():
    apply = "--apply" in sys.argv

    app = create_app()
    with app.app_context():
        from app import db

        db_host = app.config.get("SQLALCHEMY_DATABASE_URI", "").split("@")[-1]
        env = os.environ.get("ENVIRONMENT", "?")
        print("=" * 100)
        print(f"ENVIRONMENT={env}  DB={db_host}")
        print(f"MODE={'APPLY (writing)' if apply else 'DRY RUN (no writes)'}")
        print("=" * 100)

        # Existing holders of any target rel (collision guard).
        target_rels = {rel for _, rel, sid, _ in PLAN if sid is not None}
        holders = {}
        for s in Submittals.query.filter(Submittals.rel.in_(target_rels)).all():
            holders.setdefault(s.rel, []).append(s)

        ready = []     # (rel, submittal) safe to write
        blocked = []   # (rel, reason)
        skipped = []   # (rel, reason)

        for job, rel, sid, note in PLAN:
            if sid is None:
                reason = SKIPS.get(rel, "intentionally skipped")
                skipped.append((rel, reason))
                print(f"\n[{job} / rel {rel}] {note}\n    SKIP — {reason}")
                continue

            sub = Submittals.query.filter_by(submittal_id=sid).first()
            print(f"\n[{job} / rel {rel}] {note}")
            if sub is None:
                blocked.append((rel, f"submittal {sid} not found"))
                print(f"    BLOCKED — submittal {sid} not found")
                continue

            print(f"    sub={sub.submittal_id} type={sub.type!r} status={sub.status!r} "
                  f"job={sub.project_number} current_rel={sub.rel} | {sub.title!r}")

            problems = []
            if (sub.type or "").strip() != DRR_TYPE:
                problems.append(f"type is {sub.type!r}, not DRR")
            if str(sub.project_number) != str(job):
                problems.append(f"job mismatch: row={job} db={sub.project_number}")
            if sub.rel is not None and sub.rel != rel:
                problems.append(f"already has rel={sub.rel}")
            other_holders = [h for h in holders.get(rel, []) if h.submittal_id != sid]
            if other_holders:
                hd = "; ".join(f"{h.submittal_id}({h.project_number}:{h.title!r})" for h in other_holders)
                problems.append(f"rel {rel} already held by {hd}")

            if problems:
                blocked.append((rel, "; ".join(problems)))
                print(f"    BLOCKED — {'; '.join(problems)}")
            elif sub.rel == rel:
                print(f"    OK — already set to {rel} (no-op)")
            else:
                ready.append((rel, sub))
                print(f"    READY — will set rel = {rel}")

        print("\n" + "=" * 100)
        print(f"SUMMARY: {len(ready)} ready, {len(skipped)} skipped, {len(blocked)} blocked "
              f"(of {len(PLAN)} rows)")
        for rel, reason in skipped:
            print(f"  SKIP  rel {rel}: {reason}")
        for rel, reason in blocked:
            print(f"  BLOCK rel {rel}: {reason}")

        if apply:
            if blocked:
                print("\nREFUSING TO APPLY — resolve blocked rows first.")
                return
            for rel, sub in ready:
                sub.rel = rel
                sub.rel_assigned_at = datetime.utcnow()
            db.session.commit()
            print(f"\nAPPLIED: {len(ready)} submittal(s) updated and committed.")
        else:
            print("\nDRY RUN — no changes written. Re-run with --apply to commit.")


if __name__ == "__main__":
    main()
