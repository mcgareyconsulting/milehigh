"""
@milehigh-header
schema_version: 1
purpose: Carmen's read-only release report. She picks the filters, reads the rows,
  and can hand back a PDF and CSV of that same cut.
exports:
  TOOL_QUERY_RELEASE_REPORT, TOOL_RENDER_RELEASE_REPORT
  QUERY_DEFINITION, RENDER_DEFINITION
  query_release_report, render_release_report
  for_carmen
imports_from: [app.reports, app.logging_config]
imported_by: [app.brain.carmen_chat.tools, app.brain.carmen_chat.agent]
invariants:
  - Read-only. The only write is the short-lived PDF and CSV file.
  - Totals and group counts are the full match. Row bodies shown to the model
    stop at DETAIL_CAP so a huge job log cannot fill the reply.
  - Dates are unset unless the caller passes them. There is no week default.
"""
from __future__ import annotations

from app.logging_config import get_logger
from app.reports.artifacts import save_release_report
from app.reports.release_export import render_release_csv, render_release_pdf
from app.reports.release_query import ReportArgsError, build_release_report, parse_release_report_args

logger = get_logger(__name__)

TOOL_QUERY_RELEASE_REPORT = "query_release_report"
TOOL_RENDER_RELEASE_REPORT = "render_release_report"

# Full rows Carmen may reason over in one call. Above this she gets counts only
# and has to narrow the filters, or hand the user the file.
DETAIL_CAP = 200

_FILTER_PROPS = {
    "scope": {
        "type": "string",
        "enum": ["active", "archive", "both"],
        "description": (
            "active = the job log (default). archive = the archive. both = either. "
            "Drafting workload is not in this tool. Soft-deleted rows are never included."
        ),
    },
    "tag": {
        "type": "array",
        "items": {
            "type": "string",
            "enum": ["contracted", "change_order", "mhmw_cost", "untagged"],
        },
        "description": (
            "Billing tags to keep. Omit to include every tag. "
            "untagged means blank or not one of the three tags."
        ),
    },
    "invoice": {
        "type": "string",
        "enum": ["any", "blank", "partial", "complete", "contains"],
        "description": (
            "Invoice progress, the Invoiced column. any (default), blank, "
            "partial (a percent), complete (X), or contains."
        ),
    },
    "invoice_q": {
        "type": "string",
        "description": "Required when invoice is contains. Literal text, such as 50.",
    },
    "install": {
        "type": "string",
        "enum": ["any", "blank", "partial", "complete", "contains"],
        "description": (
            "Install progress, the Install Prog column. Same choices as invoice."
        ),
    },
    "install_q": {
        "type": "string",
        "description": "Required when install is contains.",
    },
    "notes": {
        "type": "string",
        "description": (
            "Case-insensitive phrase in the Notes column only. "
            "'Needs Executed' matches a note that contains that phrase."
        ),
    },
    "project": {
        "type": "string",
        "description": "Job number (410) or part of the project name (Lennar).",
    },
    "release": {
        "type": "string",
        "description": "A release number (108) or a full id (410-108). 410-108 does not include 410-108.1.",
    },
    "stage": {
        "type": "string",
        "description": "Part of the stage name. 'complete' matches Install Complete and Ship Complete.",
    },
    "pm": {"type": "string", "description": "Part of the PM name or initials."},
    "installer": {"type": "string", "description": "Part of the assigned installer."},
    "released_from": {
        "type": "string",
        "description": (
            "ISO date. Only set this when the user names a start date. "
            "Omit it for the whole set. Do not default to this week."
        ),
    },
    "released_to": {
        "type": "string",
        "description": "ISO date, inclusive. Only set when the user names an end date.",
    },
    "group_by": {
        "type": "string",
        "enum": ["project", "stage", "pm", "installer", "billing_tag"],
        "description": "How to break the rows out. Default project.",
    },
}


def _definition(name: str, description: str) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": _FILTER_PROPS,
            "required": [],
        },
    }


QUERY_DEFINITION = _definition(
    TOOL_QUERY_RELEASE_REPORT,
    (
        "Read the release list and reason over it. Use this for a list, a breakout, "
        "billing tag, notes, invoice progress, install progress, project, stage, PM, "
        "or assigned installer — actives or archive. Returns every matching release's "
        "counts, plus the rows themselves when the set is small enough to read. "
        "Does not default to the current week. Does not change any data. "
        "This is not the hours-by-tag scorecard: use that only for a fab-hour total "
        "in a time window. Call this more than once to compare cuts. "
        "Then call render_release_report with the same filters to make the PDF and CSV."
    ),
)

RENDER_DEFINITION = _definition(
    TOOL_RENDER_RELEASE_REPORT,
    (
        "Build the PDF and CSV for a release report, and return the same figures as "
        "query_release_report. Use it once you know the filters, whenever the user "
        "wants a list, a breakout, or a file. The files contain every matching release. "
        "Pass the same filters you reasoned over. Do not default the dates to this week."
    ),
)


class _ToolArgs:
    """Adapt a tool-call dict to the report parser."""

    def __init__(self, raw: dict):
        self._raw = raw or {}

    def get(self, key, default=None):
        value = self._raw.get(key, default)
        if isinstance(value, list):
            return value[-1] if value else default
        return default if value is None else value

    def getlist(self, key):
        value = self._raw.get(key)
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        return [value]


def _slim(row: dict) -> dict:
    return {
        "release_number": row["release_number"],
        "job_name": row["job_name"],
        "description": row["description"],
        "billing_tag": row["billing_tag"],
        "stage": row["stage"],
        "pm": row["pm"],
        "installer": row["installer"],
        "install_progress": row["install_progress"],
        "invoice_progress": row["invoice_progress"],
        "fab_hrs": row["fab_hrs"],
        "install_hrs": row["install_hrs"],
        "notes": row["notes"],
        "released": row["released"],
        "set": row["set"],
        "splice": row["splice"],
    }


def _group_view(group: dict, *, with_numbers: bool) -> dict:
    view = {
        "label": group["label"],
        "releases": group["releases"],
        "fab_hrs": group["fab_hrs"],
        "install_hrs": group["install_hrs"],
    }
    if with_numbers:
        view["release_numbers"] = group["release_numbers"]
    return view


def for_carmen(report: dict) -> dict:
    """What the model is allowed to see. Counts always cover the full match."""
    total = report["totals"]["releases"]
    show_rows = total <= DETAIL_CAP
    visible = report["rows"] if show_rows else []
    omitted = total - len(visible)
    return {
        "complete": True,
        "rows_are_complete": omitted == 0,
        "rows_in_report": total,
        "rows_included": len(visible),
        "rows_omitted": omitted,
        "summary": report["summary"],
        "totals": report["totals"],
        "by_tag": [_group_view(group, with_numbers=show_rows) for group in report["by_tag"]],
        "group_by": report["group_label"],
        "groups": [_group_view(group, with_numbers=show_rows) for group in report["groups"]],
        "rows": [_slim(row) for row in visible],
        "how_to_read": (
            "totals, by_tag, and groups count every matching release. "
            "Reason only from those figures and from rows. "
            "If rows_omitted is greater than zero, you have not seen the releases. "
            "Do not invent them. Narrow with project, stage, pm, installer, or notes "
            "and call again to read a slice. The PDF and CSV, once rendered, list every row. "
            "In the chat, give the counts, the point, and at most a few examples. "
            "Do not paste the full list."
        ),
    }


def _run(raw: dict) -> tuple[dict | None, dict | None]:
    try:
        filters = parse_release_report_args(_ToolArgs(raw))
    except ReportArgsError as exc:
        return None, {"error": str(exc)}
    return build_release_report(filters), None


def query_release_report(context=None, **raw):
    """Look at a cut of the release list. context is unused; the tool is read-only."""
    del context
    report, error = _run(raw)
    if error:
        return error
    return for_carmen(report)


def render_release_report(context=None, **raw):
    """Same cut as the query, plus a PDF and a CSV of every matching row."""
    report, error = _run(raw)
    if error:
        return error
    payload = for_carmen(report)
    user_id = (context or {}).get("user_id")
    try:
        saved = save_release_report(
            render_release_pdf(report),
            render_release_csv(report),
            report=report,
            user_id=user_id,
        )
    except Exception:
        logger.error("release_report_render_failed", user_id=user_id, exc_info=True)
        payload["files_error"] = "Could not build the PDF and CSV."
        return payload
    payload["pdf"] = {
        "artifact_id": saved["artifact_id"],
        "download_path": saved["pdf_download_path"],
        "filename": saved["pdf_filename"],
        "title": saved["title"],
    }
    payload["csv"] = {
        "artifact_id": saved["artifact_id"],
        "download_path": saved["csv_download_path"],
        "filename": saved["csv_filename"],
    }
    return payload
