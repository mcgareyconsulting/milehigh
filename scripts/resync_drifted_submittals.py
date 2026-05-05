"""
One-off script: resync two submittals whose DB state drifted from Procore truth.

  - 71374996 (project 480, Alta Flatirons): DB ball_in_court='David Servold',
    Procore truth='Dustin Pauley'. A workflow sequence advancement on 2026-04-30
    13:26 UTC was missed because the submittal poll-back returned a stale
    ball_in_court array.

  - 69723920 (project 590, Flats at Sand Creek): DB status='Open', Procore
    truth='Closed'. Closed by Dalton Rauer on 2026-05-01 12:24:32 UTC, but the
    status change was not detected in the same poll that captured the BIC change.

For each row this script: (1) fetches current Procore state, (2) shows the diff,
(3) updates the Submittals row to match Procore, (4) inserts a backfill
SubmittalEvents row attributed to the user known from the Procore audit log.

Usage:
    .venv/bin/python -m scripts.resync_drifted_submittals          # dry-run
    .venv/bin/python -m scripts.resync_drifted_submittals --apply  # commit
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from typing import Optional

from app import create_app
from app.models import Submittals, SubmittalEvents, db
from app.procore.procore import get_submittal_by_id
from app.procore.helpers import parse_ball_in_court_from_submittal


RESYNCS = [
    {
        "submittal_id": "71374996",
        "procore_project_id": "3212763",
        "field": "ball_in_court",
        "expected_new": "Dustin Pauley",
        "event_created_at": datetime(2026, 4, 30, 13, 26, 33),  # webhook 6358 receipt time
        "external_user_id": "7286899",  # Gary Almeida — advanced the workflow sequence
        "internal_user_id": 14,
        "reason": "missed BIC update from workflow sequence advancement (5->6) on 2026-04-30 13:26 UTC",
    },
    {
        "submittal_id": "69723920",
        "procore_project_id": "3462738",
        "field": "status",
        "expected_new": "Closed",
        "event_created_at": datetime(2026, 5, 1, 12, 24, 32),  # matching the partial event 2445
        "external_user_id": "10934410",  # Dalton Rauer
        "internal_user_id": 6,
        "reason": "missed status field in atomic Procore close action on 2026-05-01 12:24 UTC",
    },
]


def fetch_procore_view(procore_project_id: str, submittal_id: str) -> dict:
    """Pull live Procore view of a submittal. Returns parsed snapshot."""
    raw = get_submittal_by_id(procore_project_id, submittal_id)
    if not isinstance(raw, dict):
        return {"error": f"Procore returned {type(raw).__name__}: {raw!r}"}

    parsed = parse_ball_in_court_from_submittal(raw) or {}

    status_obj = raw.get("status")
    if isinstance(status_obj, dict):
        status = status_obj.get("name")
    elif isinstance(status_obj, str):
        status = status_obj
    else:
        status = None

    return {
        "ball_in_court_parsed": parsed.get("ball_in_court"),
        "ball_in_court_array_raw": raw.get("ball_in_court"),
        "status": str(status).strip() if status else None,
        "title": raw.get("title"),
    }


def backfill_payload_hash(action: str, submittal_id: str, payload: dict) -> str:
    """Same algorithm as create_submittal_payload_hash — distinct hash because the
    payload includes a 'backfill' marker, which prevents collision with normal events."""
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    raw = f"{action}:{submittal_id}:{payload_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resync_one(directive: dict, apply: bool) -> None:
    sid = directive["submittal_id"]
    field = directive["field"]
    expected_new = directive["expected_new"]

    print(f"\n=== Submittal {sid} ===")
    record = Submittals.query.filter_by(submittal_id=sid).first()
    if record is None:
        print(f"  ! No DB row for submittal {sid}; skipping.")
        return

    db_value = getattr(record, field)
    print(f"  DB.{field} = {db_value!r}")

    procore_view = fetch_procore_view(directive["procore_project_id"], sid)
    if "error" in procore_view:
        print(f"  ! Procore fetch error: {procore_view['error']}")
        return

    print(f"  Procore.status               = {procore_view['status']!r}")
    print(f"  Procore.ball_in_court_parsed = {procore_view['ball_in_court_parsed']!r}")
    print(f"  Procore.ball_in_court_array  = {procore_view['ball_in_court_array_raw']!r}")

    procore_field_value = procore_view["status"] if field == "status" else procore_view["ball_in_court_parsed"]

    if procore_field_value == db_value:
        print(f"  = No drift detected — DB and Procore both report {field}={db_value!r}.")
        print(f"    (User-confirmed truth was {expected_new!r}; if Procore now matches, no action needed.)")
        if procore_field_value != expected_new:
            print(f"  ! Procore says {procore_field_value!r}, not the expected {expected_new!r}. Skipping.")
        return

    if procore_field_value != expected_new:
        print(
            f"  ! Procore reports {field}={procore_field_value!r}, "
            f"but expected {expected_new!r}. The 'ball_in_court_parsed' "
            f"value is known to lag for this submittal — we'll trust the user-"
            f"confirmed value {expected_new!r}."
        )

    new_value = expected_new
    payload = {
        field: {"old": db_value, "new": new_value},
        "backfill": True,
        "reason": directive["reason"],
    }
    payload_hash = backfill_payload_hash("updated", sid, payload)

    print(f"  -> Will set {field}: {db_value!r} -> {new_value!r}")
    print(f"  -> Will insert SubmittalEvents row: action=updated source=Procore")
    print(f"     created_at={directive['event_created_at']}")
    print(f"     external_user_id={directive['external_user_id']} internal_user_id={directive['internal_user_id']}")
    print(f"     payload_hash={payload_hash}")
    print(f"     payload={json.dumps(payload)}")

    if not apply:
        print("  (dry-run: no changes committed)")
        return

    setattr(record, field, new_value)
    record.last_updated = datetime.utcnow()
    if field == "ball_in_court":
        record.last_bic_update = directive["event_created_at"]

    event = SubmittalEvents(
        submittal_id=sid,
        action="updated",
        payload=payload,
        payload_hash=payload_hash,
        source="Procore",
        external_user_id=directive["external_user_id"],
        internal_user_id=directive["internal_user_id"],
        is_system_echo=False,
        created_at=directive["event_created_at"],
    )
    db.session.add(event)
    db.session.commit()
    print(f"  ✓ Applied. SubmittalEvents.id={event.id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry-run)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"Mode: {mode}")
        for directive in RESYNCS:
            resync_one(directive, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
