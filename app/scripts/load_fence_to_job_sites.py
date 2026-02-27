"""
Load a GeoJSON fence file into the job_sites table.

Expects a FeatureCollection with at least one Feature that has:
  - geometry: { "type": "Polygon", "coordinates": [...] }
  - properties.name: display name (optional; can override with --name)

Usage:
  python -m app.scripts.load_fence_to_job_sites fences/lalas_fence.json 400
  python -m app.scripts.load_fence_to_job_sites fences/mhmw_fence.json 000
  python -m app.scripts.load_fence_to_job_sites fences/mhmw_fence.json 401 --name "MHMW Site"
"""

import argparse
import json
import sys
from typing import Optional


def load_fence_file(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def extract_feature_parts(data: dict):
    """Get (geometry, name) from first feature in a GeoJSON FeatureCollection."""
    features = data.get("features") or []
    if not features:
        raise ValueError("GeoJSON has no features")
    feat = features[0]
    geom = feat.get("geometry")
    if not geom or geom.get("type") != "Polygon":
        raise ValueError("First feature must have geometry.type Polygon")
    name = (feat.get("properties") or {}).get("name") or "Unnamed site"
    return geom, name


def insert_fence(path: str, job_number: str, name_override: Optional[str] = None):
    data = load_fence_file(path)
    geometry, name = extract_feature_parts(data)
    name = name_override or name

    from app import create_app
    from app.models import Jobs, db

    app = create_app()
    with app.app_context():
        existing = Jobs.query.filter_by(job_number=job_number).first()
        if existing:
            print(f"Job number {job_number} already has a site: {existing.name} (id={existing.id})")
            print("Update or delete it first, or use a different job_number.")
            return 1

        site = Jobs(
            name=name,
            job_number=job_number,
            geometry=geometry,
            is_active=True,
        )
        db.session.add(site)
        db.session.commit()
        print(f"Inserted job_site id={site.id} name={name!r} job_number={job_number}")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Load a GeoJSON fence into job_sites",
        epilog="Example: python -m app.scripts.load_fence_to_job_sites fences/lalas_fence.json 400",
    )
    parser.add_argument("file", help="Path to GeoJSON fence file (FeatureCollection)")
    parser.add_argument("job_number", type=str, help="Job number (e.g. 400 or 000) for this site")
    parser.add_argument("--name", default=None, help="Override site name from GeoJSON properties")
    args = parser.parse_args()
    return insert_fence(args.file, args.job_number, args.name)


if __name__ == "__main__":
    sys.exit(main())
