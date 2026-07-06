"""Resolve a typed reference in a chat message to a lifecycle anchor.

A user types things like "summarize 580-659", "how's job 290 release 153 going", or
"what's up with submittal SUB-1234". We parse the first release/submittal reference and
resolve it to a concrete anchor: {kind, job, release, submittal_id, label}.

Reuses the job-log numeric search (`_search_by_number` / `_job_prefix_range`) so BB resolves
references exactly the way QuickSearch does. Returns None when no reference is present (the
agent then asks the user to name one).
"""
import re

from app.logging_config import get_logger
from app.models import Releases, Submittals

logger = get_logger(__name__)

# "580-659" or "580 659" — job (1-3 digits) then a release token that starts with a digit.
_JOB_REL = re.compile(r"\b(\d{1,3})\s*[-\s]\s*(\d[\w.]*)\b")
# "job 290 ... release 153"
_JOB_REL_WORDS = re.compile(r"\bjob\s+(\d{1,3})\b.*?\brelease\s+(\w[\w.]*)\b", re.IGNORECASE)
# "submittal <id>"
_SUBMITTAL = re.compile(r"\bsubmittal\s+([\w.\-/]+)", re.IGNORECASE)
# a lone job reference: "job 290" or a bare 1-3 digit number
_LONE_JOB = re.compile(r"\bjob\s+(\d{1,3})\b|(?<![\w-])(\d{1,3})(?![\w-])")


def _release_anchor(job, release):
    return {"kind": "release", "job": int(job), "release": str(release),
            "submittal_id": None, "label": f"release {job}-{release}"}


def _resolve_release(job, rel_token):
    """Find the concrete release for job + a release token (may be a prefix)."""
    job = int(job)
    exact = Releases.query.filter_by(job=job, release=str(rel_token)).first()
    if exact:
        return _release_anchor(job, exact.release)
    # Prefix match (e.g. rel_token "15" -> "153") — reuse the job-log numeric search.
    from app.brain.job_log.routes import _search_by_number
    releases, _ = _search_by_number(str(job), str(rel_token))
    releases = [r for r in releases if r.job == job]
    if len(releases) == 1:
        return _release_anchor(job, releases[0].release)
    if releases:
        # Ambiguous release token — anchor at the job so the bundle shows all matches.
        return {"kind": "release", "job": job, "release": None,
                "submittal_id": None, "label": f"job {job}"}
    return None


def _resolve_job_only(job):
    job = int(job)
    exists = Releases.query.filter_by(job=job).first() or \
        Submittals.query.filter_by(project_number=str(job)).first()
    if not exists:
        return None
    return {"kind": "release", "job": job, "release": None,
            "submittal_id": None, "label": f"job {job}"}


def _resolve_submittal(token):
    s = Submittals.query.filter_by(submittal_id=token).first()
    if not s:
        s = Submittals.query.filter(Submittals.submittal_id.ilike(f"{token}%")).first()
    if not s:
        return None
    return {"kind": "submittal", "job": None, "release": None,
            "submittal_id": s.submittal_id, "label": f"submittal {s.submittal_id}"}


def resolve(text: str):
    """Return an anchor dict for the first reference in `text`, or None."""
    if not text:
        return None
    t = text.strip()

    m = _SUBMITTAL.search(t)
    if m:
        anchor = _resolve_submittal(m.group(1))
        if anchor:
            return anchor

    m = _JOB_REL_WORDS.search(t)
    if m:
        anchor = _resolve_release(m.group(1), m.group(2))
        if anchor:
            return anchor

    m = _JOB_REL.search(t)
    if m:
        anchor = _resolve_release(m.group(1), m.group(2))
        if anchor:
            return anchor

    m = _LONE_JOB.search(t)
    if m:
        job = m.group(1) or m.group(2)
        anchor = _resolve_job_only(job)
        if anchor:
            return anchor

    return None
