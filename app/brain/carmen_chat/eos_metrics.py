"""EOS leadership scorecard metrics — read-only queries for Carmen.

First pass: metrics we can derive from job-log / stage events / T&M without
external accounting or unbuilt features (release tags, CO log, safety, etc.).

Week convention is always Monday–Sunday on the Mountain calendar, matching
the scorecard export columns. Archived releases are excluded unless a metric
says otherwise (none do in v1).

Each metric carries a ``scorecard_owner`` (display name) and ``queried_by``
hints so Carmen can route "my metrics" / "David's numbers" correctly.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_

from app.api.helpers import get_fab_modifier
from app.datetime_utils import get_mountain_timezone
from app.models import (
    RELEASE_TAG_LABELS,
    Releases,
    ReleaseEvents,
    TMTicket,
    db,
)

# ---------------------------------------------------------------------------
# Owner registry — who queries what
# ---------------------------------------------------------------------------

# Keys match scorecard owners. ``aliases`` are matched case-insensitively
# against User.first_name / last_name / username fragments.
OWNERS: dict[str, dict[str, Any]] = {
    "david": {
        "display_name": "David Servold",
        "role": "Drafting",
        "aliases": ("david", "servold", "dservold"),
        "metrics": ("hours_released_to_production",),
    },
    "bill": {
        "display_name": "Bill O'Neill",
        "role": "Leadership / PM hygiene",
        "aliases": ("bill", "o'neill", "oneill", "boneill"),
        "metrics": ("yellow_dates",),
    },
    "luis": {
        "display_name": "Luis Solano",
        "role": "Shop / Warehouse",
        "aliases": ("luis", "solano", "lsolano"),
        "metrics": ("fabrication_hours", "qc_completed", "fab_backlog"),
    },
    "doug": {
        "display_name": "Doug Ferrin",
        "role": "Field",
        "aliases": ("doug", "ferrin", "dferrin"),
        "metrics": ("tm_hours", "target_dates_met", "releases_met_or_allocated"),
    },
}

METRIC_CATALOG: dict[str, dict[str, Any]] = {
    "hours_released_to_production": {
        "label": "Hours Released to Production",
        "owner_key": "david",
        "goal": ">= 400 fab hrs / week",
        "kind": "weekly_flow",
    },
    "yellow_dates": {
        "label": "Yellow Dates",
        "owner_key": "bill",
        "goal": "= 0 (hard start-install dates in the past)",
        "kind": "snapshot",
    },
    "fabrication_hours": {
        "label": "Fabrication Hours",
        "owner_key": "luis",
        "goal": ">= 400 fab hrs completed / week",
        "kind": "weekly_flow",
    },
    "qc_completed": {
        "label": "QC Completed",
        "owner_key": "luis",
        "goal": "= 100%",
        "kind": "weekly_flow",
    },
    "fab_backlog": {
        "label": "Fab Backlog (remaining hours)",
        "owner_key": "luis",
        "goal": "companion to shop capacity (not on scorecard)",
        "kind": "snapshot",
    },
    "tm_hours": {
        "label": "T&M Hours",
        "owner_key": "doug",
        "goal": "<= 50 hrs / week",
        "kind": "weekly_flow",
    },
    "target_dates_met": {
        "label": "Target Dates Met",
        "owner_key": "doug",
        "goal": ">= 75%",
        "kind": "weekly_flow",
    },
    "releases_met_or_allocated": {
        "label": "Releases met or allocated",
        "owner_key": "doug",
        "goal": ">= 90%",
        "kind": "weekly_flow",
    },
}

DETAIL_CAP = 100

# Legacy Trello list labels → canonical stages (fab-capacity calibration).
_STAGE_ALIASES: dict[str, str] = {
    "shipping completed": "Ship Complete",
    "shipping planning": "Ship Planning",
    "paint complete": "Paint Complete",
    "fit up complete.": "Fitup Complete",
    "fit up complete": "Fitup Complete",
    "cut start": "Cut Start",
    "store at mhmw for shipping": "Store at MHMW",
    "welded": "Welded QC",
}

# Stages that count as "past fab QC" for the QC-completed denominator/numerator.
_POST_FAB_STAGES = frozenset({
    "Welded QC",
    "Paint Start",
    "Paint Complete",
    "Store at MHMW",
    "Ship Planning",
    "Ship Complete",
    "Install Start",
    "Install Complete",
    "Complete",
})
_QC_STAGE = "Welded QC"
_COMPLETE_STAGES = frozenset({"Install Complete", "Complete"})


# ---------------------------------------------------------------------------
# Week helpers
# ---------------------------------------------------------------------------

def mountain_today() -> date:
    return datetime.now(get_mountain_timezone()).date()


def mon_sun_week_bounds(ref: date) -> tuple[date, date]:
    """(Monday, Sunday) for the Mon–Sun week containing ``ref``."""
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def parse_week_of(value) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def resolve_week(
    weeks_back: int = 0,
    week_of: str | None = None,
) -> tuple[date, date, date]:
    """Return (monday, sunday, anchor)."""
    anchor = parse_week_of(week_of)
    if anchor is None:
        try:
            n = int(weeks_back) if weeks_back is not None else 0
        except (TypeError, ValueError):
            n = 0
        n = max(0, min(n, 104))
        anchor = mountain_today() - timedelta(weeks=n)
    monday, sunday = mon_sun_week_bounds(anchor)
    return monday, sunday, anchor


def format_week_label(monday: date, sunday: date) -> str:
    return f"{monday.strftime('%b')} {monday.day} – {sunday.strftime('%b')} {sunday.day}"


def format_range_label(start: date | None, end: date) -> str:
    """Human label for an arbitrary window; open-ended below reads as 'through'."""
    if start is None:
        return f"through {end.strftime('%b')} {end.day}, {end.year}"
    if start.year == end.year:
        return (f"{start.strftime('%b')} {start.day} – "
                f"{end.strftime('%b')} {end.day}, {end.year}")
    return (f"{start.strftime('%b')} {start.day}, {start.year} – "
            f"{end.strftime('%b')} {end.day}, {end.year}")


def resolve_window(
    weeks_back: int = 0,
    week_of: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Resolve the query window, in either of two modes.

    **Week mode** (the default, and what the EOS scorecard means): no ``start``
    and no ``end``, so ``weeks_back`` / ``week_of`` pick a Monday–Sunday week the
    same way they always have. The scorecard columns are Mon–Sun and nothing here
    changes that.

    **Range mode**: either bound present. ``start`` omitted means no lower bound
    ("everything up to X"); ``end`` omitted means today (Mountain). Reversed
    bounds are swapped rather than returning nothing, since a model that has
    inverted them is asking for the span between two dates either way.

    Returns a dict carrying ``mode``, the resolved ``start`` (None only when
    unbounded) and ``end`` as dates, plus the display payload.
    """
    lo = parse_week_of(start)
    hi = parse_week_of(end)
    if start and lo is None:
        return {"error": f"could not parse start date: {start!r} (expected YYYY-MM-DD)"}
    if end and hi is None:
        return {"error": f"could not parse end date: {end!r} (expected YYYY-MM-DD)"}

    if lo is None and hi is None:
        monday, sunday, anchor = resolve_week(weeks_back, week_of)
        return {
            "mode": "week",
            "start": monday,
            "end": sunday,
            "anchor": anchor,
            "payload": week_dict(monday, sunday, anchor),
        }

    if hi is None:
        hi = mountain_today()
    if lo is not None and lo > hi:
        lo, hi = hi, lo
    return {
        "mode": "range",
        "start": lo,
        "end": hi,
        "anchor": hi,
        "payload": {
            "start": lo.isoformat() if lo else None,
            "end": hi.isoformat(),
            "label": format_range_label(lo, hi),
        },
    }


def finite_hours(value) -> float:
    """Hours as a float, with non-finite values read as zero.

    Nine legacy archived rows carry a literal ``NaN`` in ``fab_hrs`` /
    ``install_hrs``. The non-archived filter hides them from every metric today,
    but a single NaN would poison a sum and then serialize as invalid JSON, so
    the coercion lives with the read rather than with the filter that happens to
    be shielding it.
    """
    if value is None:
        return 0.0
    try:
        hrs = float(value)
    except (TypeError, ValueError):
        return 0.0
    return hrs if hrs == hrs and hrs not in (float("inf"), float("-inf")) else 0.0


def week_dict(monday: date, sunday: date, anchor: date) -> dict:
    return {
        "start": monday.isoformat(),
        "end": sunday.isoformat(),
        "label": format_week_label(monday, sunday),
        "anchor": anchor.isoformat(),
    }


def week_created_at_bounds(monday: date, sunday: date) -> tuple[datetime, datetime]:
    """Naive-UTC [start, end) covering Mountain Mon 00:00 .. next Mon 00:00."""
    mtn = get_mountain_timezone()
    start_local = datetime(monday.year, monday.month, monday.day, 0, 0, 0, tzinfo=mtn)
    next_mon = sunday + timedelta(days=1)
    end_local = datetime(next_mon.year, next_mon.month, next_mon.day, 0, 0, 0, tzinfo=mtn)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def _active_release_filter():
    """Non-archived, not soft-deleted."""
    return (
        Releases.is_archived.is_(False),
        or_(Releases.is_active.is_(None), Releases.is_active.is_(True)),
    )


def _owner_payload(owner_key: str) -> dict:
    o = OWNERS[owner_key]
    return {
        "scorecard_owner": o["display_name"],
        "owner_key": owner_key,
        "owner_role": o["role"],
    }


def _metric_shell(metric_id: str, monday: date, sunday: date, anchor: date,
                  window: dict | None = None) -> dict:
    """Common head of every metric payload.

    ``window`` is the resolved window from ``resolve_window``. In week mode the
    payload keeps its historical ``week`` key; in range mode ``week`` is
    **omitted** rather than filled with range bounds, so nothing downstream can
    read an arbitrary span as a Mon–Sun week. ``window`` is always present.
    """
    cat = METRIC_CATALOG[metric_id]
    out = {
        "metric": metric_id,
        "metric_label": cat["label"],
        "goal": cat["goal"],
        "kind": cat["kind"],
        **_owner_payload(cat["owner_key"]),
    }
    if window is None or window["mode"] == "week":
        out["week"] = week_dict(monday, sunday, anchor)
    out["window"] = {
        "mode": (window or {}).get("mode", "week"),
        **((window or {}).get("payload") or week_dict(monday, sunday, anchor)),
    }
    return out


# ---------------------------------------------------------------------------
# Owner resolution
# ---------------------------------------------------------------------------

def resolve_owner_key(name: str | None = None, user=None) -> str | None:
    """Map a free-text name or User row to an owner key."""
    tokens: list[str] = []
    if name:
        tokens.append(str(name).strip().casefold())
    if user is not None:
        for attr in ("first_name", "last_name", "username"):
            val = getattr(user, attr, None)
            if val:
                tokens.append(str(val).strip().casefold())
        # Combined "first last"
        first = (getattr(user, "first_name", None) or "").strip()
        last = (getattr(user, "last_name", None) or "").strip()
        if first or last:
            tokens.append(f"{first} {last}".strip().casefold())

    blob = " ".join(tokens)
    if not blob:
        return None
    for key, meta in OWNERS.items():
        for alias in meta["aliases"]:
            if alias in blob:
                return key
    return None


def list_owner_metrics() -> list[dict]:
    """Catalog for Carmen: who owns which metrics."""
    out = []
    for key, meta in OWNERS.items():
        metrics = []
        for mid in meta["metrics"]:
            cat = METRIC_CATALOG[mid]
            metrics.append({
                "metric": mid,
                "label": cat["label"],
                "goal": cat["goal"],
                "kind": cat["kind"],
            })
        out.append({
            "owner_key": key,
            "display_name": meta["display_name"],
            "role": meta["role"],
            "metrics": metrics,
        })
    return out


# ---------------------------------------------------------------------------
# Stage helpers (shop throughput)
# ---------------------------------------------------------------------------

def canonicalize_stage(label: str | None) -> str | None:
    if not label or not str(label).strip():
        return None
    s = str(label).strip()
    # Exact known
    if get_fab_modifier(s) != 1.0 or s in (
        "Released", "Material Ordered", "Hold", "Paint Complete", "Store at MHMW",
        "Ship Planning", "Ship Complete", "Install Start", "Install Complete",
        "Complete", "Welded QC", "Weld Complete",
    ):
        # get_fab_modifier returns 1.0 for unknown AND for Released — so also
        # check alias table and STAGE_HOUR keys via a broader map.
        pass
    alias = _STAGE_ALIASES.get(s.casefold())
    if alias:
        return alias
    # Case-insensitive match against known remaining map via modifier path
    # (unknown stays as stripped original; remaining% will be 1.0).
    return s


def _remaining_fab_pct(stage: str | None) -> float:
    """Remaining fab fraction 0–1 after alias canonicalize."""
    if not stage:
        return 1.0
    return float(get_fab_modifier(canonicalize_stage(stage) or stage))


def _stage_from_to(payload: dict | None) -> tuple[str | None, str | None]:
    """Extract (from_stage, to_stage) from either modern or legacy payload shapes."""
    p = payload or {}
    from_stage = p.get("from")
    to_stage = p.get("to")
    if from_stage is None and "old_value" in p:
        from_stage = p.get("old_value")
    if to_stage is None and "new_value" in p:
        to_stage = p.get("new_value")
    return from_stage, to_stage


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def hours_released_to_production(
    weeks_back: int = 0,
    week_of: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Hours released to the job log: release count + fab_hrs by ``released`` date.

    Two windows, one query. With neither ``start`` nor ``end`` this is David's
    Mon–Sun EOS metric, unchanged. With either bound it answers an arbitrary
    span — the form any admin asks in ("hours released last month", "since
    August 9th").

    Every result carries a **billing-tag breakdown** (N1's
    ``Releases.release_tag``: Contracted / Change Order / MHMW Cost) with an
    explicit ``untagged`` bucket. The bucket is deliberately visible: the tag
    only became required at creation on 2026-08-09 and the historical rows are
    untagged until N10 backfills them, so a total that silently dropped untagged
    hours would be wrong by most of its own value. ``tag_coverage`` states how
    much of the answer is actually classified.
    """
    window = resolve_window(weeks_back, week_of, start, end)
    if "error" in window:
        return window
    lo, hi = window["start"], window["end"]

    filters = [Releases.released.isnot(None), Releases.released <= hi]
    if lo is not None:
        filters.append(Releases.released >= lo)
    rows = (
        Releases.query.filter(*filters, *_active_release_filter())
        .order_by(Releases.released.asc(), Releases.job.asc(), Releases.release.asc())
        .all()
    )

    total_fab = 0.0
    detail = []
    buckets: dict[str | None, dict[str, Any]] = {}
    for r in rows:
        hrs = finite_hours(r.fab_hrs)
        total_fab += hrs
        tag = r.release_tag if r.release_tag in RELEASE_TAG_LABELS else None
        b = buckets.setdefault(tag, {"release_count": 0, "fab_hrs": 0.0})
        b["release_count"] += 1
        b["fab_hrs"] += hrs
        if len(detail) < DETAIL_CAP:
            detail.append({
                "identifier": f"{r.job}-{r.release}",
                "project_name": r.job_name,
                "description": r.description,
                "fab_hrs": hrs,
                "released": r.released.isoformat() if r.released else None,
                "stage": r.stage,
                "release_tag": tag,
                "release_tag_label": RELEASE_TAG_LABELS.get(tag, "Untagged"),
            })

    # Canonical tag order first, untagged last — so the answer always reads in the
    # same order whether or not a given tag appears in the window.
    by_tag = []
    for tag in list(RELEASE_TAG_LABELS) + [None]:
        b = buckets.get(tag)
        if b is None:
            continue
        by_tag.append({
            "release_tag": tag,
            "label": RELEASE_TAG_LABELS.get(tag, "Untagged"),
            "release_count": b["release_count"],
            "fab_hrs": round(b["fab_hrs"], 2),
        })
    untagged = buckets.get(None, {"release_count": 0, "fab_hrs": 0.0})
    tagged_count = len(rows) - untagged["release_count"]

    monday, sunday = window["start"] or window["end"], window["end"]
    out = _metric_shell("hours_released_to_production", monday, sunday,
                        window["anchor"], window=window)
    out.update({
        "release_count": len(rows),
        "total_fab_hrs": round(total_fab, 2),
        "by_tag": by_tag,
        "tag_coverage": {
            "tagged_releases": tagged_count,
            "untagged_releases": untagged["release_count"],
            "untagged_fab_hrs": round(untagged["fab_hrs"], 2),
            "tagged_pct": round(100.0 * tagged_count / len(rows), 1) if rows else None,
            "note": (
                "release_tag became required at creation on 2026-08-09; releases "
                "created before that are untagged until the N10 bulk-edit backfill "
                "runs. Report the untagged bucket rather than dropping it."
            ),
        },
        "releases": detail,
        "releases_truncated": max(0, len(rows) - len(detail)),
        "rules": {
            "date_field": "released",
            "week": "Monday–Sunday (Mountain)",
            "window_mode": window["mode"],
            "includes_archived": False,
            "null_fab_hrs_as": 0,
        },
    })
    return out


def yellow_dates(
    weeks_back: int = 0,
    week_of: str | None = None,
) -> dict[str, Any]:
    """Bill: hard start-install dates in the past (amber cells) — goal = 0.

    Snapshot as of ``as_of`` (Sunday of the requested week, or Mountain today
    when asking about the current week).
    """
    monday, sunday, anchor = resolve_week(weeks_back, week_of)
    today = mountain_today()
    # For a fully past week use that Sunday; for current/future week use today.
    as_of = min(sunday, today)

    rows = (
        Releases.query.filter(
            Releases.start_install.isnot(None),
            Releases.start_install_formulaTF.is_(False),
            # ASAP rows count: ASAP no longer stamps a placeholder date, it flags a
            # date a person set by hand. Excluding them would hide the most urgent
            # overdue rows we have from a scored metric.
            or_(
                Releases.start_install_no_color.is_(False),
                Releases.start_install_no_color.is_(None),
            ),
            Releases.start_install < as_of,
            *_active_release_filter(),
        )
        .order_by(Releases.start_install.asc(), Releases.job.asc())
        .all()
    )
    detail = []
    for r in rows:
        if len(detail) >= DETAIL_CAP:
            break
        days_overdue = (as_of - r.start_install).days if r.start_install else None
        detail.append({
            "identifier": f"{r.job}-{r.release}",
            "project_name": r.job_name,
            "description": r.description,
            "start_install": r.start_install.isoformat() if r.start_install else None,
            "days_overdue": days_overdue,
            "stage": r.stage,
            "pm": r.pm,
            "installer": r.installer,
        })
    out = _metric_shell("yellow_dates", monday, sunday, anchor)
    out.update({
        "as_of": as_of.isoformat(),
        "yellow_count": len(rows),
        "goal_met": len(rows) == 0,
        "releases": detail,
        "releases_truncated": max(0, len(rows) - len(detail)),
        "rules": {
            "definition": (
                "Hard start_install (formulaTF=false), not no-color, "
                "date strictly before as_of — same as job-log amber hard dates. "
                "ASAP rows are included: their date is hand-set, like any other"
            ),
            "includes_archived": False,
            "ship_dates_counted": False,
        },
    })
    return out


def fabrication_hours(
    weeks_back: int = 0,
    week_of: str | None = None,
) -> dict[str, Any]:
    """Luis: fab hours completed this week via stage transitions × fab_hrs.

    completed = fab_hrs × max(0, remaining%(from) − remaining%(to))
    Bucketed by ReleaseEvents.created_at in the Mon–Sun Mountain week.
    """
    monday, sunday, anchor = resolve_week(weeks_back, week_of)
    start_utc, end_utc = week_created_at_bounds(monday, sunday)

    events = (
        ReleaseEvents.query.filter(
            ReleaseEvents.action == "update_stage",
            ReleaseEvents.created_at >= start_utc,
            ReleaseEvents.created_at < end_utc,
            or_(ReleaseEvents.is_system_echo.is_(False), ReleaseEvents.is_system_echo.is_(None)),
        )
        .all()
    )

    # Prefetch fab_hrs for (job, release) pairs
    keys = {(ev.job, str(ev.release)) for ev in events if ev.job is not None}
    fab_by_key: dict[tuple, float] = {}
    archived_keys: set[tuple] = set()
    if keys:
        job_ids = {j for j, _ in keys}
        for r in Releases.query.filter(Releases.job.in_(job_ids)).all():
            k = (r.job, str(r.release))
            if k not in keys:
                continue
            if r.is_archived or r.is_active is False:
                archived_keys.add(k)
                continue
            fab_by_key[k] = float(r.fab_hrs) if r.fab_hrs is not None else 0.0

    total = 0.0
    credited = 0
    skipped_backward = 0
    skipped_unknown = 0
    detail = []
    for ev in events:
        k = (ev.job, str(ev.release))
        if k in archived_keys:
            continue
        from_stage, to_stage = _stage_from_to(ev.payload)
        from_pct = _remaining_fab_pct(from_stage)
        to_pct = _remaining_fab_pct(to_stage)
        delta = from_pct - to_pct
        if delta <= 0:
            skipped_backward += 1
            continue
        fab = fab_by_key.get(k)
        if fab is None:
            # Release missing or filtered — still credit if we can load fab from event job
            skipped_unknown += 1
            continue
        hrs = fab * delta
        total += hrs
        credited += 1
        if len(detail) < DETAIL_CAP:
            detail.append({
                "identifier": f"{ev.job}-{ev.release}",
                "from_stage": from_stage,
                "to_stage": to_stage,
                "fab_hrs_on_release": fab,
                "completed_hrs": round(hrs, 2),
                "event_at": ev.created_at.isoformat() if ev.created_at else None,
            })

    out = _metric_shell("fabrication_hours", monday, sunday, anchor)
    out.update({
        "total_fab_hrs_completed": round(total, 2),
        "transitions_credited": credited,
        "transitions_skipped_backward_or_noop": skipped_backward,
        "transitions_skipped_no_release": skipped_unknown,
        "transitions": detail,
        "transitions_truncated": max(0, credited - len(detail)),
        "rules": {
            "formula": "fab_hrs × max(0, remaining%(from) − remaining%(to))",
            "remaining_map": "STAGE_HOUR_PERCENTAGES / get_fab_modifier (Banana Code)",
            "aliases": list(_STAGE_ALIASES.keys()),
            "includes_archived": False,
            "source": "ReleaseEvents action=update_stage",
        },
    })
    return out


def qc_completed(
    weeks_back: int = 0,
    week_of: str | None = None,
) -> dict[str, Any]:
    """Luis: of releases that left fab into post-fab stages this week, % that hit Welded QC.

    Denominator: distinct releases with an update_stage *to* a post-fab stage
    (Welded QC and beyond) in the week.
    Numerator: those whose to_stage is Welded QC, or that also had a Welded QC
    transition in the week, or whose current stage is Welded QC+.
    """
    monday, sunday, anchor = resolve_week(weeks_back, week_of)
    start_utc, end_utc = week_created_at_bounds(monday, sunday)

    events = (
        ReleaseEvents.query.filter(
            ReleaseEvents.action == "update_stage",
            ReleaseEvents.created_at >= start_utc,
            ReleaseEvents.created_at < end_utc,
            or_(ReleaseEvents.is_system_echo.is_(False), ReleaseEvents.is_system_echo.is_(None)),
        )
        .all()
    )

    # release key -> set of canonical to-stages this week
    to_stages: dict[tuple, set[str]] = {}
    for ev in events:
        _from_raw, to_raw = _stage_from_to(ev.payload)
        to_c = canonicalize_stage(to_raw)
        if not to_c or to_c not in _POST_FAB_STAGES:
            continue
        k = (ev.job, str(ev.release))
        to_stages.setdefault(k, set()).add(to_c)

    if not to_stages:
        out = _metric_shell("qc_completed", monday, sunday, anchor)
        out.update({
            "denominator": 0,
            "numerator": 0,
            "pct": None,
            "goal_met": None,
            "releases": [],
            "rules": {
                "definition": (
                    "Among releases that entered a post-fab stage this week "
                    "(Welded QC → Complete), % that hit Welded QC this week"
                ),
            },
        })
        return out

    # Drop archived
    job_ids = {j for j, _ in to_stages}
    active_keys = set()
    current_stage: dict[tuple, str | None] = {}
    for r in Releases.query.filter(Releases.job.in_(job_ids)).all():
        k = (r.job, str(r.release))
        if k not in to_stages:
            continue
        if r.is_archived or r.is_active is False:
            continue
        active_keys.add(k)
        current_stage[k] = r.stage

    denom_keys = [k for k in to_stages if k in active_keys]
    detail = []
    numerator = 0
    for k in sorted(denom_keys, key=lambda x: (x[0], x[1])):
        stages = to_stages[k]
        hit_qc = _QC_STAGE in stages
        if hit_qc:
            numerator += 1
        if len(detail) < DETAIL_CAP:
            detail.append({
                "identifier": f"{k[0]}-{k[1]}",
                "post_fab_stages_this_week": sorted(stages),
                "hit_welded_qc": hit_qc,
                "current_stage": current_stage.get(k),
            })

    denom = len(denom_keys)
    pct = round(100.0 * numerator / denom, 1) if denom else None
    out = _metric_shell("qc_completed", monday, sunday, anchor)
    out.update({
        "denominator": denom,
        "numerator": numerator,
        "pct": pct,
        "goal_met": pct == 100.0 if pct is not None else None,
        "releases": detail,
        "releases_truncated": max(0, denom - len(detail)),
        "rules": {
            "definition": (
                "Releases with update_stage into post-fab (Welded QC+) this week; "
                "numerator = those with a Welded QC transition in the week"
            ),
            "includes_archived": False,
        },
    })
    return out


def fab_backlog(
    weeks_back: int = 0,
    week_of: str | None = None,
) -> dict[str, Any]:
    """Luis companion: remaining fab hours on the active job log (snapshot)."""
    monday, sunday, anchor = resolve_week(weeks_back, week_of)
    rows = (
        Releases.query.filter(*_active_release_filter())
        .all()
    )
    total = 0.0
    in_fab = 0
    for r in rows:
        mod = get_fab_modifier(r.stage)
        if mod <= 0:
            continue
        hrs = float(r.fab_hrs) if r.fab_hrs is not None else 0.0
        total += hrs * mod
        in_fab += 1
    out = _metric_shell("fab_backlog", monday, sunday, anchor)
    out.update({
        "remaining_fab_hrs": round(total, 2),
        "releases_with_remaining_fab": in_fab,
        "rules": {
            "definition": "sum(fab_hrs × get_fab_modifier(stage)) over non-archived active releases",
            "note": "Snapshot now; week args only label the scorecard week context",
        },
    })
    return out


def tm_hours(
    weeks_back: int = 0,
    week_of: str | None = None,
) -> dict[str, Any]:
    """Doug: sum of T&M labor hours with date_of_work in the Mon–Sun week."""
    monday, sunday, anchor = resolve_week(weeks_back, week_of)
    tickets = (
        TMTicket.query.filter(
            TMTicket.date_of_work.isnot(None),
            TMTicket.date_of_work >= monday,
            TMTicket.date_of_work <= sunday,
            TMTicket.status.notin_(["void", "rejected"]),
        )
        .all()
    )
    total_reg = total_ot = total_dt = 0.0
    ticket_count = 0
    detail = []
    for t in tickets:
        ticket_count += 1
        reg = ot = dt = 0.0
        for line in (t.labor or []):
            if not isinstance(line, dict):
                continue
            try:
                reg += float(line.get("hours_reg") or 0)
            except (TypeError, ValueError):
                pass
            try:
                ot += float(line.get("hours_ot") or 0)
            except (TypeError, ValueError):
                pass
            try:
                dt += float(line.get("hours_dt") or 0)
            except (TypeError, ValueError):
                pass
        total_reg += reg
        total_ot += ot
        total_dt += dt
        if len(detail) < DETAIL_CAP:
            detail.append({
                "ticket_id": t.id,
                "job": t.job,
                "date_of_work": t.date_of_work.isoformat() if t.date_of_work else None,
                "status": t.status,
                "hours_reg": round(reg, 2),
                "hours_ot": round(ot, 2),
                "hours_dt": round(dt, 2),
                "hours_total": round(reg + ot + dt, 2),
            })
    total = total_reg + total_ot + total_dt
    out = _metric_shell("tm_hours", monday, sunday, anchor)
    out.update({
        "ticket_count": ticket_count,
        "hours_reg": round(total_reg, 2),
        "hours_ot": round(total_ot, 2),
        "hours_dt": round(total_dt, 2),
        "total_tm_hours": round(total, 2),
        "tickets": detail,
        "tickets_truncated": max(0, ticket_count - len(detail)),
        "rules": {
            "date_field": "date_of_work",
            "excludes_statuses": ["void", "rejected"],
            "note": "Only tickets entered in the T&M module — undercounts paper tickets",
        },
    })
    return out


def _is_complete(r: Releases) -> bool:
    if (r.job_comp or "").strip().upper() == "X":
        return True
    return (r.stage or "") in _COMPLETE_STAGES


def target_dates_met(
    weeks_back: int = 0,
    week_of: str | None = None,
) -> dict[str, Any]:
    """Doug: of hard start_install dates falling in the week, % complete.

    First-pass definition (confirm with Doug):
    - Denominator: non-archived hard dates (formulaTF=false, ASAP included — an
      ASAP date is hand-set like any other) with start_install in the Mon–Sun week.
    - Numerator: those now Install Complete / Complete / job_comp=X.
    """
    monday, sunday, anchor = resolve_week(weeks_back, week_of)
    rows = (
        Releases.query.filter(
            Releases.start_install.isnot(None),
            Releases.start_install >= monday,
            Releases.start_install <= sunday,
            Releases.start_install_formulaTF.is_(False),
            *_active_release_filter(),
        )
        .order_by(Releases.start_install.asc())
        .all()
    )
    met = 0
    detail = []
    for r in rows:
        done = _is_complete(r)
        if done:
            met += 1
        if len(detail) < DETAIL_CAP:
            detail.append({
                "identifier": f"{r.job}-{r.release}",
                "project_name": r.job_name,
                "start_install": r.start_install.isoformat() if r.start_install else None,
                "stage": r.stage,
                "job_comp": r.job_comp,
                "met": done,
                "installer": r.installer,
            })
    denom = len(rows)
    pct = round(100.0 * met / denom, 1) if denom else None
    out = _metric_shell("target_dates_met", monday, sunday, anchor)
    out.update({
        "denominator": denom,
        "numerator": met,
        "pct": pct,
        "goal_met": (pct is not None and pct >= 75.0),
        "releases": detail,
        "releases_truncated": max(0, denom - len(detail)),
        "rules": {
            "definition": (
                "Hard start_install in week; met = stage Install Complete/Complete "
                "or job_comp=X. First-pass definition — confirm with Doug."
            ),
            "includes_archived": False,
        },
    })
    return out


def releases_met_or_allocated(
    weeks_back: int = 0,
    week_of: str | None = None,
) -> dict[str, Any]:
    """Doug: of releases with start_install in the week, % complete or crew-assigned.

    First-pass definition (confirm with Doug):
    - Denominator: non-archived with start_install in Mon–Sun week (hard or formula).
    - Met: Install Complete / Complete / job_comp=X.
    - Allocated: installer non-empty.
    - Success: met OR allocated.
    """
    monday, sunday, anchor = resolve_week(weeks_back, week_of)
    rows = (
        Releases.query.filter(
            Releases.start_install.isnot(None),
            Releases.start_install >= monday,
            Releases.start_install <= sunday,
            *_active_release_filter(),
        )
        .order_by(Releases.start_install.asc())
        .all()
    )
    success = 0
    met_n = 0
    allocated_n = 0
    detail = []
    for r in rows:
        done = _is_complete(r)
        allocated = bool((r.installer or "").strip())
        ok = done or allocated
        if done:
            met_n += 1
        if allocated:
            allocated_n += 1
        if ok:
            success += 1
        if len(detail) < DETAIL_CAP:
            detail.append({
                "identifier": f"{r.job}-{r.release}",
                "project_name": r.job_name,
                "start_install": r.start_install.isoformat() if r.start_install else None,
                "stage": r.stage,
                "installer": r.installer,
                "met": done,
                "allocated": allocated,
                "success": ok,
            })
    denom = len(rows)
    pct = round(100.0 * success / denom, 1) if denom else None
    out = _metric_shell("releases_met_or_allocated", monday, sunday, anchor)
    out.update({
        "denominator": denom,
        "numerator": success,
        "pct": pct,
        "met_count": met_n,
        "allocated_count": allocated_n,
        "goal_met": (pct is not None and pct >= 90.0),
        "releases": detail,
        "releases_truncated": max(0, denom - len(detail)),
        "rules": {
            "definition": (
                "start_install in week; success = complete (Install Complete/"
                "Complete/job_comp=X) OR installer assigned. First-pass — confirm with Doug."
            ),
            "includes_archived": False,
        },
    })
    return out


METRIC_EXECUTORS = {
    "hours_released_to_production": hours_released_to_production,
    "yellow_dates": yellow_dates,
    "fabrication_hours": fabrication_hours,
    "qc_completed": qc_completed,
    "fab_backlog": fab_backlog,
    "tm_hours": tm_hours,
    "target_dates_met": target_dates_met,
    "releases_met_or_allocated": releases_met_or_allocated,
}


#: Metrics whose window can be an arbitrary date range rather than a Mon–Sun week.
#: The rest of the scorecard is defined weekly and stays that way — forwarding
#: start/end to them would invent a semantic nobody agreed to.
RANGE_CAPABLE_METRICS = frozenset({"hours_released_to_production"})


def get_eos_metric(
    metric: str,
    weeks_back: int = 0,
    week_of: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Dispatch a single metric by id.

    ``start`` / ``end`` are only meaningful for ``RANGE_CAPABLE_METRICS``; asking
    for a range on a weekly-by-definition metric is an error rather than a
    silently-ignored argument, so the caller finds out that the number they got
    back is not the number they asked for.
    """
    mid = (metric or "").strip().casefold().replace(" ", "_").replace("-", "_")
    # friendly aliases
    aliases = {
        "david_fab_hours": "hours_released_to_production",
        "hours_released": "hours_released_to_production",
        "fab_hours_released": "hours_released_to_production",
        "yellow": "yellow_dates",
        "luis_fab_hours": "fabrication_hours",
        "shop_fab_hours": "fabrication_hours",
        "fab_hours": "fabrication_hours",
        "qc": "qc_completed",
        "backlog": "fab_backlog",
        "tm": "tm_hours",
        "target_dates": "target_dates_met",
        "allocated": "releases_met_or_allocated",
        "releases_allocated": "releases_met_or_allocated",
    }
    mid = aliases.get(mid, mid)
    fn = METRIC_EXECUTORS.get(mid)
    if fn is None:
        return {
            "error": f"unknown metric: {metric!r}",
            "known_metrics": list(METRIC_EXECUTORS.keys()),
            "owners": list_owner_metrics(),
        }
    if (start or end) and mid not in RANGE_CAPABLE_METRICS:
        return {
            "error": (
                f"{mid} is a weekly (Mon–Sun) metric and does not accept a date "
                f"range — use weeks_back or week_of"
            ),
            "range_capable_metrics": sorted(RANGE_CAPABLE_METRICS),
        }
    if mid in RANGE_CAPABLE_METRICS:
        return fn(weeks_back=weeks_back, week_of=week_of, start=start, end=end)
    return fn(weeks_back=weeks_back, week_of=week_of)


def get_eos_metrics_for_owner(
    owner: str | None = None,
    weeks_back: int = 0,
    week_of: str | None = None,
    *,
    user=None,
) -> dict[str, Any]:
    """All metrics for a scorecard owner (David / Bill / Luis / Doug).

    If ``owner`` is omitted, resolve from the signed-in ``user``.
    """
    key = resolve_owner_key(owner, user=user)
    if key is None:
        return {
            "error": (
                "could not resolve scorecard owner — pass owner as David, Bill, "
                "Luis, or Doug, or sign in as one of those users"
            ),
            "owners": list_owner_metrics(),
        }
    meta = OWNERS[key]
    metrics = []
    for mid in meta["metrics"]:
        metrics.append(METRIC_EXECUTORS[mid](weeks_back=weeks_back, week_of=week_of))
    monday, sunday, anchor = resolve_week(weeks_back, week_of)
    return {
        "owner_key": key,
        "scorecard_owner": meta["display_name"],
        "owner_role": meta["role"],
        "week": week_dict(monday, sunday, anchor),
        "metrics": metrics,
        "metric_ids": list(meta["metrics"]),
    }
