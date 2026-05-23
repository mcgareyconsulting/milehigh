"""
Dry-run analysis of release fab_order / Stage / Job Comp drift.

Reports three buckets, writes one CSV per bucket under analysis/, and prints
counts + a small sample to stdout. Read-only — no DB writes.

Buckets:
  1. fab_order on Complete:
       stage = 'Complete' AND fab_order IS NOT NULL
       (rule: Complete releases should have NO fab_order)
  2. Wrong fab_order on Shipping completed:
       stage IN ('Shipping completed', 'Shipping Complete') AND
       (fab_order IS NULL OR fab_order != 1)
       (rule: Shipping completed should be fab_order = 1)
  3. Stage / Job Comp out of sync:
       3a. stage = 'Complete' AND (job_comp IS NULL or trimmed-upper != 'X')
       3b. UPPER(TRIM(job_comp)) = 'X' AND stage != 'Complete'

Working set matches migrate_unified.py: is_archived != True AND
(is_active = True OR is_active IS NULL).

Usage:
    python analysis/analyze_complete_fab_order.py
"""
import csv
import os
import sys
from urllib.parse import urlparse, urlunparse

# Allow running as `python analysis/analyze_complete_fab_order.py` from project root.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import or_

from app import create_app
from app.models import Releases, db


COMPLETE_VARIANTS = ["Complete"]
SHIPPING_COMPLETE_VARIANTS = ["Shipping completed", "Shipping Complete"]


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


def write_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def row_dict(r):
    return {
        "job": r.job,
        "release": r.release,
        "pm": r.pm,
        "stage": r.stage,
        "stage_group": r.stage_group,
        "fab_order": r.fab_order,
        "job_comp": r.job_comp,
        "invoiced": r.invoiced,
    }


def print_sample(label, rows, n=10):
    print(f"\n  Sample (first {min(n, len(rows))}):")
    for r in rows[:n]:
        print(
            f"    {r['job']}-{r['release']:<6} "
            f"stage={r['stage']!r:<22} "
            f"fab_order={r['fab_order']!s:<8} "
            f"job_comp={r['job_comp']!r}"
        )


def main():
    app = create_app()
    with app.app_context():
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        out_dir = os.path.dirname(os.path.abspath(__file__))

        print("=" * 70)
        print("RELEASE DRIFT ANALYSIS — DRY RUN (read-only)")
        print("=" * 70)
        print(f"  Environment : {environment}")
        print(f"  Database URI: {redact_uri(db_uri)}")
        print(f"  Output dir  : {out_dir}")

        fields = [
            "job", "release", "pm", "stage", "stage_group",
            "fab_order", "job_comp", "invoiced",
        ]

        # Bucket 1: fab_order on Complete
        b1 = (
            Releases.query
            .filter(active_filter())
            .filter(Releases.stage.in_(COMPLETE_VARIANTS))
            .filter(Releases.fab_order.isnot(None))
            .order_by(Releases.job.asc(), Releases.release.asc())
            .all()
        )
        b1_rows = [row_dict(r) for r in b1]
        print("\n" + "-" * 70)
        print(f"[1] fab_order on Complete  —  count: {len(b1_rows)}")
        print("    rule: stage='Complete' should have fab_order = NULL")
        if b1_rows:
            print_sample("b1", b1_rows)
        b1_csv = os.path.join(out_dir, "complete_fab_order_drift.csv")
        write_csv(b1_csv, b1_rows, fields)
        print(f"  wrote: {b1_csv}")

        # Bucket 2: wrong fab_order on Shipping completed
        b2 = (
            Releases.query
            .filter(active_filter())
            .filter(Releases.stage.in_(SHIPPING_COMPLETE_VARIANTS))
            .filter(or_(Releases.fab_order.is_(None), Releases.fab_order != 1))
            .order_by(Releases.job.asc(), Releases.release.asc())
            .all()
        )
        b2_rows = [row_dict(r) for r in b2]
        print("\n" + "-" * 70)
        print(f"[2] Wrong fab_order on Shipping completed  —  count: {len(b2_rows)}")
        print("    rule: stage in ('Shipping completed','Shipping Complete') -> fab_order = 1")
        if b2_rows:
            print_sample("b2", b2_rows)
        b2_csv = os.path.join(out_dir, "shipping_fab_order_drift.csv")
        write_csv(b2_csv, b2_rows, fields)
        print(f"  wrote: {b2_csv}")

        # Bucket 3: Stage / Job Comp out of sync.
        # SQL TRIM/UPPER varies by dialect, so filter in Python after a coarse
        # candidate query. Working sets are small enough.
        candidates_3a = (
            Releases.query
            .filter(active_filter())
            .filter(Releases.stage.in_(COMPLETE_VARIANTS))
            .all()
        )
        b3a_rows = [row_dict(r) for r in candidates_3a if not is_x(r.job_comp)]

        candidates_3b = (
            Releases.query
            .filter(active_filter())
            .filter(or_(Releases.stage.notin_(COMPLETE_VARIANTS), Releases.stage.is_(None)))
            .all()
        )
        b3b_rows = [row_dict(r) for r in candidates_3b if is_x(r.job_comp)]

        print("\n" + "-" * 70)
        print(f"[3a] Complete but Job Comp != X  —  count: {len(b3a_rows)}")
        print("    rule: stage='Complete' should have job_comp='X'")
        if b3a_rows:
            print_sample("b3a", b3a_rows)
        print(f"\n[3b] Job Comp = X but stage != Complete  —  count: {len(b3b_rows)}")
        print("    rule: job_comp='X' should imply stage='Complete'")
        if b3b_rows:
            print_sample("b3b", b3b_rows)

        b3_combined = []
        for r in b3a_rows:
            d = dict(r); d["drift_kind"] = "complete_missing_jobcomp_x"
            b3_combined.append(d)
        for r in b3b_rows:
            d = dict(r); d["drift_kind"] = "jobcomp_x_without_complete"
            b3_combined.append(d)
        b3_csv = os.path.join(out_dir, "stage_jobcomp_sync_drift.csv")
        write_csv(b3_csv, b3_combined, fields + ["drift_kind"])
        print(f"\n  wrote: {b3_csv}")

        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"  [1] fab_order on Complete           : {len(b1_rows)}")
        print(f"  [2] wrong fab_order on Shipping     : {len(b2_rows)}")
        print(f"  [3a] Complete missing Job Comp = X  : {len(b3a_rows)}")
        print(f"  [3b] Job Comp = X w/o Complete      : {len(b3b_rows)}")


if __name__ == "__main__":
    main()
