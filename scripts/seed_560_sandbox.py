"""Seed sandbox with the job-560 (Alta Metro) rows the lookahead cross-check needs.

Sandbox is a stale snapshot missing releases 923/941/910 and the open DRR 944 — without
them the GC Lookahead panel misreports. Row data below is the verified prod pull from
2026-07-20 (read-only session), embedded so this script needs NO prod credentials.

Idempotent: a row is inserted only if its key (release number / synthetic submittal_id)
is absent. Only columns that exist in the sandbox schema are written. Writes ONLY to
SANDBOX_DATABASE_URL — refuses to run against anything whose URL doesn't look sandbox.

Usage:
    .venv/bin/python scripts/seed_560_sandbox.py          # dry run (default)
    .venv/bin/python scripts/seed_560_sandbox.py --apply  # insert
"""
import os
import sys
from datetime import date

from dotenv import load_dotenv
import sqlalchemy as sa

APPLY = "--apply" in sys.argv
JOB = 560
JOB_NAME = "Wood Partners - Alta Metro Center"

# Prod snapshot 2026-07-20. Keys the app reads: _release_row + cross-check fields.
RELEASES = [
    dict(job=JOB, job_name=JOB_NAME, release="923", description="Bld C Structural Steel",
         stage="Released", stage_group="FABRICATION", fab_order=23.0,
         start_install=date(2026, 7, 24), comp_eta=date(2026, 7, 30), ship_date=None,
         install_hrs=64.61, job_comp=None, invoiced=None, is_active=True, is_archived=False),
    dict(job=JOB, job_name=JOB_NAME, release="941", description="Bld B Structrual Steel",
         stage="Released", stage_group="FABRICATION", fab_order=22.0,
         start_install=date(2026, 8, 28), comp_eta=date(2026, 9, 1), ship_date=date(2026, 8, 27),
         install_hrs=47.33, job_comp=None, invoiced=None, is_active=True, is_archived=False),
    dict(job=JOB, job_name=JOB_NAME, release="910", description="Additional base plates for missaligned Embeds",
         stage="Install Complete", stage_group="COMPLETE", fab_order=None,
         start_install=date(2026, 7, 9), comp_eta=date(2026, 7, 9), ship_date=None,
         install_hrs=0.0, job_comp="X", invoiced=None, is_active=True, is_archived=False),
]

# The open Building D DRR (rel 944) — the headline gap. submittal_id is synthetic
# (sandbox-only); prod's Procore id was not carried over, and nothing joins on it here.
SUBMITTALS = [
    dict(submittal_id="seed-560-944", project_number=str(JOB), project_name="Alta Metro Center",
         rel=944, title="Building D Structural Steel", type="Drafting Release Review",
         status="Open", submittal_drafting_status="STARTED", ball_in_court="Gary Almeida",
         due_date=None, start_install=None, order_number=0.7),
]


def columns_of(conn, table):
    rows = conn.execute(
        sa.text("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = 'public'"),
        {"t": table},
    ).fetchall()
    return {r[0] for r in rows}


def insert_missing(conn, table, rows, keycol, existing):
    cols = columns_of(conn, table)
    inserted = 0
    for row in rows:
        if row[keycol] in existing:
            print(f"  = {table} {keycol}={row[keycol]!r} already present")
            continue
        data = {k: v for k, v in row.items() if k in cols}
        skipped = sorted(set(row) - cols)
        print(f"  + {table} {keycol}={row[keycol]!r} {row.get('description') or row.get('title')!r}"
              + (f"  (skipping cols not in sandbox: {skipped})" if skipped else ""))
        if APPLY:
            names = ", ".join(data)
            vals = ", ".join(f":{k}" for k in data)
            conn.execute(sa.text(f"INSERT INTO {table} ({names}) VALUES ({vals})"), data)
            inserted += 1
    return inserted


def main():
    load_dotenv(".env")
    url = os.environ["SANDBOX_DATABASE_URL"]
    if "sandbox" not in url:
        raise SystemExit("Refusing: SANDBOX_DATABASE_URL does not look like a sandbox DB.")

    eng = sa.create_engine(url, connect_args={"sslmode": "require", "connect_timeout": 10})
    with eng.connect() as c:
        have_rel = {r[0] for r in c.execute(
            sa.text("SELECT release FROM releases WHERE job = :j"), {"j": JOB}).fetchall()}
        have_sub = {r[0] for r in c.execute(
            sa.text("SELECT submittal_id FROM submittals WHERE project_number = :p"),
            {"p": str(JOB)}).fetchall()}
        print(f"sandbox now: releases({len(have_rel)})={sorted(have_rel)}  submittals={len(have_sub)}")

        n = insert_missing(c, "releases", RELEASES, "release", have_rel)
        n += insert_missing(c, "submittals", SUBMITTALS, "submittal_id", have_sub)

        if APPLY:
            c.commit()
            print(f"APPLIED — {n} rows inserted.")
        else:
            print("Dry run — pass --apply to insert.")


if __name__ == "__main__":
    main()
