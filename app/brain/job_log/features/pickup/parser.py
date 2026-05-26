"""
@milehigh-header
schema_version: 1
purpose: Parse a forwarded vendor pick-up email subject into a (job, release) job-log identifier.
exports:
  clean_subject: Strip Fwd:/Re: prefixes from an email subject.
  parse_subject: Extract the first job-release token (e.g. "123-V4") from a subject.
imports_from: [re]
imported_by: [app/brain/job_log/features/pickup/__init__, app/pickup_email/ingest]
invariants:
  - Matches a job-release token anywhere in the subject: digits, "-", optional "V", digits.
  - Mirrors the "NNN-NNN" / "NNN-VNNN" convention from app/trello/utils.extract_identifier
    but is position-independent and not width-locked, since vendor subjects vary.
  - Returns None when no identifier is present; the caller decides what to do (skip/log).
"""
import re
from typing import Optional, Tuple

# Job-release token: a run of digits, a hyphen, an optional "V", then digits.
# e.g. "123-456", "123-V4", "1234-V12". Case-insensitive on the V.
_IDENTIFIER_RE = re.compile(r"(\d{2,5})-(V?\d{1,5})", re.IGNORECASE)

# Leading reply/forward markers Gmail prepends to the subject.
_PREFIX_RE = re.compile(r"^\s*((re|fwd|fw)\s*:\s*)+", re.IGNORECASE)


def clean_subject(subject: Optional[str]) -> str:
    """Strip leading Re:/Fwd:/Fw: markers (repeated) and surrounding whitespace."""
    if not subject:
        return ""
    return _PREFIX_RE.sub("", subject).strip()


def parse_subject(subject: Optional[str]) -> Optional[Tuple[int, str]]:
    """
    Extract the first job-release identifier from an email subject.

    Returns (job_number:int, release:str) or None if no identifier is found.
    The release is upper-cased so a leading "v" normalizes to "V" to match how
    releases are stored (e.g. "V4").
    """
    if not subject:
        return None

    match = _IDENTIFIER_RE.search(subject)
    if not match:
        return None

    try:
        job_number = int(match.group(1))
    except (ValueError, TypeError):
        return None

    release = match.group(2).upper()
    return (job_number, release)
