"""Reconcile a Sunbelt rental line to one of our jobs.

Validated against the DB: Sunbelt's PO_Number IS the MHMW job number for the
large majority of rentals (exact match to releases.job / submittals.project_number).
The exceptions are exactly the signal we want — e.g. a mis-keyed PO (520) whose
address resolves to the correct job (530 East Oak Townhomes). So the resolver
tries PO first, then falls back to a normalized-address match, then submittals.
"""

import re

from app.models import db, Releases, Projects, Submittals


# Common US street-type suffixes, normalized to a single canonical token so
# 'STREET'/'ST', 'DRIVE'/'DR', etc. compare equal.
_SUFFIXES = {
    "STREET": "ST", "ST": "ST",
    "AVENUE": "AVE", "AVE": "AVE", "AV": "AVE",
    "BOULEVARD": "BLVD", "BLVD": "BLVD",
    "DRIVE": "DR", "DR": "DR",
    "ROAD": "RD", "RD": "RD",
    "LANE": "LN", "LN": "LN",
    "COURT": "CT", "CT": "CT",
    "PLACE": "PL", "PL": "PL",
    "CIRCLE": "CIR", "CIR": "CIR",
    "PARKWAY": "PKWY", "PKWY": "PKWY",
    "HIGHWAY": "HWY", "HWY": "HWY",
    "TERRACE": "TER", "TER": "TER",
}

# Trailing ', CO 80524' / 'CO 80524-1234' style state+zip.
_STATE_ZIP_RE = re.compile(r",?\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\s*$")


def normalize_address(value):
    """Normalize a street address for loose equality matching.

    Upper-cases, strips a trailing state+zip, replaces punctuation with spaces,
    standardizes street-type suffixes, and collapses whitespace. Designed so
    Sunbelt's '220 E OAK ST, FORT COLLINS' and our '220 E Oak St Fort Collins,
    CO 80524' normalize to the same key. Returns '' for falsy input.
    """
    if not value:
        return ""
    s = str(value).upper()
    s = _STATE_ZIP_RE.sub("", s)        # drop trailing state + zip
    s = re.sub(r"[.,]", " ", s)         # punctuation -> space
    tokens = [_SUFFIXES.get(t, t) for t in s.split() if t]
    return " ".join(tokens)


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


class RentalMatcher:
    """Resolves rentals to jobs using preloaded lookup maps (one query each).

    Build once per snapshot ingest, then call resolve() per row. Resolution order
    (first hit wins):
      1. PO number -> releases.job             (method 'po_number')
      2. PO number -> projects.job_number      (method 'po_number')
      3. normalized address -> projects        (method 'address')   # 520 -> 530
      4. PO number -> submittals.project_number (method 'submittal') # 490
      5. unmatched
    """

    def __init__(self):
        # releases.job (int) -> job_name
        self._release_names = {}
        for job, job_name in db.session.query(
            Releases.job, Releases.job_name
        ).distinct().all():
            if job is None or not job_name:
                continue
            self._release_names.setdefault(int(job), job_name)

        # projects: job_number (str) -> (name, job_number_int)
        #           normalized address -> (name, job_number_int)
        self._project_by_number = {}
        self._project_by_address = {}
        for name, job_number, address in db.session.query(
            Projects.name, Projects.job_number, Projects.address
        ).all():
            jn_int = _to_int(job_number)
            if job_number:
                self._project_by_number.setdefault(str(job_number).strip(), (name, jn_int))
            norm = normalize_address(address)
            if norm:
                self._project_by_address.setdefault(norm, (name, jn_int))

        # submittals: project_number (str) -> project_name
        self._submittal_names = {}
        for project_number, project_name in db.session.query(
            Submittals.project_number, Submittals.project_name
        ).distinct().all():
            if not project_number or not project_name:
                continue
            self._submittal_names.setdefault(str(project_number).strip(), project_name)

    def resolve(self, po_number, job_location):
        """Return (matched_job_number, matched_project_name, match_method)."""
        po = str(po_number).strip() if po_number else ""
        po_int = _to_int(po)

        if po_int is not None and po_int in self._release_names:
            return po_int, self._release_names[po_int], "po_number"

        if po in self._project_by_number:
            name, jn_int = self._project_by_number[po]
            return jn_int, name, "po_number"

        norm = normalize_address(job_location)
        if norm and norm in self._project_by_address:
            name, jn_int = self._project_by_address[norm]
            return jn_int, name, "address"

        if po in self._submittal_names:
            return po_int, self._submittal_names[po], "submittal"

        return None, None, "unmatched"
