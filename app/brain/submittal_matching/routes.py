"""
@milehigh-header
schema_version: 1
purpose: Admin endpoints for the Submittal Matching review tool -- suggest, confirm, and audit DRR->release links.
exports:
  get_matching_projects: GET /brain/submittal-matching/projects -- per-project DRR link coverage summary
  get_matching_drrs: GET /brain/submittal-matching/drrs?project=NNN -- DRRs with ranked release suggestions
  link_submittal_release: POST /brain/submittal-matching/<pk>/link -- confirm a link
  unlink_submittal_release: POST /brain/submittal-matching/<pk>/unlink -- revert to unreviewed
  mark_submittal_no_match: POST /brain/submittal-matching/<pk>/no-match -- confirmed no release exists
imports_from: [app.brain, app.models, app.auth.utils, app.procore.helpers, app.brain.submittal_matching.matcher, app.logging_config]
imported_by: [app/brain/__init__.py]
invariants:
  - All routes are @admin_required.
  - Suggestions and links are job-scoped: a link's release.job must equal the submittal's
    project_number (400 otherwise) -- cross-job links are always wrong.
  - Candidate pools include archived and soft-deleted releases: historical DRRs must be
    able to find their long-completed releases.
  - Every link/unlink/no-match writes a SubmittalEvents audit row (source='Brain'), and
    the submittal change is committed BEFORE the event row so a duplicate-hash event
    rollback can never revert the link itself.
updated_by_agent: 2026-07-12T00:00:00Z

Admin Submittal Matching tool.

Purpose: harden the DRR -> release link for the tee-time scheduling data foundation.
An admin filters by project, reviews ranked description-match suggestions (validated at
36/36 precision against Rel-link ground truth), and confirms links one tap at a time.
Once linked, the FC-phase span is inferred as (release date - DRR close date), since
FC releases to the job log same-day ~99% of the time.
"""

from flask import jsonify, request

from app.brain import brain_bp
from app.auth.utils import admin_required, get_current_user
from app.models import db, Releases, Submittals, SubmittalEvents
from app.procore.helpers import create_submittal_event
from app.brain.submittal_matching import matcher
from app.logging_config import get_logger

logger = get_logger(__name__)

_DRR_FILTER = Submittals.type.ilike("%drafting release review%")

LINK_STATUS_UNREVIEWED = ""
LINK_STATUS_LINKED = "linked"
LINK_STATUS_NO_MATCH = "no_match"


def _release_pool(project_number):
    """All releases of the job -- archived and soft-deleted INCLUDED (historical DRRs
    must be able to find their long-completed releases)."""
    if not project_number:
        return []
    try:
        job = int(project_number)
    except (TypeError, ValueError):
        return []
    return Releases.query.filter(Releases.job == job).all()


def _release_summary(r):
    return {
        "release_pk": r.id,
        "job": r.job,
        "release": r.release,
        "description": r.description,
        "released": r.released.isoformat() if r.released else None,
        "stage": r.stage,
        "is_archived": bool(r.is_archived),
        "is_active": bool(r.is_active) if r.is_active is not None else True,
    }


def _payload_says_closed(payload):
    """True if an event payload records the submittal reaching Closed. Handles both the
    diff shape ({'status': {'old': ..., 'new': 'Closed'}}) and the snapshot shape
    ({'status': 'Closed'})."""
    if not isinstance(payload, dict):
        return False
    status = payload.get("status")
    if isinstance(status, dict):
        status = status.get("new")
    return isinstance(status, str) and status.strip().lower() == "closed"


def _closed_dates(submittal_ids):
    """Earliest Closed-event timestamp per submittal_id (None when never observed)."""
    if not submittal_ids:
        return {}
    events = (
        SubmittalEvents.query
        .filter(SubmittalEvents.submittal_id.in_(list(submittal_ids)))
        .order_by(SubmittalEvents.created_at.asc())
        .all()
    )
    closed = {}
    for ev in events:
        if ev.submittal_id in closed:
            continue
        if _payload_says_closed(ev.payload):
            closed[ev.submittal_id] = ev.created_at
    return closed


@brain_bp.route("/submittal-matching/projects", methods=["GET"])
@admin_required
def get_matching_projects():
    """Per-project DRR link coverage: how much reviewing is left, project by project."""
    drrs = Submittals.query.filter(_DRR_FILTER).all()

    projects = {}
    for s in drrs:
        key = s.project_number or "?"
        p = projects.setdefault(key, {
            "project_number": key,
            "project_name": s.project_name,
            "drr_total": 0,
            "linked": 0,
            "no_match": 0,
            "unreviewed": 0,
        })
        p["drr_total"] += 1
        status = s.link_status or LINK_STATUS_UNREVIEWED
        if status == LINK_STATUS_LINKED:
            p["linked"] += 1
        elif status == LINK_STATUS_NO_MATCH:
            p["no_match"] += 1
        else:
            p["unreviewed"] += 1

    # Release-pool size per project so the UI can flag jobs with nothing to match against.
    for p in projects.values():
        p["release_pool"] = len(_release_pool(p["project_number"]))

    ordered = sorted(projects.values(), key=lambda p: -p["unreviewed"])
    return jsonify({"projects": ordered})


@brain_bp.route("/submittal-matching/drrs", methods=["GET"])
@admin_required
def get_matching_drrs():
    """DRRs for one project with ranked release suggestions (all statuses, all releases)."""
    project = (request.args.get("project") or "").strip()
    if not project:
        return jsonify({"error": "project query param is required"}), 400

    drrs = (
        Submittals.query
        .filter(_DRR_FILTER, Submittals.project_number == project)
        .order_by(Submittals.created_at.asc())
        .all()
    )
    pool = _release_pool(project)
    pool_dicts = [_release_summary(r) for r in pool]
    releases_by_pk = {r.id: r for r in pool}
    token_freq = matcher.build_token_frequency(r.description for r in pool)
    closed_at = _closed_dates([s.submittal_id for s in drrs])

    rows = []
    for s in drrs:
        suggestion = matcher.suggest(s.title, pool_dicts, token_freq)

        linked_release = None
        fc_inferred_days = None
        if s.linked_release_id:
            linked = releases_by_pk.get(s.linked_release_id) or db.session.get(Releases, s.linked_release_id)
            if linked is not None:
                linked_release = _release_summary(linked)
                closed = closed_at.get(s.submittal_id)
                # FC-phase inference: FC releases to the job log same-day ~99% of the
                # time, so (release date - DRR close date) approximates the FC span.
                if closed and linked.released:
                    fc_inferred_days = (linked.released - closed.date()).days

        rows.append({
            "id": s.id,
            "submittal_id": s.submittal_id,
            "title": s.title,
            "status": s.status,
            "rel": s.rel,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "closed_at": closed_at.get(s.submittal_id).isoformat() if closed_at.get(s.submittal_id) else None,
            "link_status": s.link_status or LINK_STATUS_UNREVIEWED,
            "linked_release": linked_release,
            "fc_inferred_days": fc_inferred_days,
            "suggestion": suggestion,
        })

    return jsonify({
        "project": project,
        "release_pool": len(pool),
        "drrs": rows,
    })


def _audit_link_change(submittal, old_status, old_release_id, user):
    """SubmittalEvents audit row for a link change. Called AFTER the submittal change is
    committed, so a duplicate-hash rollback inside the helper can't revert the link."""
    create_submittal_event(
        submittal.submittal_id,
        "updated",
        payload={
            "link_status": {"old": old_status, "new": submittal.link_status},
            "linked_release_id": {"old": old_release_id, "new": submittal.linked_release_id},
        },
        source="Brain",
        internal_user_id=user.id if user else None,
    )


def _get_drr_or_404(pk):
    submittal = db.session.get(Submittals, pk)
    if submittal is None or "drafting release review" not in (submittal.type or "").lower():
        return None
    return submittal


@brain_bp.route("/submittal-matching/<int:pk>/link", methods=["POST"])
@admin_required
def link_submittal_release(pk):
    """Confirm a DRR -> release link. Body: {"release_id": <releases.id>}."""
    submittal = _get_drr_or_404(pk)
    if submittal is None:
        return jsonify({"error": "DRR submittal not found"}), 404

    data = request.get_json(silent=True) or {}
    release_id = data.get("release_id")
    if not isinstance(release_id, int):
        return jsonify({"error": "release_id (int) is required"}), 400

    release = db.session.get(Releases, release_id)
    if release is None:
        return jsonify({"error": "release not found"}), 404
    if str(release.job) != (submittal.project_number or ""):
        return jsonify({
            "error": "cross_job_link",
            "message": f"Release belongs to job {release.job}, submittal to project "
                       f"{submittal.project_number} -- links are job-scoped by design.",
        }), 400

    old_status = submittal.link_status or LINK_STATUS_UNREVIEWED
    old_release_id = submittal.linked_release_id
    submittal.linked_release_id = release.id
    submittal.link_status = LINK_STATUS_LINKED
    db.session.commit()

    user = get_current_user()
    _audit_link_change(submittal, old_status, old_release_id, user)
    logger.info(
        "submittal_release_linked",
        submittal_id=submittal.submittal_id,
        release_id=release.id,
        job=release.job,
        release=release.release,
        user_id=user.id if user else None,
    )
    return jsonify({"ok": True, "link_status": submittal.link_status,
                    "linked_release": _release_summary(release)})


@brain_bp.route("/submittal-matching/<int:pk>/unlink", methods=["POST"])
@admin_required
def unlink_submittal_release(pk):
    """Revert a DRR to unreviewed (clears link or no-match)."""
    submittal = _get_drr_or_404(pk)
    if submittal is None:
        return jsonify({"error": "DRR submittal not found"}), 404

    old_status = submittal.link_status or LINK_STATUS_UNREVIEWED
    old_release_id = submittal.linked_release_id
    if old_status == LINK_STATUS_UNREVIEWED and old_release_id is None:
        return jsonify({"ok": True, "link_status": LINK_STATUS_UNREVIEWED})

    submittal.linked_release_id = None
    submittal.link_status = LINK_STATUS_UNREVIEWED
    db.session.commit()

    user = get_current_user()
    _audit_link_change(submittal, old_status, old_release_id, user)
    logger.info(
        "submittal_release_unlinked",
        submittal_id=submittal.submittal_id,
        previous_release_id=old_release_id,
        user_id=user.id if user else None,
    )
    return jsonify({"ok": True, "link_status": LINK_STATUS_UNREVIEWED})


@brain_bp.route("/submittal-matching/<int:pk>/no-match", methods=["POST"])
@admin_required
def mark_submittal_no_match(pk):
    """Mark a DRR as reviewed with no job-log release (so it stops surfacing as work)."""
    submittal = _get_drr_or_404(pk)
    if submittal is None:
        return jsonify({"error": "DRR submittal not found"}), 404

    old_status = submittal.link_status or LINK_STATUS_UNREVIEWED
    old_release_id = submittal.linked_release_id
    submittal.linked_release_id = None
    submittal.link_status = LINK_STATUS_NO_MATCH
    db.session.commit()

    user = get_current_user()
    _audit_link_change(submittal, old_status, old_release_id, user)
    logger.info(
        "submittal_release_no_match",
        submittal_id=submittal.submittal_id,
        user_id=user.id if user else None,
    )
    return jsonify({"ok": True, "link_status": LINK_STATUS_NO_MATCH})
