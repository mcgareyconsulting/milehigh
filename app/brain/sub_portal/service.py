"""
@milehigh-header
schema_version: 1
purpose: Scoped query + allowlist serializer for the subcontractor release view (T3 slice 1).
exports:
  SUB_FIELDS: The exact key set a subcontractor payload may contain
  list_releases_for_subcontractor: Crew-scoped release rows, allowlist-serialized
  serialize_release_for_sub: One row -> sub payload (exported for the allowlist test)
imports_from: [app.models, app.brain.job_log.utils, app.logging_config]
imported_by: [app/brain/sub_portal/routes.py]
invariants:
  - Keys mirror the INTERNAL /brain/jobs serializer exactly, display casing included
    ('Job #', 'Comp. ETA'), because GanttChart reads those keys. A snake_case payload
    would render an empty timeline.
  - serialize_release_for_sub emits SUB_FIELDS and nothing else; the test asserts
    equality, not containment, so a new Releases column cannot leak in silently.
  - A subcontractor with no crew gets [] — never an unscoped query.
"""
from app.brain.job_log.utils import serialize_value
from app.logging_config import get_logger
from app.models import Releases, db

logger = get_logger(__name__)

# The complete set of keys a subcontractor payload may carry.
#
# Chosen as (what GanttChart actually reads off a row) + (what Bill's release modal
# names) - (what he excludes). Casing matches the internal /brain/jobs serializer
# because the timeline reads these exact keys.
#
# Deliberately ABSENT, and why:
#   'Fab Hrs'          Bill's one stated exclusion [bill-2026-09-02#L921]
#   'Fab Order'        shop sequencing, not the sub's work
#   'Invoiced'         MHMW customer billing
#   'Notes'            the notes THREAD is its own scoped endpoint (slice 4); shipping
#                      a denormalized "latest" here invites the two to disagree
#   'Paint color'      not in the named scope; candidate if install asks for it
#   'Released'         internal drafting milestone
#   start_install_formula   the raw formula string, an internal scheduling detail
#   source_of_update / trello_card_id   internal plumbing and Trello identity
#   viewer_url / has_drawing / cover_photo_id / photo_count
#                      attachment plumbing pointing at @login_required routes — they
#                      would advertise doors that do not open until slice 4
#   is_active / is_archived   filtered server-side; the flags never travel
#
# 'last_updated_at' IS included: it carries no business information and the shared
# releases data contract needs a cursor for incremental refresh.
SUB_FIELDS = frozenset({
    'id',
    'Job #',
    'Release #',
    'Job',
    'Description',
    'Install HRS',
    'PM',
    'BY',
    'Stage',
    'Stage Group',
    'Start install',
    'start_install_formulaTF',
    'start_install_asap',
    'start_install_no_color',
    'Ship Date',
    'installer',
    'Comp. ETA',
    'comp_eta_effective',
    'num_guys',
    'Job Comp',
    'release_tag',
    'last_updated_at',
})


def serialize_release_for_sub(release: Releases) -> dict:
    """One release -> the subcontractor payload.

    Built by NAMING each allowed field rather than copying the internal row and
    deleting from it. The difference matters: a delete-list silently passes through
    every column added later, an allowlist does not.
    """
    # Imported lazily: both live in app/brain/job_log/routes, which registers routes on
    # brain_bp at import time. A module-level import here would couple registration order.
    from app.api.helpers import get_stage_group_from_stage
    from app.brain.job_log.routes import _comp_eta_effective

    stage = release.stage if release.stage else 'Released'
    return {
        'id': serialize_value(release.id),
        'Job #': serialize_value(release.job),
        'Release #': serialize_value(release.release),
        'Job': serialize_value(release.job_name),
        'Description': serialize_value(release.description),
        'Install HRS': serialize_value(release.install_hrs),
        'PM': serialize_value(release.pm),
        'BY': serialize_value(release.by),
        'Stage': stage,
        # Recomputed from the current stage, matching the internal serializer — a stale
        # stored stage_group would put the card in the wrong lane group.
        'Stage Group': serialize_value(get_stage_group_from_stage(stage)),
        'Start install': serialize_value(release.start_install),
        'start_install_formulaTF': serialize_value(release.start_install_formulaTF),
        'start_install_asap': serialize_value(release.start_install_asap),
        'start_install_no_color': serialize_value(release.start_install_no_color),
        'Ship Date': serialize_value(release.ship_date),
        'installer': serialize_value(release.installer),
        'Comp. ETA': serialize_value(release.comp_eta),
        'comp_eta_effective': serialize_value(_comp_eta_effective(release)),
        'num_guys': serialize_value(release.num_guys),
        'Job Comp': serialize_value(release.job_comp),
        'release_tag': serialize_value(release.release_tag),
        'last_updated_at': serialize_value(release.last_updated_at),
    }


def list_releases_for_subcontractor(subcontractor) -> list:
    """Releases on this subcontractor's crew, allowlist-serialized.

    Returns [] for an unscoped account. That is the fail-closed half of the crew
    model: an account with no crew must resolve to no releases, never to an
    unfiltered query, so a half-finished onboarding cannot expose the job log.

    Archived and soft-deleted rows are excluded here rather than shipped with flags
    for the client to filter — the flags themselves never travel.
    """
    crew = (subcontractor.installer_team or '').strip()
    if not crew:
        logger.debug("sub_releases_unscoped_account", subcontractor_id=subcontractor.id)
        return []

    rows = (
        Releases.query
        .filter(Releases.installer == crew)
        .filter(db.or_(Releases.is_archived == False, Releases.is_archived == None))  # noqa: E712
        .filter(db.or_(Releases.is_active == True, Releases.is_active == None))       # noqa: E712
        .order_by(Releases.start_install.asc(), Releases.id.asc())
        .all()
    )
    return [serialize_release_for_sub(r) for r in rows]
