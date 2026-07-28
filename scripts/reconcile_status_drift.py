"""
Reconcile Open-in-DB / Closed-in-Procore (and other status) drift.

What this does
--------------
1. Scan every submittal with DB status='Open' against live Procore.
2. When Procore status != DB status:
   - set DB status to Procore truth
   - if new status is not Open: clear order_number (frees the DWL slot —
     same rule as check_and_update_submittal)
   - optionally sync ball_in_court when it also drifted
   - write a SubmittalEvents row marked backfill=True for the audit trail
3. For every drafter whose Open queue lost an ordered/urgent slot, compress:
   - urgency (0.1–0.9): pack into the high end of the ladder (compress_orders)
   - regular (>=1): renumber 1..N preserving relative order (compress_ordered /
     same math as DWL "Resort")

"Clear orders + compress Gary's queue" means:
  Zombies were still holding slots like Gary order 0.9 and 5.0. Closing them
  sets order_number=NULL. Compress then renumbers the *remaining Open* items
  so Gary's queue is contiguous again, e.g. urgency 0.5–0.8 → 0.6–0.9 and
  regular 1, 8, 9 → 1, 2, 3.

Usage
-----
    ENVIRONMENT=production python -m scripts.reconcile_status_drift
    ENVIRONMENT=production python -m scripts.reconcile_status_drift --apply
    ENVIRONMENT=production python -m scripts.reconcile_status_drift --apply --report /tmp/status_reconcile.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# Never boot the prod scheduler from a one-off script.
os.environ.pop("IS_RENDER_SCHEDULER", None)
os.environ.pop("WERKZEUG_RUN_MAIN", None)
os.environ.setdefault("ENVIRONMENT", "production")

from app import create_app
from app.models import Submittals, SubmittalEvents, db
from app.procore.procore import get_submittal_by_id
from app.procore.helpers import parse_ball_in_court_from_submittal
from app.brain.drafting_work_load.engine import SubmittalOrderingEngine
from app.logging_config import get_logger

logger = get_logger(__name__)


def _status_name(raw: Any) -> Optional[str]:
    if isinstance(raw, dict):
        return (raw.get("name") or raw.get("status") or raw.get("value") or None)
    if isinstance(raw, str):
        return raw.strip() or None
    return None


def _norm(value: Optional[str]) -> str:
    return value if value is not None else ""


def _backfill_hash(action: str, submittal_id: str, payload: dict) -> str:
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    raw = f"{action}:{submittal_id}:{payload_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_procore(project_id: str, submittal_id: str) -> dict:
    raw = get_submittal_by_id(project_id, submittal_id)
    if not isinstance(raw, dict):
        return {"error": f"Procore returned {type(raw).__name__}: {raw!r}"}

    parsed = parse_ball_in_court_from_submittal(raw) or {}
    status = _status_name(raw.get("status"))
    return {
        "status": str(status).strip() if status else None,
        "ball_in_court": parsed.get("ball_in_court"),
        "title": raw.get("title"),
        "closed_at": raw.get("closed_at"),
        "current_revision": raw.get("current_revision"),
    }


def scan_open_for_drift(
    sleep_s: float = 0.05,
    only_ids: Optional[Set[str]] = None,
) -> List[dict]:
    """Return drift rows for every Open DB submittal that disagrees with Procore.

    only_ids restricts the scan to specific submittal_ids (surgical reconcile).
    """
    query = Submittals.query.filter(Submittals.status == "Open")
    if only_ids:
        query = query.filter(Submittals.submittal_id.in_(sorted(only_ids)))
    opens = query.order_by(Submittals.project_number, Submittals.id).all()

    if only_ids:
        found = {rec.submittal_id for rec in opens}
        for missing in sorted(only_ids - found):
            print(f"  NOTE: {missing} is not an Open row in the DB — nothing to reconcile")
    drifts: List[dict] = []
    errors: List[dict] = []
    in_sync = 0

    print(f"Scanning {len(opens)} Open submittals against Procore…")
    for i, rec in enumerate(opens, 1):
        if not rec.procore_project_id:
            errors.append({
                "submittal_id": rec.submittal_id,
                "error": "missing procore_project_id",
            })
            continue
        try:
            view = fetch_procore(rec.procore_project_id, rec.submittal_id)
        except Exception as e:
            errors.append({
                "submittal_id": rec.submittal_id,
                "project_number": rec.project_number,
                "error": f"{type(e).__name__}: {e}",
            })
            if sleep_s:
                time.sleep(sleep_s)
            continue

        if "error" in view:
            errors.append({
                "submittal_id": rec.submittal_id,
                "project_number": rec.project_number,
                "error": view["error"],
            })
            if sleep_s:
                time.sleep(sleep_s)
            continue

        status_drift = _norm(rec.status) != _norm(view["status"])
        bic_drift = _norm(rec.ball_in_court) != _norm(view["ball_in_court"])

        if not status_drift and not bic_drift:
            in_sync += 1
        else:
            drifts.append({
                "submittal_id": rec.submittal_id,
                "procore_project_id": rec.procore_project_id,
                "project_number": rec.project_number,
                "title": rec.title,
                "db_status": rec.status,
                "procore_status": view["status"],
                "db_bic": rec.ball_in_court,
                "procore_bic": view["ball_in_court"],
                "db_order": rec.order_number,
                "status_drift": status_drift,
                "bic_drift": bic_drift,
                "closed_at": view.get("closed_at"),
                "current_revision": view.get("current_revision"),
            })

        if i % 50 == 0 or i == len(opens):
            print(f"  … {i}/{len(opens)}  drifts={len(drifts)}  in_sync={in_sync}  errors={len(errors)}")
        if sleep_s:
            time.sleep(sleep_s)

    return drifts, errors, in_sync


def apply_status_drifts(drifts: List[dict], apply: bool) -> Tuple[List[dict], Set[str]]:
    """
    Apply status (and accompanying BIC) fixes for status-drifted rows.
    Returns (applied_rows, drafter_bics_to_compress).
    """
    applied: List[dict] = []
    compress_bics: Set[str] = set()

    status_drifts = [d for d in drifts if d["status_drift"]]
    print(f"\nStatus drifts to reconcile: {len(status_drifts)}")

    for d in status_drifts:
        rec = Submittals.query.filter_by(submittal_id=d["submittal_id"]).first()
        if rec is None:
            d["action"] = "missing_row"
            applied.append(d)
            continue

        old_status = rec.status
        old_order = rec.order_number
        old_bic = rec.ball_in_court
        new_status = d["procore_status"]
        new_bic = d["procore_bic"]

        # Any single-drafter queue that owned this Open row may need compress after
        # the row leaves Open (even if its order was already null — siblings may have gaps).
        if old_bic and "," not in old_bic:
            compress_bics.add(old_bic)

        payload: Dict[str, Any] = {
            "status": {"old": old_status, "new": new_status},
            "backfill": True,
            "reason": "reconcile_status_drift: Procore is source of truth",
        }
        will_clear_order = _norm(new_status) != "Open" and old_order is not None
        if will_clear_order:
            payload["order_number"] = {"old": old_order, "new": None}

        # Sync BIC only when status is also drifting on this pass (keep surgical).
        will_sync_bic = d["bic_drift"]
        if will_sync_bic:
            payload["ball_in_court"] = {"old": old_bic, "new": new_bic}

        action_row = {
            **d,
            "old_order": old_order,
            "will_clear_order": will_clear_order,
            "will_sync_bic": will_sync_bic,
            "action": "would_update" if not apply else "updated",
        }

        print(
            f"  {'APPLY' if apply else 'would'}  {d['submittal_id']}  "
            f"job={d['project_number']}  {(d['title'] or '')[:40]!r}"
        )
        print(f"         status  {old_status!r} -> {new_status!r}")
        if will_clear_order:
            print(f"         order   {old_order!r} -> None  (free slot)")
        if will_sync_bic:
            print(f"         BIC     {old_bic!r} -> {new_bic!r}")

        if apply:
            rec.status = new_status
            if will_clear_order:
                rec.order_number = None
            if will_sync_bic:
                rec.ball_in_court = new_bic
                rec.last_bic_update = datetime.utcnow()
            rec.last_updated = datetime.utcnow()

            event = SubmittalEvents(
                submittal_id=rec.submittal_id,
                action="updated",
                payload=payload,
                payload_hash=_backfill_hash("updated", rec.submittal_id, payload),
                source="Brain",
                is_system_echo=False,
                created_at=datetime.utcnow(),
            )
            db.session.add(event)
            action_row["event_payload"] = payload

        applied.append(action_row)

    if apply and applied:
        db.session.commit()
        print(f"  committed {sum(1 for a in applied if a.get('action') == 'updated')} status updates")

    return applied, compress_bics


def compress_drafter_queue(
    ball_in_court: str,
    apply: bool,
    exclude_ids: Optional[Set[str]] = None,
) -> List[dict]:
    """
    Compress Open submittals for one single-assignee drafter:
      urgency slots + regular 1..N (same as DWL Resort for regular).

    exclude_ids: submittals that are about to leave Open (dry-run) or were just
    closed — never include them in the compress set.
    """
    exclude_ids = exclude_ids or set()
    rows = (
        Submittals.query.filter(
            Submittals.ball_in_court == ball_in_court,
            Submittals.status == "Open",
        ).all()
    )
    rows = [s for s in rows if s.submittal_id not in exclude_ids]
    data = [{"submittal_id": s.submittal_id, "order_number": s.order_number} for s in rows]
    urgent_updates = SubmittalOrderingEngine.compress_orders(data)
    # Re-read dicts after urgent so regular math sees current numbers (engine is pure;
    # apply both against original data is fine — zones don't overlap).
    regular_updates = SubmittalOrderingEngine.compress_ordered_submittals(data)

    by_id = {s.submittal_id: s for s in rows}
    result = []
    for sid, new_order in urgent_updates + regular_updates:
        rec = by_id.get(sid)
        if rec is None:
            continue
        old = rec.order_number
        result.append({
            "submittal_id": sid,
            "ball_in_court": ball_in_court,
            "old_order": old,
            "new_order": new_order,
        })
        print(
            f"  {'APPLY' if apply else 'would'} compress  {sid}  "
            f"{ball_in_court}: {old!r} -> {new_order!r}"
        )
        if apply:
            rec.order_number = new_order
            rec.last_updated = datetime.utcnow()
            payload = {
                "resort": True,
                "order_number": {"old": old, "new": new_order},
                "backfill": True,
                "reason": "reconcile_status_drift: compress after zombie close",
            }
            db.session.add(SubmittalEvents(
                submittal_id=sid,
                action="updated",
                payload=payload,
                payload_hash=_backfill_hash("updated", sid, payload),
                source="Brain",
                is_system_echo=False,
                created_at=datetime.utcnow(),
            ))

    if apply and result:
        db.session.commit()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry-run)")
    parser.add_argument(
        "--also-bic-only",
        action="store_true",
        help="Also report Open rows with BIC drift but matching Open status (not applied)",
    )
    parser.add_argument("--report", metavar="PATH", help="Write JSON report")
    parser.add_argument("--sleep", type=float, default=0.05, help="Seconds between Procore GETs")
    parser.add_argument(
        "--only",
        metavar="IDS",
        help="Comma-separated submittal_ids: scan and reconcile ONLY these rows",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Close/clear only — never renumber a drafter's remaining Open queue",
    )
    args = parser.parse_args()
    only_ids = {s.strip() for s in args.only.split(",") if s.strip()} if args.only else None

    app = create_app()
    with app.app_context():
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"Mode: {mode}")
        print(f"DB: {app.config.get('SQLALCHEMY_DATABASE_URI', '').split('@')[-1]}")

        if only_ids:
            print(f"Scope: ONLY {', '.join(sorted(only_ids))}")
        if args.no_compress:
            print("Compress: DISABLED (--no-compress)")

        drifts, errors, in_sync = scan_open_for_drift(sleep_s=args.sleep, only_ids=only_ids)

        status_drifts = [d for d in drifts if d["status_drift"]]
        bic_only = [d for d in drifts if d["bic_drift"] and not d["status_drift"]]

        print("\n=== STATUS DRIFT (Open in DB, different in Procore) ===")
        for d in status_drifts:
            print(
                f"  job={d['project_number']:>4}  ord={str(d['db_order']):>6}  "
                f"{d['submittal_id']}  {(d['title'] or '')[:40]}"
            )
            print(
                f"         status {d['db_status']!r} -> {d['procore_status']!r}  "
                f"BIC {d['db_bic']!r} -> {d['procore_bic']!r}  "
                f"closed_at={d.get('closed_at')}"
            )

        if args.also_bic_only and bic_only:
            print(f"\n=== BIC-ONLY DRIFT (status still Open both sides): {len(bic_only)} ===")
            for d in bic_only[:40]:
                print(
                    f"  job={d['project_number']:>4}  {d['submittal_id']}  "
                    f"BIC {d['db_bic']!r} -> {d['procore_bic']!r}  {(d['title'] or '')[:35]}"
                )
            if len(bic_only) > 40:
                print(f"  … +{len(bic_only) - 40} more")

        if errors:
            print(f"\n=== FETCH ERRORS ({len(errors)}) ===")
            for e in errors[:20]:
                print(f"  {e}")

        print(
            f"\nSummary: in_sync={in_sync}  status_drift={len(status_drifts)}  "
            f"bic_only={len(bic_only)}  errors={len(errors)}"
        )

        applied, compress_bics = apply_status_drifts(status_drifts, apply=args.apply)

        # IDs leaving Open must not be renumbered (dry-run still sees them as Open).
        leaving_open_ids = {
            d["submittal_id"]
            for d in status_drifts
            if _norm(d.get("procore_status")) != "Open"
        }

        compress_results = []
        if args.no_compress:
            if compress_bics:
                print(
                    f"\n(compress skipped by --no-compress; would have touched: "
                    f"{', '.join(sorted(compress_bics))})"
                )
        else:
            for bic in sorted(compress_bics):
                print(f"\n=== Compress Open queue: {bic!r} ===")
                compress_results.extend(
                    compress_drafter_queue(bic, apply=args.apply, exclude_ids=leaving_open_ids)
                )
            if not compress_bics:
                print("\n(no single-drafter queues to compress)")

        report = {
            "mode": mode,
            "ran_at": datetime.utcnow().isoformat() + "Z",
            "in_sync": in_sync,
            "status_drifts": status_drifts,
            "bic_only_drifts": bic_only if args.also_bic_only else f"{len(bic_only)} (pass --also-bic-only)",
            "errors": errors,
            "applied": applied,
            "compress": compress_results,
        }

        if args.report:
            with open(args.report, "w") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\nWrote report → {args.report}")

        if not args.apply and status_drifts:
            print("\nRe-run with --apply to commit status closes, order clears, and compress.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
