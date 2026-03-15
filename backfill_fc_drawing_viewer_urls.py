"""
Backfill viewer_url (FC Drawing link) for existing Releases that don't have one.

Instead of calling the Procore API 3+ times per record, this script batches calls:
  - company_id     : fetched once
  - project list   : fetched once, builds a job_number → project_id lookup
  - submittals     : fetched once per unique project, then filtered locally per release
  - workflow data  : fetched once per matching submittal (unavoidable per-item call)

Usage:
    python backfill_fc_drawing_viewer_urls.py
    python backfill_fc_drawing_viewer_urls.py --dry-run
    python backfill_fc_drawing_viewer_urls.py --job 1234
    python backfill_fc_drawing_viewer_urls.py --commit-every 50 --delay 0.5
"""
import argparse
import time
from collections import defaultdict

from app import create_app
from app.models import Releases, db
from app.config import Config as cfg
from app.procore.procore import (
    get_access_token,
    _request_json,
    _normalize_title,
    get_final_pdf_viewers,
)


def fetch_all_projects(company_id):
    """Fetch every Procore project in one call. Returns {job_number_str: project_id}."""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects?company_id={company_id}"
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Procore-Company-Id": str(company_id),
    }
    projects = _request_json(url, headers=headers) or []
    return {p["project_number"]: p["id"] for p in projects}


def fetch_all_submittals(project_id):
    """Fetch every submittal for a project in one call (unfiltered)."""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects/{project_id}/submittals"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    result = _request_json(url, headers=headers)
    return result if isinstance(result, list) else []


def submittals_for_release(all_submittals, job, release):
    """Filter a pre-fetched submittal list for a specific job-release identifier."""
    identifier = f"{job}-{release}".strip().lower()
    return [
        s for s in all_submittals
        if identifier in _normalize_title(s.get("title", ""))
        and s.get("type", {}).get("name") == "For Construction"
    ]


def run_backfill(dry_run=False, filter_job=None, commit_every=50, delay=0.25):
    app = create_app()
    with app.app_context():
        # ── 1. Load records ────────────────────────────────────────────────────
        query = db.session.query(Releases).filter(
            Releases.is_active == True,
            (Releases.viewer_url == None) | (Releases.viewer_url == '')
        )
        if filter_job is not None:
            query = query.filter(Releases.job == filter_job)
        records = query.all()
        print(f"Found {len(records)} release(s) without a viewer_url.\n")
        if not records:
            return

        # ── 2. Fetch company + all projects (2 API calls total) ────────────────
        print("Fetching Procore company ID…")
        company_id_url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.0/companies"
        companies = _request_json(company_id_url, headers={"Authorization": f"Bearer {get_access_token()}"}) or []
        if not companies:
            print("ERROR: No Procore companies returned. Aborting.")
            return
        company_id = companies[0]["id"]
        print(f"  company_id = {company_id}")

        print("Fetching all Procore projects…")
        project_map = fetch_all_projects(company_id)
        print(f"  {len(project_map)} projects loaded.\n")

        # ── 3. Group records by project_id ─────────────────────────────────────
        groups = defaultdict(list)   # project_id → [release_record, ...]
        no_project = []

        for record in records:
            pid = project_map.get(str(record.job))
            if pid:
                groups[pid].append(record)
            else:
                no_project.append(record)

        if no_project:
            print(f"WARNING: {len(no_project)} record(s) have no matching Procore project:")
            for r in no_project:
                print(f"  job={r.job} release={r.release}")
            print()

        # ── 4. Process each project group ──────────────────────────────────────
        updated = 0
        failed = 0
        pending_commit = 0

        for project_id, proj_records in groups.items():
            print(f"Project {project_id} — {len(proj_records)} release(s)")

            # One submittals fetch per project
            all_submittals = fetch_all_submittals(project_id)
            print(f"  {len(all_submittals)} total submittal(s) loaded for project.")
            if delay:
                time.sleep(delay)

            for record in proj_records:
                label = f"{record.job}-{record.release}"

                matching = submittals_for_release(all_submittals, record.job, record.release)
                if not matching:
                    print(f"  [SKIP] {label} — no matching 'For Construction' submittal")
                    failed += 1
                    continue

                # get_final_pdf_viewers calls get_workflow_data per submittal (unavoidable)
                final_pdfs = get_final_pdf_viewers(project_id, matching)
                if delay:
                    time.sleep(delay)

                if not final_pdfs:
                    print(f"  [SKIP] {label} — no Final PDF Pack found")
                    failed += 1
                    continue

                url = final_pdfs[0]["viewer_url"]
                short = url[:80] + ("…" if len(url) > 80 else "")
                print(f"  [OK]   {label} → {short}")

                if not dry_run:
                    record.viewer_url = url
                    pending_commit += 1

                    if pending_commit >= commit_every:
                        db.session.commit()
                        print(f"  — committed {pending_commit} record(s)")
                        pending_commit = 0

                updated += 1

        # ── 5. Final commit ────────────────────────────────────────────────────
        if not dry_run and pending_commit > 0:
            db.session.commit()
            print(f"\nFinal commit: {pending_commit} record(s).")

        print(f"\n{'DRY RUN — ' if dry_run else ''}Done.")
        print(f"  Updated : {updated}")
        print(f"  Skipped : {failed}")
        print(f"  No project: {len(no_project)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill FC Drawing viewer_url for existing Releases.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch URLs but do not write to the database.")
    parser.add_argument("--job", type=int, default=None, help="Only process releases for this job number.")
    parser.add_argument("--commit-every", type=int, default=50, metavar="N",
                        help="Commit to DB every N successful updates (default: 50).")
    parser.add_argument("--delay", type=float, default=0.25, metavar="SEC",
                        help="Seconds to sleep between Procore API calls (default: 0.25).")
    args = parser.parse_args()

    run_backfill(
        dry_run=args.dry_run,
        filter_job=args.job,
        commit_every=args.commit_every,
        delay=args.delay,
    )
