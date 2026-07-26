"""
@milehigh-header
schema_version: 1
purpose: MOCK GC-lookahead cross-check wiring. Until the ingest pipeline (email -> bronze ->
  persisted LookaheadSchedule) is built, a job can be wired to a sample lookahead PDF (the one
  Bill forwarded from the GC) via MOCK_LOOKAHEADS. This module reads that PDF, runs the parser
  + cross-check engine against the job's LIVE releases/submittals, and returns a JSON-safe
  result the project page renders and the health score consumes. Only the *source* is mocked
  — the parsing, matching, slip math, and health impact are all real.
exports:
  crosscheck_for_job(job_number, release_models, submittal_models): result dict or None
  MOCK_LOOKAHEADS: job_number -> sample-schedule metadata
imports_from: [os, datetime, app.brain.lookahead.parser, app.brain.lookahead.crosscheck, app.logging_config]
imported_by: [app/brain/projects/service.py, tests]
invariants:
  - Read-only. Reads a sample PDF from disk + the passed-in models; never writes.
  - Returns None for any job not in MOCK_LOOKAHEADS or if the sample file is missing.
"""
import os
from datetime import date, datetime

from app.brain.lookahead import parser, crosscheck
from app.logging_config import get_logger

logger = get_logger(__name__)

_SAMPLES = os.path.join(os.path.dirname(__file__), "samples")

# Jobs wired to a sample GC lookahead until real ingestion lands. Keyed by job_number.
MOCK_LOOKAHEADS = {
    "560": {
        "gc": "Wood Partners",
        "issued": "2026-07-17",
        "file": "AMC_-_3WK_Lookahead_-_07172026.pdf",
        "subject": "Alta Metro - 3 Week Lookahead Update - 07/20",
    },
}


def _iso(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return value


def _xcheck_release(r):
    """Release model -> cross-check input dict (keeps real date objects for slip math)."""
    return {
        "release": r.release,
        "description": r.description,
        "stage": r.stage,
        "start_install": r.start_install,
        "comp_eta": r.comp_eta,
        "job_comp": r.job_comp,
        "invoiced": r.invoiced,
    }


def _xcheck_submittal(s):
    return {"rel": s.rel, "title": s.title, "type": s.type, "status": s.status}


def _serialize(result):
    out = dict(result)
    for k in ("gc_need", "gc_finish", "our_date"):
        out[k] = _iso(result.get(k))
    return out


def crosscheck_for_job(job_number, release_models, submittal_models):
    """Mock lookahead cross-check for a wired job, or None.

    Reads the sample GC PDF, runs parser.metal_activities + crosscheck.cross_check against
    the job's live releases/submittals, and returns a JSON-safe payload:
    {source, gc, issued, file, subject, activities:[cross-check results]}.
    """
    meta = MOCK_LOOKAHEADS.get(str(job_number))
    if not meta:
        return None

    pdf_path = os.path.join(_SAMPLES, meta["file"])
    if not os.path.exists(pdf_path):
        logger.warning("lookahead_sample_missing", job=str(job_number), file=meta["file"])
        return None

    try:
        activities = parser.metal_activities(pdf_path)
        results = crosscheck.cross_check(
            activities,
            [_xcheck_release(r) for r in release_models],
            [_xcheck_submittal(s) for s in submittal_models],
        )
    except Exception as exc:
        logger.error(
            "lookahead_crosscheck_failed",
            job=str(job_number),
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return None

    return {
        "source": "mock_forwarded_email",
        "gc": meta["gc"],
        "issued": meta["issued"],
        "file": meta["file"].replace("_", " "),
        "subject": meta["subject"],
        "activities": [_serialize(r) for r in results],
    }
