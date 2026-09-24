"""
@milehigh-header
schema_version: 1
purpose: Filter the releases table and aggregate the full match. The list is the
  report — counts are computed from those rows, and nothing is truncated.
exports:
  ReportArgsError: Bad query string. The route turns it into a 400.
  ReleaseReportFilters: Parsed, validated filters.
  parse_release_report_args(args) -> ReleaseReportFilters
  build_release_report(filters) -> dict
imports_from: [re, datetime, dataclasses, sqlalchemy, app.models]
imported_by: [app/brain/carmen_chat/release_report.py, app/reports/release_export.py]
invariants:
  - Every row that matches is returned. There is no sample size and no week default.
  - Group counts and tag counts are sums of those rows, so they add up to the total.
  - A blank or unknown billing tag is Untagged, same bucket the hours tool uses.
  - Soft-deleted rows (is_active is False) stay out of Actives, Archive, and Both.
  - Non-finite fab or install hours count as zero so one legacy NaN cannot poison the sum.
  - Install hours are also reported "each family once": a splice's pool hours are not
    added again when its parent is in the same result. The stored sum is still reported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import not_, or_

from app.datetime_utils import format_datetime_mountain
from app.models import RELEASE_TAG_LABELS, RELEASE_TAGS, Releases

SCOPES = ("active", "archive", "both")
GROUP_BY = ("project", "stage", "pm", "installer", "billing_tag")
PROGRESS_MODES = ("any", "blank", "partial", "complete", "contains")
TAG_ORDER = ("contracted", "change_order", "mhmw_cost", "untagged")

SCOPE_LABELS = {
    "active": "Actives",
    "archive": "Archive",
    "both": "Actives and archive",
}
GROUP_LABELS = {
    "project": "Project",
    "stage": "Stage",
    "pm": "PM",
    "installer": "Assigned installer",
    "billing_tag": "Billing tag",
}
PROGRESS_LABELS = {
    "blank": "blank",
    "partial": "in progress",
    "complete": "complete (X)",
}

_SCOPE_ALIASES = {
    "active": "active",
    "actives": "active",
    "archive": "archive",
    "archived": "archive",
    "both": "both",
}
_GROUP_ALIASES = {
    "project": "project",
    "projects": "project",
    "stage": "stage",
    "pm": "pm",
    "installer": "installer",
    "assigned_installer": "installer",
    "assigned installer": "installer",
    "billing_tag": "billing_tag",
    "billing tag": "billing_tag",
    "tag": "billing_tag",
}
_TAG_ALIASES = {"untagged": "untagged", "none": "untagged", "blank": "untagged"}
for _slug, _label in RELEASE_TAG_LABELS.items():
    _TAG_ALIASES[_slug] = _slug
    _TAG_ALIASES[_label.casefold()] = _slug
    _TAG_ALIASES[_label.casefold().replace(" ", "")] = _slug

_PROGRESS_RE = re.compile(r"^\d+(?:\.\d+)?\s*%?$")
_RELEASE_TOKEN = re.compile(r"^(\d+)\s*-\s*(\S+)$")
_MAX_LEN = {
    "notes": 200,
    "project": 128,
    "release": 40,
    "stage": 128,
    "pm": 32,
    "installer": 64,
    "invoice_q": 32,
    "install_q": 32,
}


class ReportArgsError(ValueError):
    """The query string cannot be run. Message is safe to show the user."""


@dataclass(frozen=True)
class ReleaseReportFilters:
    scope: str = "active"
    tags: tuple[str, ...] = ()
    invoice: str = "any"
    invoice_q: str = ""
    install: str = "any"
    install_q: str = ""
    notes: str = ""
    project: str = ""
    release: str = ""
    stage: str = ""
    pm: str = ""
    installer: str = ""
    released_from: date | None = None
    released_to: date | None = None
    group_by: str = "project"


def _finite_hours(value) -> float:
    """Hours as a float. Non-finite values (legacy NaN rows) read as zero.

    Same coercion as ``eos_metrics.finite_hours``. Kept here so a report that
    includes the archive does not import the Carmen metrics module.
    """
    if value is None:
        return 0.0
    try:
        hrs = float(value)
    except (TypeError, ValueError):
        return 0.0
    if hrs != hrs or hrs in (float("inf"), float("-inf")):
        return 0.0
    return round(hrs, 2)


def _one(args, key) -> str:
    if hasattr(args, "getlist"):
        values = [v for v in args.getlist(key) if v is not None and str(v).strip() != ""]
        if values:
            return str(values[-1]).strip()
    raw = args.get(key, "")
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        raw = raw[-1] if raw else ""
    return str(raw).strip()


def _many(args, key) -> list[str]:
    raw: list[str] = []
    if hasattr(args, "getlist"):
        raw.extend(str(v) for v in args.getlist(key) if v is not None)
    else:
        value = args.get(key, "")
        if isinstance(value, (list, tuple)):
            raw.extend(str(v) for v in value if v is not None)
        elif value:
            raw.append(str(value))
    parts: list[str] = []
    for item in raw:
        parts.extend(piece.strip() for piece in item.split(","))
    return [piece for piece in parts if piece]


def _bounded(key: str, value: str) -> str:
    limit = _MAX_LEN[key]
    if len(value) > limit:
        raise ReportArgsError("Search text is too long.")
    return value


def _choice(value: str, aliases: dict[str, str], allowed_label: str, default: str | None) -> str:
    if not value:
        if default is None:
            raise ReportArgsError(f"{allowed_label} is required.")
        return default
    picked = aliases.get(value.casefold())
    if picked is None:
        choices = ", ".join(sorted(set(aliases.values())))
        raise ReportArgsError(f"{allowed_label} must be one of: {choices}.")
    return picked


def _parse_date(value: str, label: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ReportArgsError(f"{label} must be a date (YYYY-MM-DD).") from exc


def parse_release_report_args(args) -> ReleaseReportFilters:
    """Validate a query string (Flask MultiDict or a mapping) into filters."""
    scope = _choice(_one(args, "scope"), _SCOPE_ALIASES, "Set", "active")
    group_by = _choice(_one(args, "group_by"), _GROUP_ALIASES, "Break out by", "project")

    tags: list[str] = []
    for raw in _many(args, "tag"):
        slug = _TAG_ALIASES.get(raw.casefold())
        if slug is None:
            known = ", ".join([*RELEASE_TAG_LABELS.values(), "Untagged"])
            raise ReportArgsError(f"Billing tag must be one of: {known}.")
        if slug not in tags:
            tags.append(slug)

    invoice = _choice(_one(args, "invoice") or "any", {m: m for m in PROGRESS_MODES}, "Invoice progress", "any")
    install = _choice(_one(args, "install") or "any", {m: m for m in PROGRESS_MODES}, "Install progress", "any")
    invoice_q = _bounded("invoice_q", _one(args, "invoice_q"))
    install_q = _bounded("install_q", _one(args, "install_q"))
    if invoice == "contains" and not invoice_q:
        raise ReportArgsError("Type the invoice progress text to search for.")
    if install == "contains" and not install_q:
        raise ReportArgsError("Type the install progress text to search for.")

    released_from = _parse_date(_one(args, "released_from"), "Released from")
    released_to = _parse_date(_one(args, "released_to"), "Released to")
    if released_from and released_to and released_from > released_to:
        raise ReportArgsError("Released from is after released to.")

    return ReleaseReportFilters(
        scope=scope,
        tags=tuple(tags),
        invoice=invoice,
        invoice_q=invoice_q,
        install=install,
        install_q=install_q,
        notes=_bounded("notes", _one(args, "notes")),
        project=_bounded("project", _one(args, "project")),
        release=_bounded("release", _one(args, "release")),
        stage=_bounded("stage", _one(args, "stage")),
        pm=_bounded("pm", _one(args, "pm")),
        installer=_bounded("installer", _one(args, "installer")),
        released_from=released_from,
        released_to=released_to,
        group_by=group_by,
    )


def progress_bucket(value) -> str:
    """How a Job Log progress cell reads: blank, complete (X), a percent, or other."""
    if value is None:
        return "blank"
    text = str(value).strip()
    if not text or text.upper() == "O":
        return "blank"
    if text.upper() == "X":
        return "complete"
    if _PROGRESS_RE.match(text):
        return "partial"
    return "other"


def _text_contains(value, needle: str) -> bool:
    if not needle:
        return True
    return needle.casefold() in str(value or "").casefold()


def _progress_matches(value, mode: str, needle: str) -> bool:
    if mode == "any":
        return True
    if mode == "contains":
        return needle.casefold() in str(value or "").casefold()
    return progress_bucket(value) == mode


def _job_number(term: str) -> int | None:
    """A job-number token that fits the integer column, or None when it is a name."""
    if not term.isdigit() or len(term) > 9:
        return None
    job = int(term)
    if job > 2_147_483_647:
        return None
    return job


def _like_pattern(term: str, *, contains: bool) -> str:
    # '#' is the LIKE escape so a search for "100%" stays a literal percent.
    escaped = term.replace("#", "##").replace("%", "#%").replace("_", "#_")
    return f"%{escaped}%" if contains else escaped


def _contains(column, term: str):
    return column.ilike(_like_pattern(term, contains=True), escape="#")


def _equals_ci(column, term: str):
    return column.ilike(_like_pattern(term, contains=False), escape="#")


def _apply_scope(query, scope: str):
    alive = or_(Releases.is_active.is_(None), Releases.is_active.is_(True))
    not_archived = or_(Releases.is_archived.is_(False), Releases.is_archived.is_(None))
    query = query.filter(alive)
    if scope == "active":
        return query.filter(not_archived)
    if scope == "archive":
        return query.filter(Releases.is_archived.is_(True))
    return query


def _apply_tags(query, tags: tuple[str, ...]):
    if not tags:
        return query
    clauses = []
    known = [tag for tag in tags if tag in RELEASE_TAGS]
    if known:
        clauses.append(Releases.release_tag.in_(known))
    if "untagged" in tags:
        clauses.append(or_(
            Releases.release_tag.is_(None),
            Releases.release_tag == "",
            not_(Releases.release_tag.in_(tuple(RELEASE_TAGS))),
        ))
    return query.filter(or_(*clauses))


def _apply_text(query, filters: ReleaseReportFilters):
    # Notes are matched in Python (see build_release_report) so a search for
    # "100%" stays literal. LIKE treats % as a wildcard.
    if filters.project:
        job = _job_number(filters.project)
        if job is not None:
            query = query.filter(or_(
                Releases.job == job,
                _contains(Releases.job_name, filters.project),
            ))
        else:
            query = query.filter(_contains(Releases.job_name, filters.project))
    if filters.release:
        token = _RELEASE_TOKEN.fullmatch(filters.release)
        job = _job_number(token.group(1)) if token else None
        if token and job is not None:
            query = query.filter(
                Releases.job == job,
                _equals_ci(Releases.release, token.group(2)),
            )
        else:
            query = query.filter(_contains(Releases.release, filters.release))
    if filters.stage:
        query = query.filter(_contains(Releases.stage, filters.stage))
    if filters.pm:
        query = query.filter(_contains(Releases.pm, filters.pm))
    if filters.installer:
        query = query.filter(_contains(Releases.installer, filters.installer))
    if filters.released_from:
        query = query.filter(
            Releases.released.isnot(None),
            Releases.released >= filters.released_from,
        )
    if filters.released_to:
        query = query.filter(
            Releases.released.isnot(None),
            Releases.released <= filters.released_to,
        )
    return query


def _billing(raw) -> tuple[str, str]:
    slug = (raw or "").strip()
    if slug in RELEASE_TAGS:
        return slug, RELEASE_TAG_LABELS[slug]
    return "untagged", "Untagged"


def _release_number(job, release) -> str:
    return f"{job}-{release}"


def _number_key(token: str):
    job_text, _, rel = token.partition("-")
    try:
        job = int(job_text)
    except ValueError:
        job = 0

    def parts(text: str):
        return tuple(
            int(piece) if piece.isdigit() else piece.casefold()
            for piece in re.split(r"(\d+)", text)
            if piece
        )

    return (job, parts(rel))


def _row_from(release) -> dict:
    tag_key, tag_label = _billing(release.release_tag)
    released = release.released.isoformat() if isinstance(release.released, date) else ""
    return {
        "id": release.id,
        "job": release.job,
        "release": release.release,
        "release_number": _release_number(release.job, release.release),
        "job_name": release.job_name or "",
        "description": release.description or "",
        "billing_tag": tag_label,
        "billing_tag_key": tag_key,
        "release_tag": (release.release_tag or "").strip() or None,
        "stage": release.stage or "",
        "pm": release.pm or "",
        "installer": release.installer or "",
        "install_progress": release.job_comp or "",
        "invoice_progress": release.invoiced or "",
        "fab_hrs": _finite_hours(release.fab_hrs),
        "install_hrs": _finite_hours(release.install_hrs),
        "additional_install_hrs": _finite_hours(release.additional_install_hrs),
        "notes": release.notes or "",
        "released": released,
        "set": "Archive" if release.is_archived else "Active",
        "parent_release_id": release.parent_release_id,
        "splice": bool(release.parent_release_id),
    }


def _group_key(row: dict, group_by: str) -> str:
    if group_by == "project":
        return f"{row['job']}|{(row['job_name'] or '').casefold()}"
    if group_by == "stage":
        return (row["stage"] or "").casefold()
    if group_by == "pm":
        return (row["pm"] or "").casefold()
    if group_by == "installer":
        return (row["installer"] or "").casefold()
    return row["billing_tag_key"]


def _group_label(row: dict, group_by: str) -> str:
    if group_by == "project":
        name = (row["job_name"] or "").strip()
        return f"{row['job']} — {name}" if name else str(row["job"])
    if group_by == "stage":
        return row["stage"] or "(No stage)"
    if group_by == "pm":
        return row["pm"] or "(No PM)"
    if group_by == "installer":
        return row["installer"] or "(No installer)"
    return row["billing_tag"]


def _sum_hours(rows: list[dict], field: str) -> float:
    return round(sum(row[field] for row in rows), 2)


def _net_install(rows: list[dict]) -> float:
    """Install hours counting a splice family once.

    The parent's install_hrs is the whole pool. A splice's install_hrs includes
    the hours it drew from that pool, plus any additional hours from outside it.
    When the parent is also in the result, only the additional hours are added
    for the splice. A splice whose parent is absent counts its own install_hrs.
    """
    present = {row["id"] for row in rows}
    total = 0.0
    for row in rows:
        parent = row["parent_release_id"]
        if parent and parent in present:
            total += row["additional_install_hrs"]
        else:
            total += row["install_hrs"]
    return round(total, 2)


def _groups(rows: list[dict], group_by: str) -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in rows:
        key = _group_key(row, group_by)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "key": key,
                "label": _group_label(row, group_by),
                "rows": [],
            }
            buckets[key] = bucket
        bucket["rows"].append(row)
    groups = []
    for bucket in buckets.values():
        members = bucket["rows"]
        numbers = [member["release_number"] for member in members]
        numbers.sort(key=_number_key)
        groups.append({
            "key": bucket["key"],
            "label": bucket["label"],
            "releases": len(members),
            "fab_hrs": _sum_hours(members, "fab_hrs"),
            "install_hrs": _sum_hours(members, "install_hrs"),
            "release_numbers": numbers,
        })
    groups.sort(key=lambda group: (-group["fab_hrs"], -group["releases"], group["label"].casefold()))
    return groups


def _by_tag(rows: list[dict], selected: tuple[str, ...]) -> list[dict]:
    grouped = {group["key"]: group for group in _groups(rows, "billing_tag")}
    keys = list(TAG_ORDER)
    for key in grouped:
        if key not in keys:
            keys.append(key)
    present = {key for key, group in grouped.items() if group["releases"]}
    show = set(selected) | present if selected else present
    out = []
    for key in keys:
        if key not in show:
            continue
        group = grouped.get(key)
        if selected and key not in selected and (group is None or group["releases"] == 0):
            continue
        if group is None and key not in selected:
            continue
        label = "Untagged" if key == "untagged" else RELEASE_TAG_LABELS.get(key, key)
        out.append({
            "key": key,
            "label": group["label"] if group else label,
            "releases": group["releases"] if group else 0,
            "fab_hrs": group["fab_hrs"] if group else 0,
            "install_hrs": group["install_hrs"] if group else 0,
            "release_numbers": group["release_numbers"] if group else [],
        })
    return out


def _applied(filters: ReleaseReportFilters) -> list[str]:
    lines = [SCOPE_LABELS[filters.scope]]
    if filters.tags:
        labels = [
            "Untagged" if tag == "untagged" else RELEASE_TAG_LABELS[tag]
            for tag in filters.tags
        ]
        lines.append("Billing tag: " + ", ".join(labels))
    if filters.invoice == "contains":
        lines.append(f'Invoice progress contains "{filters.invoice_q}"')
    elif filters.invoice != "any":
        lines.append(f"Invoice progress: {PROGRESS_LABELS[filters.invoice]}")
    if filters.install == "contains":
        lines.append(f'Install progress contains "{filters.install_q}"')
    elif filters.install != "any":
        lines.append(f"Install progress: {PROGRESS_LABELS[filters.install]}")
    if filters.notes:
        lines.append(f'Notes contain "{filters.notes}"')
    if filters.project:
        lines.append(f"Project: {filters.project}")
    if filters.release:
        lines.append(f"Release: {filters.release}")
    if filters.stage:
        lines.append(f"Stage: {filters.stage}")
    if filters.pm:
        lines.append(f"PM: {filters.pm}")
    if filters.installer:
        lines.append(f"Assigned installer: {filters.installer}")
    if filters.released_from or filters.released_to:
        start = filters.released_from.isoformat() if filters.released_from else None
        end = filters.released_to.isoformat() if filters.released_to else None
        if start and end:
            lines.append(f"Released {start} to {end}")
        elif start:
            lines.append(f"Released on or after {start}")
        else:
            lines.append(f"Released on or before {end}")
    lines.append(f"Break out by {GROUP_LABELS[filters.group_by].lower()}")
    return lines


def _order_rows(rows: list[dict], groups: list[dict], group_by: str) -> list[dict]:
    rank = {group["key"]: index for index, group in enumerate(groups)}
    rows.sort(key=lambda row: (
        rank.get(_group_key(row, group_by), len(rank)),
        _number_key(row["release_number"]),
        row["id"] or 0,
    ))
    return rows


def build_release_report(filters: ReleaseReportFilters) -> dict:
    """Run the filters and return every matching release plus the rollups."""
    query = _apply_text(_apply_tags(_apply_scope(Releases.query, filters.scope), filters.tags), filters)
    matched = [
        _row_from(release)
        for release in query.all()
        if _text_contains(release.notes, filters.notes)
        and _progress_matches(release.job_comp, filters.install, filters.install_q)
        and _progress_matches(release.invoiced, filters.invoice, filters.invoice_q)
    ]
    matched.sort(key=lambda row: row["id"] or 0)
    groups = _groups(matched, filters.group_by)
    ordered = _order_rows(matched, groups, filters.group_by)
    stored_install = _sum_hours(ordered, "install_hrs")
    net_install = _net_install(ordered)
    install_note = None
    if abs(stored_install - net_install) >= 0.01:
        install_note = (
            "Install hours on a splice sit inside its parent's pool. "
            "Adding every row counts that pool twice. "
            f"Each family once: {net_install:g} install hrs."
        )
    applied = _applied(filters)
    return {
        "scope": filters.scope,
        "group_by": filters.group_by,
        "group_label": GROUP_LABELS[filters.group_by],
        "applied": applied,
        "summary": " · ".join(applied),
        "complete": True,
        "generated_at": f"{format_datetime_mountain(datetime.now(timezone.utc))} MT",
        "totals": {
            "releases": len(ordered),
            "fab_hrs": _sum_hours(ordered, "fab_hrs"),
            "install_hrs": stored_install,
            "install_hrs_net": net_install,
            "install_note": install_note,
        },
        "by_tag": _by_tag(ordered, filters.tags),
        "groups": groups,
        "rows": ordered,
    }


def report_filename(report: dict, extension: str, today: date | None = None) -> str:
    day = (today or date.today()).isoformat()
    return f"release-report-{report['scope']}-{day}.{extension}"
