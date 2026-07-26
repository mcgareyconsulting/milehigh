"""Period → time-window resolution and day-bucketing, in Mountain time.

Event timestamps across the app are stored as naive UTC (see
``app/history/__init__.py`` and ``app/datetime_utils.py``). The user thinks in
Mountain-time days/weeks/months, so we compute window bounds and day-bucket keys
in America/Denver and hand back naive-UTC datetimes that line up with the stored
values.
"""
from datetime import datetime, timedelta, timezone

from app.datetime_utils import get_mountain_timezone

# A period is a trailing window measured in whole Mountain-time calendar days,
# always ending "now". Buckets are daily, so `day` yields a single bucket.
PERIOD_DAYS = {"day": 1, "week": 7, "month": 30}
DEFAULT_PERIOD = "week"


def _to_utc_naive(dt_aware):
    return dt_aware.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_iso_local(value, mtn):
    """Parse an ISO date/datetime override; a naive value is read as Mountain-local."""
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=mtn)
    return _to_utc_naive(dt)


def resolve_window(period=None, start=None, end=None):
    """Resolve a request's window.

    Returns ``(period_label, start_utc_naive, end_utc_naive)``. Explicit
    ``start``/``end`` ISO overrides win; otherwise ``period`` selects a trailing
    N-day window aligned to Mountain-time midnight.
    """
    mtn = get_mountain_timezone()
    now_local = datetime.now(mtn)

    if start or end:
        end_utc = _parse_iso_local(end, mtn) if end else _to_utc_naive(now_local)
        if start:
            start_utc = _parse_iso_local(start, mtn)
        else:
            start_utc = end_utc - timedelta(days=PERIOD_DAYS[DEFAULT_PERIOD])
        return "custom", start_utc, end_utc

    label = (period or DEFAULT_PERIOD).lower()
    days = PERIOD_DAYS.get(label, PERIOD_DAYS[DEFAULT_PERIOD])
    if label not in PERIOD_DAYS:
        label = DEFAULT_PERIOD
    start_date = (now_local - timedelta(days=days - 1)).date()
    start_local = datetime(start_date.year, start_date.month, start_date.day, tzinfo=mtn)
    return label, _to_utc_naive(start_local), _to_utc_naive(now_local)


def mountain_date_key(dt):
    """The Mountain-time calendar date (``YYYY-MM-DD``) a naive-UTC datetime falls on."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_mountain_timezone()).strftime("%Y-%m-%d")


def bucket_dates(start_utc, end_utc):
    """Ordered list of Mountain-time date keys spanning ``[start, end]`` inclusive.

    Used to zero-fill day-series so charts show empty days rather than gaps.
    """
    mtn = get_mountain_timezone()
    start_d = start_utc.replace(tzinfo=timezone.utc).astimezone(mtn).date()
    end_d = end_utc.replace(tzinfo=timezone.utc).astimezone(mtn).date()
    out, d = [], start_d
    while d <= end_d:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out
