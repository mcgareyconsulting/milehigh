"""
Check archived releases in the DB for data quality issues.

Finds archived releases missing Job Comp = 'X' and/or Invoiced = 'X',
and those archived in non-COMPLETE stage groups.

Usage:
    python check_archive_quality.py
"""
import csv
import os
import sys
from urllib.parse import urlparse, urlunparse

from app import create_app
from app.models import Releases, db


def redact_uri(uri):
    """Redact password from a database URI for safe logging."""
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


def load_csv(path):
    """Load (job, release) -> (job_comp, invoiced) from the Completed Job Log CSV."""
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    data = {}
    for row in rows[3:]:
        if not row or not row[0].strip():
            continue
        try:
            job_int = int(row[0].strip())
        except ValueError:
            continue
        release_str = row[1].strip()
        key = (job_int, release_str)
        if key not in data:
            job_comp = row[18].strip() if len(row) > 18 else ""
            invoiced = row[19].strip() if len(row) > 19 else ""
            data[key] = (job_comp, invoiced)
    return data


def main():
    csv_path = os.path.join(os.path.dirname(__file__) or ".", "archive-fix.csv")

    app = create_app()

    with app.app_context():
        # --- Environment info ---
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        print("=" * 70)
        print("ARCHIVE QUALITY CHECK")
        print("=" * 70)
        print(f"\n  Environment : {environment}")
        print(f"  Database URI: {redact_uri(db_uri)}")

        # --- Load CSV for cross-reference ---
        csv_data = {}
        if os.path.exists(csv_path):
            csv_data = load_csv(csv_path)
            print(f"  CSV loaded:   {len(csv_data):,} unique entries")

        # --- DB archived releases ---
        archived = Releases.query.filter_by(is_archived=True, is_active=True).all()
        print(f"\n{'—' * 70}")
        print("Archived Releases Breakdown")
        print(f"{'—' * 70}")
        print(f"  Total archived (is_archived=True): {len(archived):,}")

        # Group by stage_group
        by_group = {}
        for r in archived:
            group = r.stage_group or "UNKNOWN"
            by_group.setdefault(group, []).append(r)

        for group in sorted(by_group.keys()):
            print(f"    {group}: {len(by_group[group]):,}")

        # --- Check: archived but not COMPLETE stage_group ---
        not_complete = [r for r in archived if (r.stage_group or "") != "COMPLETE"]
        print(f"\n{'—' * 70}")
        print("Results")
        print(f"{'—' * 70}")
        print(f"  Archived in COMPLETE stage:     {len(archived) - len(not_complete):,}")
        print(f"  Archived NOT in COMPLETE stage:  {len(not_complete):,}  <-- PREMATURE")

        # --- Check: missing Job Comp or Invoiced in DB ---
        missing_data = []
        for r in archived:
            jc = (r.job_comp or "").strip()
            inv = (r.invoiced or "").strip()
            if jc != "X" or inv != "X":
                # Also grab CSV values for comparison
                csv_jc, csv_inv = csv_data.get((r.job, r.release), ("", ""))
                missing_data.append((r, jc, inv, csv_jc, csv_inv))

        print(f"  DB job_comp=X AND invoiced=X:    {len(archived) - len(missing_data):,}")
        print(f"  DB missing Job Comp or Invoiced:  {len(missing_data):,}  <-- INCOMPLETE")

        # --- Detail: premature archives ---
        if not_complete:
            print(f"\n{'=' * 70}")
            print(f"PREMATURE ARCHIVES — not in COMPLETE stage ({len(not_complete)})")
            print(f"{'=' * 70}")
            print(
                f"  {'Job':<7} {'Rel':<7} {'Job Name':<30} {'Stage':<22} {'Group':<14} {'JC':<6} {'Inv'}"
            )
            print(
                f"  {'---':<7} {'---':<7} {'--------':<30} {'-----':<22} {'-----':<14} {'--':<6} {'---'}"
            )
            for r in sorted(not_complete, key=lambda x: (x.stage_group or "", x.job, x.release)):
                jc = (r.job_comp or "").strip() or "-"
                inv = (r.invoiced or "").strip() or "-"
                name = (r.job_name or "")[:28]
                stage = (r.stage or "")[:20]
                group = (r.stage_group or "")[:12]
                print(
                    f"  {r.job:<7} {r.release:<7} {name:<30} {stage:<22} {group:<14} {jc:<6} {inv}"
                )

        # --- Export full CSV ---
        out_path = os.path.join(os.path.dirname(__file__) or ".", "archive_quality.csv")
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Job", "Release", "Identifier", "Job Name", "Description",
                "Stage", "Stage Group",
                "DB Job Comp", "DB Invoiced",
                "CSV Job Comp", "CSV Invoiced",
            ])
            for r, jc, inv, csv_jc, csv_inv in sorted(
                missing_data, key=lambda x: (x[0].stage_group or "", x[0].job, x[0].release)
            ):
                writer.writerow([
                    r.job,
                    r.release,
                    f"{r.job}-{r.release}",
                    r.job_name or "",
                    r.description or "",
                    r.stage or "",
                    r.stage_group or "",
                    jc,
                    inv,
                    csv_jc,
                    csv_inv,
                ])
        print(f"\n  CSV exported: {out_path} ({len(missing_data)} rows)")
        print()


if __name__ == "__main__":
    main()
