"""
Full audit of DB releases against the Completed Job Log CSV.

Reports:
  1. Active (is_archived=False) releases found in the CSV (shouldn't still be active)
  2. Archived (is_archived=True) releases NOT in the CSV (no CSV backing)
  3. Archived releases IN the CSV — diff of Stage, Job Comp, and Invoiced

All archived releases should be: stage_group=COMPLETE, job_comp='X', invoiced='X'.

Usage:
    python audit_archive.py
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
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    app = create_app()

    with app.app_context():
        # --- Environment info ---
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        print("=" * 70)
        print("FULL ARCHIVE AUDIT — DB vs CSV")
        print("=" * 70)
        print(f"\n  Environment : {environment}")
        print(f"  Database URI: {redact_uri(db_uri)}")

        # --- Load CSV ---
        csv_data = load_csv(csv_path)
        csv_keys = set(csv_data.keys())
        print(f"  CSV entries : {len(csv_data):,} unique (job, release) pairs")

        # --- Load all DB releases (ignoring is_active) ---
        all_releases = Releases.query.all()
        archived = [r for r in all_releases if r.is_archived]
        active = [r for r in all_releases if not r.is_archived]
        print(f"\n  DB releases (all): {len(all_releases):,}")
        print(f"    Archived (is_archived=True):  {len(archived):,}")
        print(f"    Active (is_archived=False):   {len(active):,}")

        # Build lookup dicts
        archived_dict = {(r.job, r.release): r for r in archived}
        active_dict = {(r.job, r.release): r for r in active}

        # =====================================================================
        # SECTION 1: Active releases that appear in CSV
        # =====================================================================
        active_in_csv = [(r, csv_data[(r.job, r.release)])
                         for r in active
                         if (r.job, r.release) in csv_keys]

        print(f"\n{'=' * 70}")
        print(f"SECTION 1: Active (not archived) releases found in CSV ({len(active_in_csv)})")
        print(f"{'=' * 70}")
        if active_in_csv:
            print(
                f"  {'Job':<7} {'Rel':<7} {'Job Name':<30} {'Stage Group':<14} {'Description'}"
            )
            print(
                f"  {'---':<7} {'---':<7} {'--------':<30} {'-----------':<14} {'-----------'}"
            )
            for r, (csv_jc, csv_inv) in sorted(active_in_csv, key=lambda x: (x[0].job, x[0].release)):
                name = (r.job_name or "")[:28]
                group = (r.stage_group or "")[:12]
                desc = (r.description or "")[:40]
                print(f"  {r.job:<7} {r.release:<7} {name:<30} {group:<14} {desc}")
        else:
            print("  None — all active releases are absent from the CSV.")

        # =====================================================================
        # SECTION 2: Archived releases NOT in CSV
        # =====================================================================
        archived_keys = set(archived_dict.keys())
        suspects = archived_keys - csv_keys

        print(f"\n{'=' * 70}")
        print(f"SECTION 2: Archived releases NOT in CSV ({len(suspects)})")
        print(f"{'=' * 70}")
        if suspects:
            print(
                f"  {'Job':<7} {'Rel':<7} {'Job Name':<30} {'Stage Group':<14} {'Description'}"
            )
            print(
                f"  {'---':<7} {'---':<7} {'--------':<30} {'-----------':<14} {'-----------'}"
            )
            for key in sorted(suspects):
                r = archived_dict[key]
                name = (r.job_name or "")[:28]
                group = (r.stage_group or "")[:12]
                desc = (r.description or "")[:40]
                print(f"  {r.job:<7} {r.release:<7} {name:<30} {group:<14} {desc}")
        else:
            print("  None — all archived releases have CSV backing.")

        # =====================================================================
        # SECTION 3: Archived releases IN CSV — diff check
        # =====================================================================
        overlap_keys = archived_keys & csv_keys

        print(f"\n{'=' * 70}")
        print(f"SECTION 3: Archived + in CSV — Diff Check ({len(overlap_keys)} releases)")
        print(f"{'=' * 70}")

        # Analyze each overlapping release
        stage_ok = 0
        jc_ok = 0
        inv_ok = 0
        all_ok = 0
        mismatches = []

        for key in sorted(overlap_keys):
            r = archived_dict[key]
            csv_jc, csv_inv = csv_data[key]

            db_stage_group = (r.stage_group or "").strip()
            db_jc = (r.job_comp or "").strip()
            db_inv = (r.invoiced or "").strip()

            s_ok = db_stage_group == "COMPLETE"
            j_ok = db_jc == "X"
            i_ok = db_inv == "X"

            if s_ok:
                stage_ok += 1
            if j_ok:
                jc_ok += 1
            if i_ok:
                inv_ok += 1
            if s_ok and j_ok and i_ok:
                all_ok += 1
            else:
                mismatches.append((r, db_stage_group, db_jc, db_inv, csv_jc, csv_inv, s_ok, j_ok, i_ok))

        total = len(overlap_keys)
        print(f"\n  Summary ({total} archived releases with CSV match):")
        print(f"    Stage Group = COMPLETE:  {stage_ok:>4} / {total}  ({total - stage_ok} wrong)")
        print(f"    DB Job Comp = X:         {jc_ok:>4} / {total}  ({total - jc_ok} wrong)")
        print(f"    DB Invoiced = X:         {inv_ok:>4} / {total}  ({total - inv_ok} wrong)")
        print(f"    ALL THREE correct:       {all_ok:>4} / {total}  ({total - all_ok} need fixing)")

        # Detail table of mismatches
        if mismatches:
            print(f"\n{'—' * 70}")
            print(f"Mismatched releases ({len(mismatches)}):")
            print(f"{'—' * 70}")
            print(
                f"  {'Job':<7} {'Rel':<7} {'Job Name':<25} "
                f"{'DB Stage':<14} {'DB JC':<7} {'DB Inv':<7} "
                f"{'CSV JC':<7} {'CSV Inv':<7} {'Issues'}"
            )
            print(
                f"  {'---':<7} {'---':<7} {'--------':<25} "
                f"{'--------':<14} {'-----':<7} {'------':<7} "
                f"{'------':<7} {'-------':<7} {'------'}"
            )
            for r, db_sg, db_jc, db_inv, csv_jc, csv_inv, s_ok, j_ok, i_ok in mismatches:
                name = (r.job_name or "")[:23]
                issues = []
                if not s_ok:
                    issues.append("Stage")
                if not j_ok:
                    issues.append("JC")
                if not i_ok:
                    issues.append("Inv")
                issue_str = ", ".join(issues)
                print(
                    f"  {r.job:<7} {r.release:<7} {name:<25} "
                    f"{db_sg or '-':<14} {db_jc or '-':<7} {db_inv or '-':<7} "
                    f"{csv_jc or '-':<7} {csv_inv or '-':<7} {issue_str}"
                )

        # =====================================================================
        # Export CSV — mismatched rows only
        # =====================================================================
        out_path = os.path.join(os.path.dirname(__file__) or ".", "audit_archive.csv")
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Job", "Release", "Identifier", "Job Name", "Description",
                "DB Stage", "DB Stage Group",
                "DB Job Comp", "DB Invoiced",
                "CSV Job Comp", "CSV Invoiced",
                "Stage OK", "Job Comp OK", "Invoiced OK",
            ])
            for r, db_sg, db_jc, db_inv, csv_jc, csv_inv, s_ok, j_ok, i_ok in mismatches:
                writer.writerow([
                    r.job,
                    r.release,
                    f"{r.job}-{r.release}",
                    r.job_name or "",
                    r.description or "",
                    r.stage or "",
                    db_sg or "",
                    db_jc or "",
                    db_inv or "",
                    csv_jc or "",
                    csv_inv or "",
                    "Y" if s_ok else "N",
                    "Y" if j_ok else "N",
                    "Y" if i_ok else "N",
                ])
        print(f"\n  CSV exported: {out_path} ({len(mismatches)} rows)")
        print()


if __name__ == "__main__":
    main()
