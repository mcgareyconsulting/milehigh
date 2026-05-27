"""Installer-team scheduling: conflict detection & availability.

A release occupies an install window ``[start_install, comp_eta]`` inside its
installer team's lane on the PM Board timeline. ``comp_eta`` defaults to
``start_install + ceil(install_hrs / 24)`` calendar days (24 = 3 installers x
8 hrs/day), floored at 1 day — the same default the ``/gantt-data`` endpoint
uses. Two releases CONFLICT when they share an installer team and their windows
overlap (inclusive on both ends). A team is FREE for a window when none of its
eligible releases overlap it.

Eligibility mirrors the installer timeline (see ``get_gantt_data`` in
``app/brain/job_log/routes.py``): a hard start date (``start_install_formulaTF``
is False or NULL), an assigned installer, ``install_hrs > 0``, and a
``stage_group`` of FABRICATION / READY_TO_SHIP / COMPLETE.

These functions are pure reads — no writes, no events. Banana Boy's read-only
``propose_reschedule_install`` tool and any future conflict UI build on them.
"""
import math
from datetime import date, timedelta

from sqlalchemy import or_

from app.config import Config
from app.models import Releases

# Stage groups that belong on the installer timeline (matches /gantt-data).
TIMELINE_STAGE_GROUPS = ("FABRICATION", "READY_TO_SHIP", "COMPLETE")


def _install_hrs_valid(install_hrs) -> bool:
    """SQL ``> 0`` does not reliably exclude NaN across backends — guard here."""
    return (
        install_hrs is not None
        and not math.isnan(install_hrs)
        and install_hrs > 0
    )


def default_window_days(install_hrs) -> int:
    """Calendar days an install spans when no explicit comp_eta is set."""
    if not _install_hrs_valid(install_hrs):
        return 1
    return max(1, math.ceil(install_hrs / 24))


def release_window(rec: Releases):
    """Return ``(start_install, comp_eta)`` dates for a release.

    Falls back to the default window when ``comp_eta`` is unset. Returns
    ``(None, None)`` when the release has no start date.
    """
    start = rec.start_install
    if not start:
        return None, None
    if rec.comp_eta:
        return start, rec.comp_eta
    return start, start + timedelta(days=default_window_days(rec.install_hrs))


def windows_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    """Inclusive overlap test for two date ranges."""
    return a_start <= b_end and b_start <= a_end


def _eligible_query():
    """Releases eligible for the installer timeline (same filter as /gantt-data)."""
    return Releases.query.filter(
        Releases.start_install.isnot(None),
        or_(
            Releases.start_install_formulaTF.is_(False),
            Releases.start_install_formulaTF.is_(None),
        ),
        Releases.installer.isnot(None),
        Releases.installer != "",
        Releases.install_hrs.isnot(None),
        Releases.install_hrs > 0,
        Releases.stage_group.in_(TIMELINE_STAGE_GROUPS),
    )


def find_conflicts(installer, start, end, exclude_job=None, exclude_release=None):
    """Eligible releases for ``installer`` whose window overlaps ``[start, end]``.

    ``exclude_job`` / ``exclude_release`` drop the release being rescheduled so
    it never conflicts with itself. Returns a list of ``Releases`` rows.
    """
    if not installer:
        return []
    target = installer.strip()
    return [
        r for r in _overlapping_eligible(start, end, exclude_job, exclude_release)
        if (r.installer or "").strip() == target
    ]


def _overlapping_eligible(start, end, exclude_job=None, exclude_release=None):
    """All eligible releases whose window overlaps ``[start, end]`` — one query.

    Shared by ``find_conflicts`` and ``team_availability`` so a full
    availability sweep is a single DB round trip, not one query per team.
    """
    if not start or not end:
        return []
    hits = []
    for r in _eligible_query().all():
        if (
            exclude_job is not None
            and r.job == exclude_job
            and str(r.release) == str(exclude_release)
        ):
            continue
        if not _install_hrs_valid(r.install_hrs):
            continue
        r_start, r_end = release_window(r)
        if r_start is None:
            continue
        if windows_overlap(start, end, r_start, r_end):
            hits.append(r)
    return hits


def team_availability(start, end, teams=None, exclude_job=None, exclude_release=None):
    """Map every team to the conflicting releases (if any) in ``[start, end]``.

    Returns ``{team_name: [Releases, ...]}``; an empty list means the team is
    free. Defaults to the configured ``INSTALLER_TEAMS`` roster. One query
    total: the overlapping releases are fetched once and grouped by installer.
    """
    teams = list(teams if teams is not None else Config.INSTALLER_TEAMS)
    by_team = {}
    for r in _overlapping_eligible(start, end, exclude_job, exclude_release):
        by_team.setdefault((r.installer or "").strip(), []).append(r)
    return {t: by_team.get(t, []) for t in teams}


def free_teams(start, end, teams=None, exclude_job=None, exclude_release=None):
    """List of teams with no conflicting release in ``[start, end]``."""
    avail = team_availability(start, end, teams, exclude_job, exclude_release)
    return [t for t, conflicts in avail.items() if not conflicts]
