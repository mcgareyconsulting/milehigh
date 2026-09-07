"""HTTP routes for admin management of the subcontractor roster and ticket
assignment (registered on brain_bp). All admin-only.

POST   /brain/subcontractors                                  create + invite
GET    /brain/subcontractors                                  list roster
GET    /brain/subcontractors/<id>                              detail
POST   /brain/subcontractors/<id>/resend-invite                 regenerate token, resend
POST   /brain/subcontractors/<id>/deactivate                    is_active = False
POST   /brain/subcontractors/<id>/reactivate                    is_active = True
GET    /brain/subcontractors/installer-teams                     crews an account may be scoped to
PATCH  /brain/subcontractors/<id>/installer-team                 set/clear the account's crew
POST   /brain/tm-tickets/<ticket_id>/subcontractors             assign
GET    /brain/tm-tickets/<ticket_id>/subcontractors             list assignments for a ticket
DELETE /brain/tm-tickets/<ticket_id>/subcontractors/<sub_id>    unassign
"""
from flask import request, jsonify

from app.brain import brain_bp
from app.auth.utils import admin_required, get_current_user
from app.models import Subcontractor, TMTicket, TMTicketSubcontractor, db
from app.logging_config import get_logger

from app.brain.subs.service import assignable_installer_teams
from app.brain.tm.subcontractors import command
from app.brain.tm.subcontractors.payloads import validate_invite_payload

logger = get_logger(__name__)


def _display_name(user) -> str:
    """Mirrors TMTicketAttachment._display_name / BoardItemPhoto._display_name's
    first+last-with-username-fallback convention. Used as the "invited by"
    name in the email body — the send identity itself is user.username."""
    first = (user.first_name or '').strip()
    last = (user.last_name or '').strip()
    return (f"{first} {last}".strip()) or user.username


@brain_bp.route('/subcontractors', methods=['POST'])
@admin_required
def create_subcontractor():
    body = request.get_json(silent=True) or {}
    error = validate_invite_payload(body)
    if error:
        return jsonify({'error': error}), 400

    email = body['email'].strip().lower()
    if Subcontractor.query.filter_by(email=email).first():
        return jsonify({'error': f'A subcontractor with email {email} already exists'}), 409

    user = get_current_user()
    try:
        sub = command.InviteSubcontractorCommand(
            company_name=body['company_name'].strip(),
            contact_name=body['contact_name'].strip(),
            email=email,
            invited_by_user_id=user.id,
            invited_by_email=user.username,
            invited_by_name=_display_name(user),
        ).execute()
    except command.OutboundLinkNotConfiguredError as exc:
        # Misconfiguration, not a mail-server failure — say so, because "email
        # send failed" sends the admin looking in entirely the wrong place.
        logger.error("subcontractor_invite_misconfigured", email=email, error=str(exc), exc_info=True)
        return jsonify({'error': str(exc)}), 500
    except Exception as exc:
        logger.error("subcontractor_invite_failed", email=email, error=str(exc), exc_info=True)
        return jsonify({'error': 'Subcontractor could not be invited (email send failed)'}), 502

    return jsonify(sub.to_dict()), 201


@brain_bp.route('/subcontractors', methods=['GET'])
@admin_required
def list_subcontractors():
    subs = Subcontractor.query.order_by(Subcontractor.company_name, Subcontractor.contact_name).all()
    return jsonify({'subcontractors': [s.to_dict() for s in subs]}), 200


@brain_bp.route('/subcontractors/<int:sub_id>', methods=['GET'])
@admin_required
def get_subcontractor(sub_id):
    sub = db.session.get(Subcontractor, sub_id)
    if not sub:
        return jsonify({'error': 'Subcontractor not found'}), 404
    return jsonify(sub.to_dict()), 200


@brain_bp.route('/subcontractors/<int:sub_id>/resend-invite', methods=['POST'])
@admin_required
def resend_subcontractor_invite(sub_id):
    sub = db.session.get(Subcontractor, sub_id)
    if not sub:
        return jsonify({'error': 'Subcontractor not found'}), 404
    if sub.invite_accepted_at is not None:
        return jsonify({'error': 'Invite already accepted; there is no pending invite to resend'}), 400

    user = get_current_user()
    try:
        command.resend_invite(sub, resent_by_email=user.username, resent_by_name=_display_name(user))
    except command.OutboundLinkNotConfiguredError as exc:
        logger.error("subcontractor_resend_misconfigured", subcontractor_id=sub_id, error=str(exc), exc_info=True)
        return jsonify({'error': str(exc)}), 500
    except Exception as exc:
        logger.error("subcontractor_resend_invite_failed", subcontractor_id=sub_id, error=str(exc), exc_info=True)
        return jsonify({'error': 'Resend failed (email send error)'}), 502

    return jsonify(sub.to_dict()), 200


@brain_bp.route('/subcontractors/<int:sub_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_subcontractor(sub_id):
    sub = db.session.get(Subcontractor, sub_id)
    if not sub:
        return jsonify({'error': 'Subcontractor not found'}), 404
    command.set_active(sub, False)
    return jsonify(sub.to_dict()), 200


@brain_bp.route('/subcontractors/<int:sub_id>/reactivate', methods=['POST'])
@admin_required
def reactivate_subcontractor(sub_id):
    sub = db.session.get(Subcontractor, sub_id)
    if not sub:
        return jsonify({'error': 'Subcontractor not found'}), 404
    command.set_active(sub, True)
    return jsonify(sub.to_dict()), 200


@brain_bp.route('/subcontractors/installer-teams', methods=['GET'])
@admin_required
def list_assignable_installer_teams():
    """The crew names the roster's crew picker may offer.

    Deliberately NOT /brain/installer-teams: that route serves the job log's full
    roster, which includes MHMW's own crews. Scoping an external account to one of
    those would hand a subcontractor MHMW-staff work.

    Sits above the '/subcontractors/<int:sub_id>' rule only for readability — the
    int converter means 'installer-teams' could never match it anyway.
    """
    return jsonify({'installer_teams': assignable_installer_teams()}), 200


@brain_bp.route('/subcontractors/<int:sub_id>/installer-team', methods=['PATCH'])
@admin_required
def set_subcontractor_installer_team(sub_id):
    """Scope a subcontractor account to an installer crew, or clear it with null.

    PATCH rather than POST: this edits one field of an existing account, unlike the
    deactivate/reactivate pair above, which are named state transitions.

    Clearing is allowed on an inactive account too — an admin tidying up a departed
    crew shouldn't have to reactivate the account to unscope it.
    """
    sub = db.session.get(Subcontractor, sub_id)
    if not sub:
        return jsonify({'error': 'Subcontractor not found'}), 404

    body = request.get_json(silent=True) or {}
    if 'installer_team' not in body:
        return jsonify({'error': 'installer_team is required (send null to clear)'}), 400

    team = body['installer_team']
    if team is not None and not isinstance(team, str):
        return jsonify({'error': 'installer_team must be a string or null'}), 400

    try:
        command.set_installer_team(sub, team)
    except command.InvalidInstallerTeamError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify(sub.to_dict()), 200


@brain_bp.route('/tm-tickets/<int:ticket_id>/subcontractors', methods=['POST'])
@admin_required
def assign_subcontractor(ticket_id):
    ticket = db.session.get(TMTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404

    body = request.get_json(silent=True) or {}
    sub_id = body.get('subcontractor_id')
    sub = db.session.get(Subcontractor, sub_id) if sub_id else None
    if not sub:
        return jsonify({'error': 'subcontractor_id is required and must reference an existing subcontractor'}), 400
    if not sub.is_active:
        return jsonify({'error': 'Cannot assign an inactive subcontractor'}), 400

    user = get_current_user()
    assignment = command.assign_to_ticket(
        ticket, sub, user.id, assigned_by_email=user.username, assigned_by_name=_display_name(user))
    return jsonify(assignment.to_dict()), 201


@brain_bp.route('/tm-tickets/<int:ticket_id>/subcontractors', methods=['GET'])
@admin_required
def list_ticket_subcontractors(ticket_id):
    ticket = db.session.get(TMTicket, ticket_id)
    if not ticket:
        return jsonify({'error': 'Ticket not found'}), 404
    assignments = TMTicketSubcontractor.query.filter_by(tm_ticket_id=ticket_id).all()
    return jsonify({'subcontractors': [a.to_dict() for a in assignments]}), 200


@brain_bp.route('/tm-tickets/<int:ticket_id>/subcontractors/<int:sub_id>', methods=['DELETE'])
@admin_required
def unassign_subcontractor(ticket_id, sub_id):
    removed = command.unassign_from_ticket(ticket_id, sub_id)
    if not removed:
        return jsonify({'error': 'Assignment not found'}), 404
    return jsonify({'status': 'unassigned'}), 200
