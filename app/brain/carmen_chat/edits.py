"""Spoken release edits — propose, confirm, then write. Admin-only.

Carmen is read-only everywhere else, and this module is the one deliberate exception. It
exists because voice mishears numbers: "150-893" and "150-894" are nearly the same sound,
and a wrong stage change cascades into `job_comp`, fab_order and the Trello outbox before
anyone would notice. So nothing here writes on the strength of a transcript alone.

The shape is two steps:

    propose_release_changes(...)  -> resolve, validate, compute from->to, SIGN. No writes.
    POST .../live/apply           -> verify signature, execute through the real commands.

**The plan is signed, not stored.** `_sign()` HMACs the canonical plan with the app's
SECRET_KEY, the acting user's id and an issue timestamp. That means no table, no migration
and no multi-worker state to get wrong — and an expired or edited plan simply fails to
verify. A plan is good for `_TTL_SECONDS` and only for the user it was issued to.

Execution goes through the existing job-log commands (`UpdateStageCommand`, etc.), so a
spoken edit is indistinguishable from one typed into the Job Log: same validation, same
`ReleaseEvents` row, same Trello outbox entry, same undo. The apply response carries every
event id back so the UI can offer an Undo straight away.

Two kinds of plan travel through here — release field changes and new to-dos — and both
take the identical route: validated, signed, shown, confirmed, written. `plan["kind"]`
says which. A plan with no kind is a release change (the original shape).

Known gap: release notes are a plain text column, so "@Bill" lands as text and notifies
nobody. Mentions notify on *board* comments, not release notes.
"""
import hashlib
import hmac
import json
import time
from datetime import date, datetime

from app.api.helpers import DYNAMIC_STAGE_ORDER, FIXED_TIER_STAGES
from app.config import Config as cfg
from app.logging_config import get_logger
from app.models import ChecklistItem, Releases, User, db

from .tools import _parse_identifier

logger = get_logger(__name__)

_TTL_SECONDS = 300  # a proposal the user walked away from must not still be live

FIELD_STAGE = "stage"
FIELD_NOTES = "notes"
FIELD_SHIP_DATE = "ship_date"
FIELD_START_INSTALL = "start_install"
EDITABLE_FIELDS = (FIELD_STAGE, FIELD_NOTES, FIELD_SHIP_DATE, FIELD_START_INSTALL)

# Every stage a release may legally sit in, drawn from the same tables the Job Log uses
# so this can't drift out of sync with them.
VALID_STAGES = sorted(
    {s for group in FIXED_TIER_STAGES.values() for s in group}
    | set(DYNAMIC_STAGE_ORDER)
    | {"Complete", "Hold"}
)
_STAGE_BY_LOWER = {s.lower(): s for s in VALID_STAGES}


KIND_RELEASE = "release_changes"
KIND_TODO = "todo"


class EditError(ValueError):
    """A proposal could not be built or verified. Message is safe to speak aloud."""


# --- the tool Carmen calls ------------------------------------------------------------

TOOL_PROPOSE_CHANGES = "propose_release_changes"

PROPOSE_TOOL_DEF = {
    "type": "function",
    "name": TOOL_PROPOSE_CHANGES,
    "description": (
        "Propose one or more changes to a release and show them to the person for "
        "confirmation. NOTHING IS SAVED until they confirm on screen — this is how you "
        "make edits, and it is safe to call. Use it whenever the person asks you to "
        "change, move, set, update or add something to a release. Put ALL the changes "
        "they asked for in a single call so they confirm once. Calling it again replaces "
        "the card that is already up, so correct a mistake by re-proposing the WHOLE set "
        "of changes, not just the part that was wrong. Never claim a change is done until "
        "you are told it was applied."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "identifier": {
                "type": "string",
                "description": "The job-release, e.g. '150-893'.",
            },
            "changes": {
                "type": "array",
                "description": "Every change to apply to that release.",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": list(EDITABLE_FIELDS),
                            "description": "Which field to change.",
                        },
                        "value": {
                            "type": "string",
                            "description": (
                                "New value. For stage, one of the exact stage names — note "
                                "that 'Install Start' and 'Install Complete' are STAGES, not "
                                "dates. For ship_date / start_install, an ISO date "
                                "(YYYY-MM-DD); resolve relative dates like 'next Friday' "
                                "yourself. For notes, THE PERSON'S OWN WORDS, verbatim — "
                                "if they said 'hey let's get Saul on this', the note is "
                                "\"hey let's get Saul on this\". Never paraphrase, summarise, "
                                "re-word, or add detail they did not say."
                            ),
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["replace", "append"],
                            "description": "Notes only. 'replace' overwrites the note cell with the new text (DEFAULT — the release's activity feed keeps the old note, so nothing is lost). 'append' keeps the existing text and adds a line below it; only use it if they explicitly say to add to or keep the current note.",
                        },
                    },
                    "required": ["field", "value"],
                },
            },
        },
        "required": ["identifier", "changes"],
    },
}


TOOL_PROPOSE_TODO = "propose_todo"

PROPOSE_TODO_TOOL_DEF = {
    "type": "function",
    "name": TOOL_PROPOSE_TODO,
    "description": (
        "Propose a new to-do for someone and show it for confirmation. NOTHING IS SAVED "
        "until they confirm on screen, so this is safe to call. Use it whenever the person "
        "asks you to leave, add, create or assign a to-do, a task, a reminder or a "
        "follow-up for someone. The to-do lands in that person's To-Dos list."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": (
                    "What needs doing, in the person's own words and phrased as an action — "
                    "\"follow up with Drexel Supply on the decking order\". Do not add "
                    "detail they did not say."
                ),
            },
            "owner": {
                "type": "string",
                "description": "Who it is for: a first name, full name, or email. Must match a real person in the app.",
            },
            "due_date": {
                "type": "string",
                "description": "Optional ISO date (YYYY-MM-DD). Resolve 'Friday' or 'next week' to a real date yourself. Omit if no date was mentioned.",
            },
            "release": {
                "type": "string",
                "description": "Optional job-release this is about, e.g. '170-181', so the to-do links to that release.",
            },
            "detail": {
                "type": "string",
                "description": "Optional extra context, only if the person actually gave some.",
            },
        },
        "required": ["title", "owner"],
    },
}


# --- signing ---------------------------------------------------------------------------

def _canonical(plan: dict) -> str:
    return json.dumps(plan, sort_keys=True, separators=(",", ":"), default=str)


def _sign(plan: dict, user_id: int, issued_at: int) -> str:
    secret = (cfg.SECRET_KEY or "").encode() or b"carmen-unsigned"
    msg = f"{_canonical(plan)}|{user_id}|{issued_at}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify(plan: dict, token: str, issued_at, user_id: int) -> None:
    """Raise EditError unless this exact plan was issued to this user and is still fresh."""
    try:
        issued = int(issued_at)
    except (TypeError, ValueError):
        raise EditError("That change request is malformed.")
    if not token or not hmac.compare_digest(token, _sign(plan, user_id, issued)):
        logger.warning("carmen_edit_signature_mismatch", user_id=user_id)
        raise EditError("That change request couldn't be verified. Ask Carmen again.")
    if time.time() - issued > _TTL_SECONDS:
        raise EditError("That change request expired. Ask Carmen again.")


# --- proposing ---------------------------------------------------------------------------

def _parse_date(value: str, label: str):
    text = (value or "").strip()
    if not text or text.lower() in {"none", "null", "clear", "blank"}:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        raise EditError(f"I couldn't read '{value}' as a date for {label}. Use YYYY-MM-DD.")


def _fmt(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _resolve_stage(value: str) -> str:
    stage = _STAGE_BY_LOWER.get((value or "").strip().lower())
    if stage:
        return stage
    raise EditError(
        f"'{value}' isn't a stage I recognise. Valid stages are: {', '.join(VALID_STAGES)}."
    )


def _build_change(release: Releases, raw: dict) -> dict:
    field = (raw.get("field") or "").strip().lower()
    value = raw.get("value")
    if field not in EDITABLE_FIELDS:
        raise EditError(
            f"I can't change '{raw.get('field')}'. I can set stage, notes, ship date and install date."
        )

    if field == FIELD_STAGE:
        new = _resolve_stage(value)
        old = release.stage or "Released"
        if new == old:
            raise EditError(f"{release.job}-{release.release} is already in {new}.")
        return {"field": field, "from": old, "to": new,
                "label": "Stage", "from_display": old, "to_display": new}

    if field == FIELD_NOTES:
        # Replace by default: the note cell reads as one current note, and the release's
        # activity feed already carries every previous one, so overwriting loses nothing.
        mode = (raw.get("mode") or "replace").strip().lower()
        if mode not in ("append", "replace"):
            mode = "replace"
        addition = (value or "").strip()
        if not addition:
            raise EditError("There was no note text to add.")
        old = release.notes or ""
        new = f"{old.rstrip()}\n{addition}".strip() if (mode == "append" and old.strip()) else addition
        if new.strip() == old.strip():
            raise EditError("That note is already on the release.")
        return {"field": field, "from": old, "to": new, "mode": mode,
                "label": "Note (added)" if mode == "append" else "Note",
                # On an append nothing is replaced, so an arrow pointing at the old note
                # would misdescribe it. On a replace the old note is exactly what you want
                # to see before confirming.
                "from_display": "—" if mode == "append" else _fmt(old or None),
                "to_display": addition if mode == "append" else new}

    label, current = (
        ("Ship date", release.ship_date) if field == FIELD_SHIP_DATE
        else ("Install date", release.start_install)
    )
    new_date = _parse_date(value, label.lower())
    if new_date == current:
        raise EditError(
            f"The {label.lower()} on {release.job}-{release.release} is already "
            f"{_fmt(current)} — did you mean the stage instead?"
        )
    return {"field": field,
            "from": current.isoformat() if current else None,
            "to": new_date.isoformat() if new_date else None,
            "label": label, "from_display": _fmt(current), "to_display": _fmt(new_date)}


def propose(identifier: str, changes: list, *, user_id: int) -> dict:
    """Resolve and validate a change set, and sign it. Writes nothing.

    Returns a payload the UI renders as a confirmation card — and which the apply
    endpoint will only accept back unmodified.
    """
    job, release_no = _parse_identifier(identifier)
    if job is None or not release_no:
        raise EditError(
            f"I couldn't work out which release '{identifier}' is. Give me a job and release, like 150-893."
        )
    row = Releases.resolve(job, release_no)
    if row is None:
        raise EditError(f"I can't find release {job}-{release_no}.")
    if not isinstance(changes, list) or not changes:
        raise EditError("There were no changes to make.")

    seen, built = set(), []
    for raw in changes:
        if not isinstance(raw, dict):
            raise EditError("One of those changes wasn't in a form I could read.")
        change = _build_change(row, raw)
        if change["field"] in seen:
            raise EditError(f"You gave me two different values for {change['label'].lower()}.")
        seen.add(change["field"])
        built.append(change)

    plan = {
        "kind": KIND_RELEASE,
        "headline": f"Change {job}-{release_no}"
                    + (f" — {len(built)} changes" if len(built) > 1 else ""),
        "job": job,
        "release": release_no,
        "job_name": row.job_name,
        "scope": getattr(row, "scope", None),
        "changes": built,
    }
    issued_at = int(time.time())
    logger.info("carmen_edit_proposed", user_id=user_id, job=job, release=release_no,
                fields=[c["field"] for c in built])
    return {
        "proposed": True,
        "applied": False,
        "plan": plan,
        "token": _sign(plan, user_id, issued_at),
        "issued_at": issued_at,
        "expires_in_seconds": _TTL_SECONDS,
        "message": (
            f"Proposed {len(built)} change{'s' if len(built) != 1 else ''} to "
            f"{job}-{release_no}. NOT SAVED YET — waiting for them to confirm on screen."
        ),
    }


def _resolve_owner(name: str) -> User:
    """Match a spoken name to a real person, or say who it could have been.

    A to-do assigned to the wrong person is worse than one that failed to save, so an
    ambiguous name is refused with the candidates rather than guessed at.
    """
    text = (name or "").strip()
    if not text:
        raise EditError("Who is that to-do for?")
    needle = text.lower()

    rows = User.query.filter(User.is_active.is_(True)).all() if hasattr(User, "is_active") \
        else User.query.all()

    def full(u):
        return f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip()

    exact = [u for u in rows
             if full(u).lower() == needle
             or (u.username or "").lower() == needle
             or (u.first_name or "").strip().lower() == needle]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise EditError(
            f"There's more than one {text}: " + ", ".join(sorted(full(u) or u.username for u in exact))
            + ". Which one?"
        )

    partial = [u for u in rows if needle in full(u).lower() or needle in (u.username or "").lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise EditError(
            f"I found a few people matching '{text}': "
            + ", ".join(sorted(full(u) or u.username for u in partial)) + ". Which one?"
        )
    raise EditError(f"I can't find anyone called '{text}' in the app.")


def propose_todo(title: str, owner: str, *, due_date=None, release=None, detail=None,
                 user_id: int) -> dict:
    """Resolve and validate a new to-do, and sign it. Writes nothing."""
    title = (title or "").strip()
    if not title:
        raise EditError("What should the to-do say?")

    person = _resolve_owner(owner)
    owner_name = f"{(person.first_name or '').strip()} {(person.last_name or '').strip()}".strip() \
        or person.username
    due = _parse_date(due_date, "the due date") if due_date else None

    release_id = job = release_no = job_name = None
    if release:
        job, release_no = _parse_identifier(release)
        row = Releases.resolve(job, release_no) if (job and release_no) else None
        if row is None:
            raise EditError(f"I can't find release {release} to attach that to-do to.")
        release_id, job_name = row.id, row.job_name

    changes = [
        {"field": "title", "label": "To-do", "from_display": "—", "to_display": title},
        {"field": "owner", "label": "For", "from_display": "—", "to_display": owner_name},
    ]
    if due:
        changes.append({"field": "due_date", "label": "Due",
                        "from_display": "—", "to_display": _fmt(due)})
    if release_id:
        changes.append({"field": "release", "label": "Release", "from_display": "—",
                        "to_display": f"{job}-{release_no}"})
    if (detail or "").strip():
        changes.append({"field": "detail", "label": "Detail", "from_display": "—",
                        "to_display": detail.strip()})

    plan = {
        "kind": KIND_TODO,
        "headline": f"New to-do for {owner_name}",
        "title": title,
        "detail": (detail or "").strip() or None,
        "owner_user_id": person.id,
        "owner_name": owner_name,
        "due_date": due.isoformat() if due else None,
        "release_id": release_id,
        "job": job,
        "release": release_no,
        "job_name": job_name,
        "changes": changes,
    }
    issued_at = int(time.time())
    logger.info("carmen_todo_proposed", user_id=user_id, owner_user_id=person.id,
                release_id=release_id, has_due_date=bool(due))
    return {
        "proposed": True,
        "applied": False,
        "plan": plan,
        "token": _sign(plan, user_id, issued_at),
        "issued_at": issued_at,
        "expires_in_seconds": _TTL_SECONDS,
        "message": (
            f"Proposed a to-do for {owner_name}. NOT SAVED YET — waiting for them to "
            f"confirm on screen."
        ),
    }


# --- applying ---------------------------------------------------------------------------

def apply(plan: dict, *, user_id: int) -> dict:
    """Execute a verified plan. Call verify() first — this trusts what it is given."""
    if plan.get("kind") == KIND_TODO:
        return _apply_todo(plan, user_id=user_id)
    return _apply_release_changes(plan, user_id=user_id)


def _apply_todo(plan: dict, *, user_id: int) -> dict:
    """Create the to-do. It lands as an accepted, owned checklist item — the same shape
    the meeting extractor produces on accept, so the To-Dos page treats it identically."""
    try:
        item = ChecklistItem(
            meeting_id=None,            # raised directly, not mined from a transcript
            title=plan["title"],
            detail=plan.get("detail"),
            item_type="action",
            status="accepted",          # skips the propose/curate step: a human just did it
            owner_user_id=plan["owner_user_id"],
            due_date=_parse_date(plan["due_date"], "the due date") if plan.get("due_date") else None,
            release_id=plan.get("release_id"),
        )
        db.session.add(item)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("carmen_todo_apply_failed", user_id=user_id,
                     owner_user_id=plan.get("owner_user_id"), error=str(exc),
                     error_type=type(exc).__name__, exc_info=True)
        return {"applied": 0, "failed": 1, "event_ids": [],
                "results": [{"field": "todo", "label": "To-do", "status": "failed",
                             "error": "that to-do could not be saved"}]}

    logger.info("carmen_todo_created", user_id=user_id, todo_id=item.id,
                owner_user_id=item.owner_user_id, release_id=item.release_id,
                due_date=item.due_date.isoformat() if item.due_date else None)
    return {
        "applied": 1,
        "failed": 0,
        "todo_id": item.id,
        # No ReleaseEvents row behind a to-do, so there is nothing for the undo endpoint
        # to reverse — the To-Dos page is where it gets closed or removed.
        "event_ids": [],
        "results": [{"field": "todo", "label": f"To-do for {plan['owner_name']}",
                     "status": "applied", "event_id": None,
                     "detail": {"todo_id": item.id}}],
        "job": plan.get("job"),
        "release": plan.get("release"),
    }


def _apply_release_changes(plan: dict, *, user_id: int) -> dict:
    """Execute release field changes through the real job-log commands."""
    from app.brain.job_log.features.notes.command import UpdateNotesCommand
    from app.brain.job_log.features.ship_date.command import UpdateShipDateCommand
    from app.brain.job_log.features.stage.command import UpdateStageCommand
    from app.brain.job_log.features.start_install.command import UpdateStartInstallCommand

    job = plan["job"]
    release_no = plan["release"]
    results, failures = [], []

    for change in plan.get("changes", []):
        field = change["field"]
        try:
            if field == FIELD_STAGE:
                out = UpdateStageCommand(job_id=job, release=release_no, stage=change["to"],
                                         source="Carmen", source_of_update="Carmen").execute()
            elif field == FIELD_NOTES:
                out = UpdateNotesCommand(job_id=job, release=release_no, notes=change["to"],
                                         source="Carmen", source_of_update="Carmen").execute()
            elif field == FIELD_SHIP_DATE:
                out = UpdateShipDateCommand(
                    job_id=job, release=release_no,
                    ship_date=_parse_date(change["to"], "ship date") if change["to"] else None,
                    source="Carmen", source_of_update="Carmen").execute()
            else:
                out = UpdateStartInstallCommand(
                    job_id=job, release=release_no,
                    start_install=_parse_date(change["to"], "install date") if change["to"] else None,
                    source="Carmen", source_of_update="Carmen").execute()
            payload = out.to_dict() if hasattr(out, "to_dict") else {}
            results.append({"field": field, "label": change["label"], "status": "applied",
                            "event_id": payload.get("event_id"), "detail": payload})
        except Exception as exc:
            # Keep going: a failed note must not silently drop an applied stage move.
            logger.error("carmen_edit_apply_failed", user_id=user_id, job=job,
                         release=release_no, field=field, error=str(exc),
                         error_type=type(exc).__name__, exc_info=True)
            failures.append({"field": field, "label": change["label"], "status": "failed",
                             "error": str(exc)})

    logger.info("carmen_edit_applied", user_id=user_id, job=job, release=release_no,
                applied=len(results), failed=len(failures),
                event_ids=[r.get("event_id") for r in results])
    return {
        "applied": len(results),
        "failed": len(failures),
        "results": results + failures,
        "event_ids": [r["event_id"] for r in results if r.get("event_id")],
        "job": job,
        "release": release_no,
    }
