"""Admin CRUD for installer crews (the `installer_teams` table).

Endpoints (registered on brain_bp under the /brain prefix):
  GET    /crews            — list crews (login required; feeds the assign dropdown)
  POST   /crews            — create a crew (admin)
  PATCH  /crews/<id>       — rename / change crew_size / toggle active (admin)
  DELETE /crews/<id>       — remove a crew (admin)

A crew's `name` is kept identical to its Trello list name (the mirror-card move
resolves the list by name or stored trello_list_id). A crew's `crew_size`
(number of installers) drives the completion ETA of every release assigned to
that crew, so size changes trigger a scheduling recalc.
"""

from flask import jsonify, request

from app.brain import brain_bp
from app.auth.utils import login_required, admin_required
from app.models import InstallerTeam, db
from app.logging_config import get_logger

logger = get_logger(__name__)


def _coerce_crew_size(value, default=2):
    """Crew size must be a positive int; fall back to default otherwise."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= 1 else default


def _recalc_fabrication():
    """Reflow scheduling — comp_eta depends on each release's assigned crew size."""
    try:
        from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling
        recalculate_all_jobs_scheduling(stage_group='FABRICATION')
    except Exception as cascade_error:
        logger.error(
            f"Scheduling cascade failed after crew change: {cascade_error}",
            exc_info=True,
        )


@brain_bp.route('/crews', methods=['GET'])
@login_required
def list_crews():
    """List crews, active first then by name. Used by the assign-installer dropdown."""
    crews = InstallerTeam.query.order_by(
        InstallerTeam.is_active.desc(), InstallerTeam.name.asc()
    ).all()
    return jsonify({'crews': [c.to_dict() for c in crews]}), 200


@brain_bp.route('/crews', methods=['POST'])
@admin_required
def create_crew():
    """Create a crew. Name must be unique (it matches the Trello list name)."""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Crew name is required'}), 400

    if InstallerTeam.query.filter_by(name=name).first():
        return jsonify({'error': f"A crew named '{name}' already exists"}), 409

    crew = InstallerTeam(
        name=name,
        crew_size=_coerce_crew_size(data.get('crew_size', 2)),
        is_active=bool(data.get('is_active', True)),
    )
    db.session.add(crew)
    db.session.commit()
    logger.info(f"Crew created: {name} (crew_size={crew.crew_size})")
    return jsonify(crew.to_dict()), 201


@brain_bp.route('/crews/<int:crew_id>', methods=['PATCH'])
@admin_required
def update_crew(crew_id):
    """Rename a crew, change its size, or toggle active. A size change reflows ETAs."""
    crew = InstallerTeam.query.get_or_404(crew_id)
    data = request.get_json() or {}

    size_changed = False
    renamed_from = None

    if 'name' in data:
        new_name = (data.get('name') or '').strip()
        if not new_name:
            return jsonify({'error': 'Crew name cannot be empty'}), 400
        if new_name != crew.name:
            clash = InstallerTeam.query.filter_by(name=new_name).first()
            if clash and clash.id != crew.id:
                return jsonify({'error': f"A crew named '{new_name}' already exists"}), 409
            renamed_from = crew.name
            crew.name = new_name

    if 'crew_size' in data:
        new_size = _coerce_crew_size(data.get('crew_size'), default=crew.crew_size)
        if new_size != crew.crew_size:
            size_changed = True
        crew.crew_size = new_size

    if 'is_active' in data:
        crew.is_active = bool(data.get('is_active'))

    if 'trello_list_id' in data:
        crew.trello_list_id = (data.get('trello_list_id') or '').strip() or None

    db.session.commit()

    # Keep release.installer (stored by name) in sync with a rename so existing
    # assignments don't dangle, then reflow ETAs if the crew size changed.
    if renamed_from:
        from app.models import Releases
        Releases.query.filter_by(installer=renamed_from).update(
            {Releases.installer: crew.name}, synchronize_session=False
        )
        db.session.commit()
        logger.info(f"Crew renamed: {renamed_from} → {crew.name}")

    if size_changed:
        _recalc_fabrication()

    return jsonify(crew.to_dict()), 200


@brain_bp.route('/crews/<int:crew_id>', methods=['DELETE'])
@admin_required
def delete_crew(crew_id):
    """Remove a crew. Releases keep their stored installer name (now unmatched);
    their ETA falls back to the default crew size on the next recalc."""
    crew = InstallerTeam.query.get_or_404(crew_id)
    name = crew.name
    db.session.delete(crew)
    db.session.commit()
    logger.info(f"Crew deleted: {name}")
    _recalc_fabrication()
    return jsonify({'ok': True}), 200
