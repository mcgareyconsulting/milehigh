"""
@milehigh-header
schema_version: 1
purpose: Download a release-report PDF or CSV that Carmen already rendered.
exports: route handlers registered on brain_bp
imports_from: [flask, app.auth.utils, app.reports.artifacts]
imported_by: [app.brain]
invariants:
  - Read-only against releases. The files were written when the tool ran.
  - Admin only. Opaque artifact ids only.
"""
from io import BytesIO

from flask import jsonify, send_file

from app.auth.utils import admin_required
from app.brain import brain_bp
from app.logging_config import get_logger
from app.reports.artifacts import load_meta, read_release_report

logger = get_logger(__name__)


def _send(artifact_id: str, ext: str, mimetype: str):
    try:
        payload = read_release_report(artifact_id, ext)
    except ValueError:
        return jsonify({"error": "invalid artifact id"}), 400
    except FileNotFoundError:
        return jsonify({"error": "artifact not found"}), 404
    meta = load_meta(artifact_id) or {}
    filename = meta.get(f"{ext}_filename") or f"release-report.{ext}"
    return send_file(
        BytesIO(payload),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


@brain_bp.route("/reports/artifacts/<artifact_id>.pdf", methods=["GET"])
@admin_required
def release_report_pdf(artifact_id):
    return _send(artifact_id, "pdf", "application/pdf")


@brain_bp.route("/reports/artifacts/<artifact_id>.csv", methods=["GET"])
@admin_required
def release_report_csv(artifact_id):
    return _send(artifact_id, "csv", "text/csv; charset=utf-8")
