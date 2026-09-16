"""
@milehigh-header
schema_version: 1
purpose: Flag-gated demo surface that prints ONE readable block per action showing the whole cascade — every DB field that moved, every audit event written, and every outbound Trello call that would have gone out — so a change can be walked through with the client before Trello is wired back up.
exports:
  init_cascade_trace: Wire the trace into a Flask app + SQLAlchemy session (called from create_app)
  note_outbound: Record an outbound integration call into the active trace
  enabled: Whether tracing is switched on
imports_from: [flask, sqlalchemy, app.config]
imported_by: [app/__init__.py, app/trello/api.py]
invariants:
  - Entirely OFF unless CASCADE_TRACE=1. Zero cost and zero output otherwise.
  - Never raises into the request. Every hook is wrapped; a broken trace must not break a write.
  - Read-only observer: it inspects the session, it never modifies an object or the flush plan.

WHY THIS PRINTS INSTEAD OF LOGGING (deliberate, and the one exception in the codebase):
docs/logging-standard.md bans print() on runtime paths, and it is right to — logs are JSON so
they can be queried. This is not a log. It is a presentation surface aimed at a person sitting
in front of a screen, and a JSON blob with \\n escapes in it cannot be read aloud to a client.
It is gated behind a flag that is off everywhere except a developer's laptop, it writes to
stdout only, and nothing else in the app depends on it. If it ever needs to be machine-readable,
render() returns the structured record and that is what should be logged.

WHAT IT CATCHES, AND WHY IT IS HOOKED AT THE SESSION
It listens to the SQLAlchemy session rather than to individual commands, so it reports what
ACTUALLY changed rather than what some command remembered to announce. A cascade nobody wired
up — a stage change that silently drops an ASAP flag three modules away — shows up here without
anyone adding a line for it. That is the point: the client is being shown consequences, and the
undeclared consequences are the interesting ones.
"""
import os
import sys
import threading
from datetime import date, datetime

_LOCAL = threading.local()

# Fields that move on literally every write. Real, but noise in a walkthrough — they are
# summarised on one line at the bottom instead of competing with the actual cascade.
_HOUSEKEEPING = {"last_updated_at", "source_of_update", "applied_at", "closed_at"}

_WIDTH = 78


def enabled() -> bool:
    """True when the trace is switched on. Read from the environment each call so it can be
    flipped without touching code, and so importing this module costs nothing."""
    return os.environ.get("CASCADE_TRACE", "0") == "1"


class _Trace:
    __slots__ = ("label", "changes", "created", "outbound", "housekeeping")

    def __init__(self, label):
        self.label = label
        self.changes = []      # (entity_label, field, old, new)
        self.created = []      # (kind, obj)
        self.outbound = []     # (op, fields, simulated)
        self.housekeeping = set()


def _current():
    return getattr(_LOCAL, "trace", None)


def _begin(label):
    _LOCAL.trace = _Trace(label)


def _end():
    t = _current()
    _LOCAL.trace = None
    return t


# ---------------------------------------------------------------------------
# value + label rendering
# ---------------------------------------------------------------------------

def _fmt(v):
    """One short, human-readable cell. Dates as ISO, blanks as an em dash, long text clipped."""
    if v is None:
        return "—"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v)
    if s == "":
        return "(blank)"
    s = s.replace("\n", "⏎ ")
    return s if len(s) <= 34 else s[:31] + "..."


def _entity_label(obj):
    """How a row is named in the block. A release is its job-release; anything else falls back
    to its class name so an unexpected table still reports rather than disappearing."""
    cls = type(obj).__name__
    try:
        if cls in ("Releases", "Job"):
            return f"{getattr(obj, 'job', '?')}-{getattr(obj, 'release', '?')}"
        if cls == "Submittals":
            return f"submittal {getattr(obj, 'submittal_id', '?')}"
    except Exception:
        pass
    return cls


def _headline(trace):
    """The release the action was about, with its name, if one was touched."""
    for entity, _f, _o, _n in trace.changes:
        if "-" in str(entity):
            return entity
    return None


# ---------------------------------------------------------------------------
# recording
# ---------------------------------------------------------------------------

def note_outbound(op, fields=None, simulated=True):
    """Record an outbound integration call. Called from the Trello mock guard, so the block can
    show what WOULD have been sent without anything leaving the machine."""
    if not enabled():
        return
    t = _current()
    if t is None:
        return
    try:
        t.outbound.append((op, dict(fields or {}), simulated))
    except Exception:
        pass


def _record_flush(session):
    """Diff the session before it flushes. History is only readable at this point — once the
    flush completes the old values are gone."""
    t = _current()
    if t is None:
        return
    from sqlalchemy import inspect as sa_inspect

    for obj in list(session.dirty):
        try:
            if not session.is_modified(obj, include_collections=False):
                continue
            state = sa_inspect(obj)
            label = _entity_label(obj)
            for attr in state.attrs:
                key = attr.key
                # Touching an unloaded column here would emit a SELECT mid-flush; skip it.
                if key in state.unloaded:
                    continue
                hist = attr.history
                if not hist.has_changes():
                    continue
                old = hist.deleted[0] if hist.deleted else None
                new = hist.added[0] if hist.added else None
                if old == new:
                    continue
                if key in _HOUSEKEEPING:
                    t.housekeeping.add(key)
                    continue
                t.changes.append((label, key, old, new))
        except Exception:
            continue

    for obj in list(session.new):
        try:
            t.created.append((type(obj).__name__, obj))
        except Exception:
            continue


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _line(text=""):
    return "║ " + text


def render(trace) -> str:
    """The block. Returns '' when the action changed nothing, so a plain GET prints nothing."""
    if not trace or (not trace.changes and not trace.created and not trace.outbound):
        return ""

    out = ["", "╔" + "═" * _WIDTH, _line(f"CASCADE   {trace.label}")]

    head = _headline(trace)
    if head:
        out.append(_line(f"release   {head}"))
    out.append("╟" + "─" * _WIDTH)

    # --- what moved in the database ---
    if trace.changes:
        out.append(_line("DATA CHANGED"))
        for entity, field, old, new in trace.changes:
            # Only name the row when it is not the release this action was about — otherwise
            # every line would repeat "560-923" and the eye has nothing to land on.
            prefix = "" if entity == head else f"[{entity}] "
            out.append(_line(f"   {prefix}{field:<26}{_fmt(old):<20} →  {_fmt(new)}"))
        out.append(_line())

    # --- the audit trail it wrote ---
    events = [o for k, o in trace.created if k in ("ReleaseEvents", "SubmittalEvents")]
    queued = [(k, o) for k, o in trace.created if k in ("TrelloOutbox", "ProcoreOutbox")]
    others = [
        (k, o) for k, o in trace.created
        if k not in ("ReleaseEvents", "SubmittalEvents", "TrelloOutbox", "ProcoreOutbox")
    ]
    if events:
        out.append(_line("AUDIT EVENTS WRITTEN   (these are what Undo reverses)"))
        for ev in events:
            try:
                action = getattr(ev, "action", "?")
                eid = getattr(ev, "id", None)
                payload = getattr(ev, "payload", None) or {}
                parent = payload.get("parent_event_id")
                tag = f"#{eid}" if eid else "(pending)"
                suffix = f"   ← caused by #{parent}" if parent else ""
                out.append(_line(f"   {action:<26}{tag}{suffix}"))
            except Exception:
                continue
        out.append(_line())
    if others:
        out.append(_line("ROWS CREATED"))
        for kind, obj in others:
            out.append(_line(f"   {kind:<26}{_entity_label(obj)}"))
        out.append(_line())

    # --- what would have gone out ---
    # Two ways a release reaches Trello: pushed inline during the request, or QUEUED on the
    # outbox for the retry worker to deliver. A queued row is still a real outbound update —
    # reporting only the inline half would tell the client "nothing goes to Trello" on a stage
    # change that very much does.
    if trace.outbound or queued:
        simulated = all(s for _o, _f, s in trace.outbound) if trace.outbound else True
        banner = "(mocked — nothing left this machine)" if simulated else "(SENT FOR REAL)"
        out.append(_line(f"GOES TO TRELLO   {banner}"))
        for op, fields, sim in trace.outbound:
            # Drop the kwargs that are None — a push that sets a due date and nothing else
            # should read as "due=2026-09-26", not trail a column of em dashes.
            bits = "  ".join(f"{k}={_fmt(v)}" for k, v in fields.items() if v is not None)
            mark = "" if sim else "   ** REAL **"
            out.append(_line(f"   now      {op:<20}{bits}{mark}"))
        for _kind, row in queued:
            try:
                action = getattr(row, "action", "?")
                dest = getattr(row, "destination", "trello")
                out.append(_line(f"   queued   {action:<20}via {dest} outbox, delivered by the retry worker"))
            except Exception:
                continue
        out.append(_line())
    else:
        out.append(_line("GOES TO TRELLO   nothing — this change stays in the Brain"))
        out.append(_line())

    if trace.housekeeping:
        out.append(_line(f"also touched: {', '.join(sorted(trace.housekeeping))}"))

    out.append("╚" + "═" * _WIDTH)
    out.append("")
    return "\n".join(out)


def _emit(trace):
    block = render(trace)
    if block:
        sys.stdout.write(block + "\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# wiring
# ---------------------------------------------------------------------------

def init_cascade_trace(app, db):
    """Attach the trace to a Flask app and its SQLAlchemy session. No-op unless CASCADE_TRACE=1.

    Called once from create_app(), after db.init_app().
    """
    if not enabled():
        return

    from flask import request
    from sqlalchemy import event

    @app.before_request
    def _cascade_begin():
        try:
            # Only mutating requests can cascade; a GET would print an empty block.
            if request.method in ("GET", "HEAD", "OPTIONS"):
                _LOCAL.trace = None
                return
            _begin(f"{request.method} {request.path}")
        except Exception:
            pass

    @app.after_request
    def _cascade_emit(response):
        try:
            _emit(_end())
        except Exception:
            pass
        return response

    @app.teardown_request
    def _cascade_clear(exc):
        # A request that died mid-flight must not leak its trace into the next one.
        try:
            _LOCAL.trace = None
        except Exception:
            pass

    @event.listens_for(db.session, "before_flush")
    def _cascade_before_flush(session, flush_context, instances):
        try:
            _record_flush(session)
        except Exception:
            pass

    sys.stdout.write(
        "\nCASCADE_TRACE is ON — every write prints a cascade block. "
        "Unset CASCADE_TRACE to silence it.\n\n"
    )
    sys.stdout.flush()
