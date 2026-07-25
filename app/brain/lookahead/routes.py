"""
@milehigh-header
schema_version: 1
purpose: HTTP surface for GC-facing look-ahead PDFs — generate from job number and download
  a short-lived artifact. Gated by carmen_chat access (admins always allowed).
exports: route handlers registered on brain_bp
imports_from: [flask, app.auth.utils, app.brain.lookahead.*]
imported_by: [app.brain.__init__]
invariants:
  - Read-only w.r.t. job data; only writes artifact files under storage/lookahead.
  - Artifact ids are opaque tokens; path traversal rejected in artifacts module.
"""
from flask import jsonify, request, send_file, current_app
from io import BytesIO

from app.auth.utils import carmen_chat_required, get_current_user
from app.brain import brain_bp
from app.brain.lookahead.artifacts import load_meta, read_lookahead_pdf, save_lookahead_pdf
from app.brain.lookahead.export_pdf import render_schedule_pdf
from app.brain.lookahead.schedule_builder import build_project_lookahead
from app.logging_config import get_logger

logger = get_logger(__name__)


@brain_bp.route("/lookahead/pdf", methods=["POST"])
@carmen_chat_required
def lookahead_generate_pdf():
    """Build schedule + PDF for a job. Body: {job: int, weeks?: int}.

    Returns JSON: {artifact_id, download_path, title, job, project_name, window, summary}.
    """
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    job = data.get("job")
    weeks = data.get("weeks", 3)
    if job is None:
        return jsonify({"error": "job is required"}), 400
    try:
        job_int = int(job)
    except (TypeError, ValueError):
        return jsonify({"error": f"invalid job: {job!r}"}), 400
    try:
        weeks_int = int(weeks) if weeks is not None else 3
    except (TypeError, ValueError):
        weeks_int = 3

    schedule = build_project_lookahead(job_int, weeks=weeks_int)
    if not schedule.get("found"):
        return jsonify({
            "found": False,
            "job": job_int,
            "error": schedule.get("error") or "no active work for this job",
        }), 404

    try:
        pdf_bytes = render_schedule_pdf(schedule)
        meta = save_lookahead_pdf(
            pdf_bytes,
            schedule=schedule,
            user_id=user.id if user else None,
        )
    except Exception as exc:
        logger.error(
            "lookahead_pdf_generate_failed",
            job=job_int,
            error=str(exc),
            error_type=type(exc).__name__,
            user_id=user.id if user else None,
            exc_info=True,
        )
        return jsonify({"error": "failed to render look-ahead PDF"}), 500

    logger.info(
        "lookahead_pdf_generated",
        job=job_int,
        artifact_id=meta["artifact_id"],
        bytes=meta.get("bytes"),
        user_id=user.id if user else None,
    )
    return jsonify({
        "found": True,
        "artifact_id": meta["artifact_id"],
        "download_path": meta["download_path"],
        "title": meta["title"],
        "job": schedule.get("job"),
        "project_name": schedule.get("project_name"),
        "window": schedule.get("window"),
        "summary": schedule.get("summary"),
        "page_size": meta.get("page_size"),
        "assumptions": schedule.get("assumptions"),
    }), 200


@brain_bp.route("/lookahead/artifacts/<artifact_id>.pdf", methods=["GET"])
@carmen_chat_required
def lookahead_download_pdf(artifact_id):
    """Download a previously generated look-ahead PDF by opaque artifact id."""
    try:
        pdf_bytes = read_lookahead_pdf(artifact_id)
    except ValueError:
        return jsonify({"error": "invalid artifact id"}), 400
    except FileNotFoundError:
        return jsonify({"error": "artifact not found"}), 404

    meta = load_meta(artifact_id) or {}
    filename = _safe_filename(meta.get("title") or f"lookahead-{artifact_id}")
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{filename}.pdf",
        max_age=0,
    )


def _safe_filename(title: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", " ") else "-" for ch in title)
    cleaned = "-".join(cleaned.split())
    return (cleaned or "lookahead")[:80]
