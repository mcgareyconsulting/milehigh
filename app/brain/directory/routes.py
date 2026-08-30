"""
@milehigh-header
schema_version: 1
purpose: Admin-only read-only directory of employees (User) and subcontractors
         (Subcontractor). First T2 pass — list First/Last/email/role, no writes.
exports:
  GET /brain/directory — {employees, subcontractors}
imports_from: [flask, app.brain, app.auth.utils, app.route_utils, app.models]
imported_by: [app/brain/__init__.py]
invariants:
  - @admin_required on the only route. Never logs at INFO (this is a read).
  - username is the employee email. Subcontractor first/last is split from contact_name.
"""
from flask import jsonify

from app.brain import brain_bp
from app.auth.utils import admin_required
from app.route_utils import handle_errors
from app.models import User, Subcontractor


def employee_role(user):
    """Role label from the current User boolean flags.

    Admin and Drafter can both be true; list both so the directory shows who
    has what. Anyone with neither flag is an Employee.
    """
    labels = []
    if user.is_admin:
        labels.append("Admin")
    if user.is_drafter:
        labels.append("Drafter")
    return ", ".join(labels) if labels else "Employee"


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
    }), 200
