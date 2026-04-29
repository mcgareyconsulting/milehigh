"""
One-off script: refresh docs/jobsites.json from Procore.

Pulls every active Procore project's address, lat/lng, and Project Manager,
regenerates a circular geofence polygon for each (using the existing helper),
and rewrites docs/jobsites.json. Also upserts ProjectManager rows into the DB
so pm_id FKs in the JSON resolve cleanly.

Usage:
    .venv/bin/python -m scripts.refresh_jobsites_from_procore           # dry-run, prints diff
    .venv/bin/python -m scripts.refresh_jobsites_from_procore --apply   # writes JSON + commits PMs

After applying, load the new data via `app/ingest_jobsites.py`. Note that
ingest is currently insert-only (skips existing job_numbers); to update
existing rows you'll need to add an upsert flag to that script first.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app import create_app
from app.config import Config as cfg
from app.models import ProjectManager, db
from app.procore.client import get_procore_client
from app.brain.map.utils.geofence import generate_geofence_polygon

DEFAULT_RADIUS_METERS = 3218.68  # 2 miles
DEFAULT_PM_COLOR = "#888888"
JOBSITES_PATH = Path("docs/jobsites.json")

PM_ROLE_NAMES = {"project manager", "pm"}


def fetch_project_pm(procore, project_id: int) -> Optional[str]:
    """Best-effort PM lookup: try /projects/{id}/users and filter by project_role.
    Returns the PM's display name or None."""
    try:
        users = procore._get(f"/rest/v1.0/projects/{project_id}/users")
    except Exception as e:
        print(f"  ! PM lookup failed for project {project_id}: {e}", file=sys.stderr)
        return None

    if not isinstance(users, list):
        return None

    for u in users:
        role = (u.get("project_role") or u.get("role") or "").strip().lower()
        if role in PM_ROLE_NAMES:
            return (u.get("name") or f"{u.get('first_name','')} {u.get('last_name','')}").strip() or None
    return None


def upsert_pm(name: str, pm_cache: Dict[str, int], apply: bool) -> Optional[int]:
    """Resolve a PM name to a ProjectManager id, creating one if absent."""
    if not name:
        return None
    key = name.strip().lower()
    if key in pm_cache:
        return pm_cache[key]
    existing = ProjectManager.query.filter(db.func.lower(ProjectManager.name) == key).first()
    if existing:
        pm_cache[key] = existing.id
        return existing.id
    if not apply:
        print(f"  + would create ProjectManager '{name}'")
        return None
    pm = ProjectManager(name=name, color=DEFAULT_PM_COLOR)
    db.session.add(pm)
    db.session.flush()
    pm_cache[key] = pm.id
    print(f"  + created ProjectManager '{name}' (id={pm.id})")
    return pm.id


def build_address(p: Dict) -> Optional[str]:
    parts = [
        p.get("address"),
        p.get("city"),
        p.get("state_code") or p.get("state"),
        p.get("zip"),
    ]
    cleaned = [s.strip() for s in parts if s and isinstance(s, str) and s.strip()]
    return ", ".join(cleaned) if cleaned else None


def build_entry(
    procore_project: Dict,
    existing: Optional[Dict],
    pm_id: Optional[int],
) -> Tuple[Optional[Dict], List[str]]:
    """Returns (entry_or_None_if_skip, list_of_field_change_descriptions)."""
    job_number = str(procore_project.get("project_number") or "").strip()
    if not job_number:
        return None, [f"skipped: project {procore_project.get('id')} has no project_number"]

    name = procore_project.get("name") or (existing or {}).get("name") or job_number
    address = build_address(procore_project) or (existing or {}).get("address")

    lat = procore_project.get("latitude")
    lng = procore_project.get("longitude")
    if lat is None or lng is None:
        lat = (existing or {}).get("latitude")
        lng = (existing or {}).get("longitude")
    if lat is None or lng is None:
        return None, [f"skipped {job_number}: no lat/lng in Procore or existing JSON"]

    radius = (existing or {}).get("radius_meters") or DEFAULT_RADIUS_METERS
    polygon = generate_geofence_polygon(lat, lng, radius)

    final_pm_id = pm_id if pm_id is not None else (existing or {}).get("pm_id")

    entry = {
        "job_number": job_number,
        "name": name,
        "address": address,
        "latitude": lat,
        "longitude": lng,
        "pm_id": final_pm_id,
        "is_active": (existing or {}).get("is_active", True),
        "radius_meters": radius,
        "geofence_geojson": polygon,
        "geometry": polygon,
    }

    changes = []
    if existing is None:
        changes.append("NEW")
    else:
        for field in ("name", "address", "latitude", "longitude", "pm_id", "radius_meters"):
            if existing.get(field) != entry[field]:
                changes.append(f"{field}: {existing.get(field)!r} -> {entry[field]!r}")
        changes.append("polygon: regenerated")
    return entry, changes


def run(apply: bool):
    procore = get_procore_client()
    company_id = cfg.PROD_PROCORE_COMPANY_ID
    print(f"Fetching projects from Procore company_id={company_id}...")
    projects = procore.get_projects(company_id) or []
    print(f"  got {len(projects)} projects")

    existing_by_jn: Dict[str, Dict] = {}
    if JOBSITES_PATH.exists():
        with JOBSITES_PATH.open() as f:
            data = json.load(f)
        for site in data.get("jobsites", []):
            existing_by_jn[str(site["job_number"])] = site

    pm_cache: Dict[str, int] = {}
    new_jobsites: List[Dict] = []
    seen_job_numbers = set()

    for p in projects:
        if not p.get("active", True):
            continue
        job_number = str(p.get("project_number") or "").strip()
        if not job_number:
            continue
        seen_job_numbers.add(job_number)

        pm_name = fetch_project_pm(procore, p["id"])
        pm_id = upsert_pm(pm_name, pm_cache, apply) if pm_name else None

        entry, changes = build_entry(p, existing_by_jn.get(job_number), pm_id)
        if entry is None:
            print(f"  - {changes[0]}")
            continue

        tag = "NEW" if "NEW" in changes else ("CHANGED" if any(c != "polygon: regenerated" for c in changes) else "polygon-only")
        print(f"  [{tag}] {entry['job_number']} {entry['name']}")
        for c in changes:
            print(f"      {c}")
        new_jobsites.append(entry)

    # Preserve entries that exist in current JSON but not in Procore (manual additions).
    kept_manual = 0
    for jn, site in existing_by_jn.items():
        if jn not in seen_job_numbers:
            print(f"  [KEPT] {jn} {site.get('name')} (not in Procore)")
            new_jobsites.append(site)
            kept_manual += 1

    new_jobsites.sort(key=lambda e: e["job_number"])
    output = {"jobsites": new_jobsites}

    print()
    print(f"Summary: {len(seen_job_numbers)} from Procore, {kept_manual} manual kept, {len(new_jobsites)} total")

    if not apply:
        print("Dry-run: not writing JSON or committing PMs. Re-run with --apply.")
        db.session.rollback()
        return

    db.session.commit()
    JOBSITES_PATH.write_text(json.dumps(output, indent=2))
    print(f"Wrote {JOBSITES_PATH} ({len(new_jobsites)} entries)")
    print("Next: load via app/ingest_jobsites.py (insert-only; add upsert flag for updates).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write JSON and commit ProjectManager rows. Default is dry-run.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        run(apply=args.apply)


if __name__ == "__main__":
    main()
