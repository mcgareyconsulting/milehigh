"""
@milehigh-header
schema_version: 1
purpose: Deterministic parser for GC weekly lookahead schedules exported from MS Project
  (the "AMC - 3WK Lookahead" PDFs Wood Partners emails). The export has a real text layer
  laid out as `<WBS id> [resource] <task name> <Day M/D/YY> <Day M/D/YY>`, so extraction
  is pure table-reading — NO OCR/vision. Rows are grouped under their `Building A/B/C/D`
  summary row, and a keyword classifier isolates the MHMW (Mile High Metal Works) metal
  scope (structural steel, embeds, anchor bolts / hold-downs) whose GC need dates we
  cross-check against our releases.
exports:
  parse_activities(pdf_path): every activity row -> [{wbs_id, building, resource, task_name, start, finish, page}]
  is_metal_scope(task_name): True if the activity is MHMW steel/embed scope
  metal_activities(pdf_path): parse_activities filtered to is_metal_scope
  KNOWN_RESOURCES, METAL_KEYWORDS
imports_from: [re, datetime, pypdf]
imported_by: [app/brain/lookahead/service.py, tests]
invariants:
  - Read-only text extraction; never mutates the PDF or the DB.
  - Two-digit years are 2000-relative (schedule horizon is well within 21st century).
"""
import re
from datetime import date

# Subcontractor/resource tokens seen in the leftmost column of the export. Used to peel a
# resource prefix off the task text (a task row is "<id> <resource> <task> <dates>", while
# a summary row is "<id> <task> <dates>" with no resource).
KNOWN_RESOURCES = {
    "A&J", "Baker", "RMP", "Hi-Power", "REC", "WP", "GTH", "SWI", "MEP",
    "Pearson", "Schindler", "Survey", "CASI", "Cowboys", "Tricor",
}

# MHMW scope: the metal activities whose GC need dates matter to us. Deliberately narrow —
# excludes wood-framing look-alikes ("A&J Stair Core Construction", and A&J shear-wall
# "Hardware (ATS Rods... Hold Downs...)" — bare "hold down" is a framing term, so it is NOT
# a keyword; "Anchor Bolt Install & Hold-Down Verification" still matches on "anchor bolt",
# the concrete/steel interface for our embeds & baseplates).
METAL_KEYWORDS = ("structural steel", "embed", "anchor bolt")

# "<id> <middle> <Day M/D/YY> <Day M/D/YY>" — the middle holds an optional resource + name.
_ROW = re.compile(
    r"^(\d+)\s+(.*?)\s+"
    r"([A-Z][a-z]{2}\s+\d{1,2}/\d{1,2}/\d{2})\s+"
    r"([A-Z][a-z]{2}\s+\d{1,2}/\d{1,2}/\d{2})\s*$"
)
_DATE = re.compile(r"^[A-Z][a-z]{2}\s+(\d{1,2})/(\d{1,2})/(\d{2})$")
_BUILDING = re.compile(r"^Building\s+([A-Z])\b", re.IGNORECASE)


def _parse_date(token):
    m = _DATE.match((token or "").strip())
    if not m:
        return None
    month, day, yr = (int(x) for x in m.groups())
    return date(2000 + yr, month, day)


def _split_resource(text):
    """Peel a known resource prefix off the middle column; return (resource|None, task_name)."""
    for res in sorted(KNOWN_RESOURCES, key=len, reverse=True):  # longest first ("Hi-Power")
        if text == res or text.startswith(res + " "):
            return res, text[len(res):].strip()
    return None, text


def parse_activities(pdf_path):
    """Every schedule row as a dict, tagged with the Building summary it falls under."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    activities = []
    current_building = None
    for pageno, page in enumerate(reader.pages, start=1):
        for raw in (page.extract_text() or "").splitlines():
            m = _ROW.match(raw.strip())
            if not m:
                continue
            wbs_id, middle, start_s, finish_s = m.groups()
            # A bare "Building X" summary row (no resource prefix) switches the group.
            b = _BUILDING.match(middle)
            if b:
                current_building = f"Building {b.group(1).upper()}"
            resource, task_name = _split_resource(middle)
            activities.append(
                {
                    "wbs_id": int(wbs_id),
                    "building": current_building,
                    "resource": resource,
                    "task_name": task_name,
                    "start": _parse_date(start_s),
                    "finish": _parse_date(finish_s),
                    "page": pageno,
                }
            )
    return activities


def is_metal_scope(task_name):
    t = (task_name or "").lower()
    return any(k in t for k in METAL_KEYWORDS)


def metal_activities(pdf_path):
    """MHMW-relevant activities only — the ones we cross-check against our releases."""
    return [a for a in parse_activities(pdf_path) if is_metal_scope(a["task_name"])]
