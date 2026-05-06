"""
@milehigh-header
schema_version: 1
purpose: Expose admin-only endpoints for geofence regeneration and Procore project onboarding.
exports:
  admin_bp: Flask blueprint registered at /admin with admin-only routes
  regenerate_geofences: POST endpoint to rebuild all jobsite geofence polygons
  add_project_preview: POST endpoint to preview Procore project submittals before import
  add_project_confirm: POST endpoint to create webhook and sync submittals for a Procore project
imports_from: [flask, app.models, app.auth.utils, app.brain.map.utils.geofence, app.logging_config, app.route_utils, app.procore.client, app.procore.procore]
imported_by: [app/__init__.py]
invariants:
  - All routes require @admin_required; removing it exposes destructive operations to non-admins
  - add_project_confirm uses lazy imports for create_webhook_and_trigger and sync_submittals_for_project to avoid circular imports
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
import os

from flask import Blueprint, current_app, jsonify, request, g
from app.models import Projects, ReleaseDrawingVersion, db
from app.auth.utils import admin_required
from app.brain.map.utils.geofence import generate_geofence_polygon
from app.brain.job_log.features.pdf_markup.storage import absolute_path
from app.logging_config import get_logger
from app.route_utils import handle_errors, require_json
from app.procore.client import get_procore_client
from app.procore.procore import get_project_info

logger = get_logger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route('/jobsites/regenerate-geofences', methods=['POST'])
@admin_required
@handle_errors("regenerate geofences")
def regenerate_geofences():
    """Regenerate geofence polygons for all jobsites and persist to the database."""
    projects = Projects.query.filter(
        Projects.latitude.isnot(None),
        Projects.longitude.isnot(None),
        Projects.radius_meters.isnot(None),
    ).all()
    for project in projects:
        project.geofence_geojson = generate_geofence_polygon(
            project.latitude,
            project.longitude,
            project.radius_meters,
        )
    db.session.commit()
    return jsonify({"jobsites_updated": len(projects)}), 200


@admin_bp.route('/procore/add-project/preview', methods=['POST'])
@admin_required
@handle_errors("preview project")
@require_json("project_id")
def add_project_preview():
    """Fetch submittals from Procore API (read-only) and return a preview for admin confirmation."""
    try:
        project_id = int(g.json_data['project_id'])
    except (ValueError, TypeError):
        return jsonify({"error": "project_id must be an integer"}), 400

    procore_client = get_procore_client()
    all_submittals = procore_client.get_submittals(project_id)
    project_info = get_project_info(project_id)

    submittal_counts = {}
    for s in all_submittals:
        if not isinstance(s, dict):
            continue
        status = s.get('status')
        if isinstance(status, dict):
            status = status.get('name') or status.get('value') or 'Unknown'
        status = str(status).strip() if status else 'Unknown'
        submittal_counts[status] = submittal_counts.get(status, 0) + 1

    return jsonify({
        "project_id": project_id,
        "project_name": project_info.get("name") if project_info else None,
        "project_number": project_info.get("project_number") if project_info else None,
        "webhook_url": procore_client.webhook_url,
        "submittal_counts": submittal_counts,
        "total": len(all_submittals),
    }), 200


@admin_bp.route('/procore/add-project/confirm', methods=['POST'])
@admin_required
@handle_errors("add project")
@require_json("project_id")
def add_project_confirm():
    """Create Procore webhook and sync all submittals to DB for a given project."""
    try:
        project_id = int(g.json_data['project_id'])
    except (ValueError, TypeError):
        return jsonify({"error": "project_id must be an integer"}), 400

    from app.procore.scripts.create import create_webhook_and_trigger
    from app.procore.scripts.sync_submittals import sync_submittals_for_project

    procore_client = get_procore_client()
    project_info = get_project_info(project_id)
    project_number = project_info.get("project_number") if project_info else None
    project_name = project_info.get("name") if project_info else None

    webhook_result = create_webhook_and_trigger(procore_client, project_id, project_number)

    if webhook_result.get("status") == "error":
        return jsonify({
            "error": "Failed to create webhook",
            "details": webhook_result.get("error"),
            "webhook_result": webhook_result,
        }), 500

    sync_result = sync_submittals_for_project(project_id)

    return jsonify({
        "project_id": project_id,
        "project_name": project_name,
        "webhook_result": webhook_result,
        "sync_result": sync_result,
    }), 200


def _human_bytes(n):
    if n < 1024:
        return f"{n} B"
    kb = n / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.2f} MB"
    return f"{mb / 1024:.2f} GB"


@admin_bp.route('/disk/pdfs', methods=['GET'])
@admin_required
def disk_pdfs_summary():
    """Inspect the PDF markup persistent-storage directory.

    Returns: storage root, totals (file count + bytes), per-release breakdown
    (largest first), and DB↔disk orphan counts so we can spot missing files
    or leftover bytes from a botched delete.
    """
    override = current_app.config.get('PDF_STORAGE_ROOT')
    storage_root = override or os.path.join(current_app.root_path, 'storage', 'pdfs')

    info = {
        'storage_root': storage_root,
        'env_var_set': bool(override),
        'exists': os.path.isdir(storage_root),
        'writable': os.access(storage_root, os.W_OK) if os.path.isdir(storage_root) else False,
    }

    if not info['exists']:
        info.update({
            'total_files': 0,
            'total_bytes': 0,
            'per_release': [],
            'db_rows': db.session.query(ReleaseDrawingVersion).count(),
            'note': 'Storage root does not exist yet (no uploads have been written here).',
        })
        return jsonify(info), 200

    # Walk the disk
    per_release_bytes = {}
    per_release_count = {}
    total_files = 0
    total_bytes = 0
    on_disk_keys = set()  # storage_keys present on disk

    for entry in os.scandir(storage_root):
        if not entry.is_dir():
            continue
        try:
            release_id = int(entry.name)
        except ValueError:
            continue
        for f in os.scandir(entry.path):
            if not f.is_file() or not f.name.endswith('.pdf'):
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            total_files += 1
            total_bytes += size
            per_release_bytes[release_id] = per_release_bytes.get(release_id, 0) + size
            per_release_count[release_id] = per_release_count.get(release_id, 0) + 1
            on_disk_keys.add(f"{release_id}/{f.name}")

    # Cross-reference with DB
    db_rows = db.session.query(ReleaseDrawingVersion).all()
    db_keys = {r.storage_key for r in db_rows if not r.is_deleted}
    db_only = sorted(db_keys - on_disk_keys)        # rows pointing at missing files
    disk_only = sorted(on_disk_keys - db_keys)      # files with no live DB row (deleted or orphaned)

    per_release = [
        {
            'release_id': rid,
            'file_count': per_release_count[rid],
            'bytes': per_release_bytes[rid],
            'human_size': _human_bytes(per_release_bytes[rid]),
        }
        for rid in sorted(per_release_bytes, key=lambda k: per_release_bytes[k], reverse=True)
    ]

    info.update({
        'total_files': total_files,
        'total_bytes': total_bytes,
        'human_size': _human_bytes(total_bytes),
        'unique_releases': len(per_release_bytes),
        'db_rows_active': len(db_keys),
        'db_rows_total': len(db_rows),
        'db_missing_on_disk': db_only[:50],         # cap to keep payload small
        'db_missing_count': len(db_only),
        'disk_orphans': disk_only[:50],
        'disk_orphans_count': len(disk_only),
        'per_release': per_release[:50],            # top 50 largest
    })
    return jsonify(info), 200
