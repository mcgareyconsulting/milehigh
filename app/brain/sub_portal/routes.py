"""
@milehigh-header
schema_version: 1
purpose: Subcontractor-facing release routes (T3 slice 1) — the crew-scoped read model
  behind the sub timeline.
exports: (none — routes register on brain_bp)
imports_from: [flask, app.brain, app.subcontractor_auth.utils, app.brain.sub_portal.service]
imported_by: [app/brain/__init__.py]
invariants:
  - @subcontractor_login_required only. An internal User session is NOT accepted here,
    matching the decorator's own rule — the two identity spaces never cross.
  - No route in this module serves the changelog. Subs get Activity (slice 4), and the
    changelog is blocked by never having a route that returns it, not by a hidden tab.

GET /brain/subcontractor/releases         crew-scoped releases, allowlist-serialized
GET /brain/subcontractor/installer-teams  the caller's own crew, as a list
"""
from flask import jsonify

from app.brain import brain_bp
from app.brain.sub_portal.service import list_releases_for_subcontractor
from app.logging_config import get_logger
from app.subcontractor_auth.utils import get_current_subcontractor, subcontractor_login_required

logger = get_logger(__name__)


@brain_bp.route('/subcontractor/releases', methods=['GET'])
@subcontractor_login_required
def list_subcontractor_releases():
    """The releases assigned to this account's installer crew.

    Full load only. Cursor/incremental refresh (the `since` param the internal
    /brain/jobs feed carries) waits for the timeline in slice 3, so the shape of the
    polling contract is decided once, against a real consumer.
    """
    sub = get_current_subcontractor()
    releases = list_releases_for_subcontractor(sub)
    return jsonify({'releases': releases, 'installer_team': sub.installer_team}), 200


@brain_bp.route('/subcontractor/installer-teams', methods=['GET'])
@subcontractor_login_required
def list_subcontractor_installer_teams():
    """The caller's own crew, as a one-element list (empty if unscoped).

    A sub-scoped counterpart to /brain/installer-teams, which is @login_required and
    returns the FULL roster. The timeline blocks its initial load on the teams fetch,
    so without this route a subcontractor session 401s and the page never finishes
    loading — and serving the internal route would name every other crew to them.
    """
    sub = get_current_subcontractor()
    crew = (sub.installer_team or '').strip()
    return jsonify({'installer_teams': [crew] if crew else []}), 200
