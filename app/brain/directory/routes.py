"""
@milehigh-header
schema_version: 1
purpose: Admin-only user directory (employees from User, subcontractors from
         Subcontractor) plus permissions management — an admin assigns an
         employee one of Admin / Drafter / Default from the Users page.
exports:
  GET   /brain/directory — {employees, subcontractors}
  PATCH /brain/directory/employees/<user_id>/role — set one employee's role
imports_from: [flask, app.brain, app.auth.utils, app.route_utils, app.models, app.logging_config]
imported_by: [app/brain/__init__.py]
invariants:
  - @admin_required on every route. GET never logs at INFO (it is a read).
  - Employee roles are mutually exclusive: exactly one of admin / drafter / default.
    Admin already satisfies every drafter gate (drafter_or_admin_required checks
    is_admin OR is_drafter), so collapsing the old "both flags" rows loses no access.
  - Subcontractors are a separate table and are never touched here — they have no
    role to assign and stay labelled "Subcontractor".
  - An admin cannot change their own role, and the last remaining admin cannot be
    demoted (both would lock admins out of this page).
  - username is the employee email. Subcontractor first/last is split from contact_name.
"""
from flask import g, jsonify

from app.brain import brain_bp
from app.auth.utils import admin_required, get_current_user
from app.logging_config import get_logger
from app.route_utils import handle_errors, require_json
from app.models import User, Subcontractor, db

logger = get_logger(__name__)

# The three assignable employee permission levels, most privileged first.
ROLE_ADMIN = "admin"
ROLE_DRAFTER = "drafter"
ROLE_DEFAULT = "default"

ROLE_LABELS = {
    ROLE_ADMIN: "Admin",
    ROLE_DRAFTER: "Drafter",
    ROLE_DEFAULT: "Default",
}

# is_admin / is_drafter as written for each role. Exactly one flag can be set;
# admin implies every drafter permission already, so it does not also set is_drafter.
ROLE_FLAGS = {
    ROLE_ADMIN: (True, False),
    ROLE_DRAFTER: (False, True),
    ROLE_DEFAULT: (False, False),
}


def employee_role_key(user):
    """The single role key for a user, from the current boolean flags.

    Legacy rows may carry both flags; admin wins, since it is the strictly
    higher level and already grants everything drafter does.
    """
    if user.is_admin:
        return ROLE_ADMIN
    if user.is_drafter:
        return ROLE_DRAFTER
    return ROLE_DEFAULT


def employee_role(user):
    """Display label for a user's role: Admin, Drafter, or Default."""
    return ROLE_LABELS[employee_role_key(user)]


def split_contact_name(contact_name):
    """Split a single contact_name into (first, last) on the first space.

    Subcontractor.contact_name is one field; the directory wants First/Last.
    A one-token name is all first; empty/None becomes ("", "").
    """
    parts = (contact_name or "").strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _sort_key(row):
    return (
        (row["last_name"] or "").lower(),
        (row["first_name"] or "").lower(),
        (row["email"] or "").lower(),
    )


def _employee_row(user):
    return {
        "id": user.id,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "email": user.username or "",
        "role": employee_role(user),
        "role_key": employee_role_key(user),
    }


def _subcontractor_row(sub):
    first_name, last_name = split_contact_name(sub.contact_name)
    return {
        "id": sub.id,
        "first_name": first_name,
        "last_name": last_name,
        "email": sub.email or "",
        "role": "Subcontractor",
    }


@brain_bp.route("/directory", methods=["GET"])
@admin_required
@handle_errors("load user directory")
def list_directory():
    employees = sorted(
        (_employee_row(u) for u in User.query.all()),
        key=_sort_key,
    )
    subcontractors = sorted(
        (_subcontractor_row(s) for s in Subcontractor.query.all()),
        key=_sort_key,
    )
    return jsonify({
        "employees": employees,
        "subcontractors": subcontractors,
        "roles": [{"key": key, "label": ROLE_LABELS[key]}
                  for key in (ROLE_ADMIN, ROLE_DRAFTER, ROLE_DEFAULT)],
    }), 200


@brain_bp.route("/directory/employees/<int:user_id>/role", methods=["PATCH"])
@admin_required
@handle_errors("update user role")
@require_json("role")
def set_employee_role(user_id):
    """Assign one employee a role. Body: {"role": "admin"|"drafter"|"default"}."""
    role = str(g.json_data["role"]).strip().lower()
    if role not in ROLE_FLAGS:
        return jsonify({"error": "role must be one of: admin, drafter, default"}), 400

    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"error": "User not found"}), 404

    actor = get_current_user()
    if actor and actor.id == target.id:
        return jsonify({"error": "You cannot change your own role"}), 400

    previous = employee_role_key(target)
    if previous == ROLE_ADMIN and role != ROLE_ADMIN:
        remaining_admins = User.query.filter(
            User.is_admin.is_(True),
            User.id != target.id,
        ).count()
        if remaining_admins == 0:
            return jsonify({"error": "At least one admin must remain"}), 400

    if previous == role:
        # Still normalize the flags: a legacy row with both set collapses to one.
        target.is_admin, target.is_drafter = ROLE_FLAGS[role]
        db.session.commit()
        return jsonify(_employee_row(target)), 200

    target.is_admin, target.is_drafter = ROLE_FLAGS[role]
    db.session.commit()

    logger.info(
        "user_role_changed",
        user_id=target.id,
        username=target.username,
        from_role=previous,
        to_role=role,
        actor_id=actor.id if actor else None,
    )
    return jsonify(_employee_row(target)), 200
