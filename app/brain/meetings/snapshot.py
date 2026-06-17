"""Pre/post-meeting Brain snapshots + reconciliation of agreed updates.

The premise (from the shop): meetings are where the team decides a release should ship,
an install date should move, a submittal's ball-in-court should flip — but those changes
only matter once they land on the Brain (job log / DWL). They routinely don't.

So a meeting now captures the job-log/DWL FIELD VALUES of the entities it discusses at two
points: a `pre_snapshot` when the meeting starts (bot dispatched) and a `post_snapshot`
when extraction runs (after the meeting ends). The extractor tags each agreed field change
with `expected_update` (target/field/new_value). `reconcile()` then checks whether that
change is actually reflected in the Brain by meeting end; if not, it flags the checklist
item `brain_update_pending=True` — a recommended action surfaced to the super user:
"you said you'd update this, the Brain still shows the old value."

Reading the live row at reconcile time IS the post-meeting Brain state (reconcile runs at
meeting end), so the pending check reads the row directly — robust to the snapshot's entity
scoping missing a late-mentioned job, and to events being dropped from the during-meeting
stream. The stored snapshots are the before/after record for display.
"""
from datetime import date, datetime

from app.models import db, Releases, Submittals
from app.logging_config import get_logger

logger = get_logger(__name__)

# The mutable job-log / DWL fields worth snapshotting + verifying. Also the allowlist that
# bounds what an LLM-supplied expected_update.field can name (no arbitrary getattr).
RELEASE_FIELDS = ("stage", "start_install", "comp_eta", "job_comp", "invoiced",
                  "num_guys", "installer")
SUBMITTAL_FIELDS = ("status", "ball_in_court", "due_date")


def _val(v):
    """JSON-safe scalar for a snapshot cell (dates -> ISO strings)."""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def capture_snapshot(meeting):
    """Snapshot the current job-log/DWL field values of the entities this meeting touches.

    Shape: {"captured_at": iso, "releases": {"480-146": {field: value}},
            "submittals": {"<id>": {field: value}}}. Entity scoping is shared with the
    extraction context (context.relevant_entities). Never raises — returns an empty-ish
    snapshot on any failure so capture can't break meeting creation/extraction.
    """
    from app.brain.meetings import context as meeting_context
    try:
        releases, submittals = meeting_context.relevant_entities(meeting)
    except Exception as e:  # noqa: BLE001 — scoping must never break the caller
        logger.warning("snapshot_scope_failed", meeting_id=getattr(meeting, "id", None),
                       error=str(e))
        releases, submittals = [], []

    snap = {"captured_at": datetime.utcnow().isoformat(), "releases": {}, "submittals": {}}
    for r in releases:
        snap["releases"][f"{r.job}-{r.release}"] = {
            f: _val(getattr(r, f, None)) for f in RELEASE_FIELDS
        }
    for s in submittals:
        snap["submittals"][str(s.submittal_id)] = {
            f: _val(getattr(s, f, None)) for f in SUBMITTAL_FIELDS
        }
    return snap


def sanitize_expected_update(raw):
    """Normalize an LLM-supplied brain_update into a stored expected_update, or None.

    Keeps only a well-formed {target, field, new_value} where target is release|submittal
    and field is in the allowlist for that target — so a hallucinated field name can never
    drive a getattr in reconcile()."""
    if not isinstance(raw, dict):
        return None
    target = (raw.get("target") or "").strip().lower()
    field = (raw.get("field") or "").strip().lower()
    new_value = raw.get("new_value")
    if new_value is None or not field:
        return None
    if target == "release" and field in RELEASE_FIELDS:
        pass
    elif target == "submittal" and field in SUBMITTAL_FIELDS:
        pass
    else:
        return None
    return {"target": target, "field": field, "new_value": _val(new_value)}


def _to_float(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _parse_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _matches(current, expected):
    """True when the Brain's current value already reflects the agreed new_value.

    Lenient on representation drift: dates parsed and compared as dates, numerics as
    floats, free text by case-insensitive equality or containment (so 'shipped' matches a
    'Ship Complete' stage). A missing current value never matches → the update is pending.
    """
    if current is None or expected is None:
        return False
    if isinstance(current, (date, datetime)):
        cd = current.date() if isinstance(current, datetime) else current
        ed = _parse_date(expected)
        return ed is not None and cd == ed
    cf, ef = _to_float(current), _to_float(expected)
    if cf is not None and ef is not None:
        return cf == ef
    cs, es = str(current).strip().lower(), str(expected).strip().lower()
    if not es:
        return False
    return cs == es or es in cs or cs in es


def _current_value(item):
    """The live Brain value for an item's expected_update field, or (None, False) when the
    item isn't anchored to the targeted record (can't verify → not flagged)."""
    eu = item.expected_update or {}
    target, field = eu.get("target"), eu.get("field")
    if target == "release" and item.release_id:
        row = db.session.get(Releases, item.release_id)
        if row and field in RELEASE_FIELDS:
            return getattr(row, field, None), True
    elif target == "submittal" and item.submittal_id:
        row = Submittals.query.filter_by(submittal_id=str(item.submittal_id)).first()
        if row and field in SUBMITTAL_FIELDS:
            return getattr(row, field, None), True
    return None, False


def reconcile(meeting):
    """Flag checklist items whose agreed Brain update never landed by meeting end.

    For each item carrying an expected_update and anchored to its release/submittal, compare
    the agreed new_value to the live Brain value; brain_update_pending=True when they differ
    (the update is still owed). Does NOT commit — the caller commits with its own writes.
    Returns the number of items flagged pending.
    """
    from app.models import ChecklistItem
    items = ChecklistItem.query.filter(
        ChecklistItem.meeting_id == meeting.id,
        ChecklistItem.expected_update.isnot(None),
    ).all()
    flagged = 0
    for item in items:
        eu = item.expected_update or {}
        current, anchored = _current_value(item)
        if not anchored:
            item.brain_update_pending = False
            continue
        pending = not _matches(current, eu.get("new_value"))
        item.brain_update_pending = pending
        if pending:
            flagged += 1
    logger.info("meeting_reconcile_done", meeting_id=meeting.id,
                checked=len(items), pending=flagged)
    return flagged
