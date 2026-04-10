"""
Check the diff between releases with stage='Paint complete' in the DB
and their actual Trello card positions.

Reports three categories:
  A) DB says Paint Complete but Trello card is in a different list
  B) Trello card is in 'Paint complete' list but DB stage disagrees
  C) Outbox diagnostics — failed/pending items for Paint Complete moves

Usage:
    python check_paint_complete_diff.py          # dry-run report only
    python check_paint_complete_diff.py --fix    # move mismatched cards to match DB
"""
import argparse
import csv
import os
import sys
from urllib.parse import urlparse, urlunparse

from app import create_app
from app.config import Config as cfg
from app.models import Releases, TrelloOutbox, ReleaseEvents, db
from app.trello.api import get_all_trello_cards, get_list_by_name, update_trello_card


PAINT_COMPLETE_VARIANTS = {"Paint complete", "Paint Complete"}


def redact_uri(uri):
    """Redact password from a database URI for safe logging."""
    try:
        parsed = urlparse(uri)
        if parsed.password:
            replaced = parsed._replace(
                netloc=f"{parsed.username}:***@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(replaced)
    except Exception:
        pass
    return uri


def main():
    parser = argparse.ArgumentParser(description="Paint Complete diff check")
    parser.add_argument("--fix", action="store_true",
                        help="Move mismatched Trello cards to match Releases.stage")
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        # --- Environment info ---
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        print("=" * 70)
        print("PAINT COMPLETE DIFF CHECK")
        print("=" * 70)
        print(f"\n  Environment : {environment}")
        print(f"  Database URI: {redact_uri(db_uri)}")
        print(f"  Trello Board: {cfg.TRELLO_BOARD_ID}")

        # --- Query DB: releases with stage = Paint complete ---
        paint_releases = Releases.query.filter(
            Releases.is_archived == False,
            Releases.is_active == True,
            db.func.lower(Releases.stage) == "paint complete",
        ).all()

        release_by_card_id = {}
        no_card_id = []
        for r in paint_releases:
            if r.trello_card_id:
                release_by_card_id[r.trello_card_id] = r
            else:
                no_card_id.append(r)

        print(f"\n  DB releases at 'Paint complete':  {len(paint_releases):,}")
        print(f"    With trello_card_id:            {len(release_by_card_id):,}")
        print(f"    Missing trello_card_id:         {len(no_card_id):,}")

        # --- Fetch all Trello cards ---
        print(f"\n{'—' * 70}")
        print("Fetching all cards from Trello board...")
        print(f"{'—' * 70}")
        all_cards = get_all_trello_cards()
        board_card_lookup = {c["id"]: c for c in all_cards}

        trello_paint_cards = [c for c in all_cards if c["list_name"] == "Paint complete"]
        trello_paint_card_ids = {c["id"] for c in trello_paint_cards}

        print(f"  Total open cards on board:        {len(all_cards):,}")
        print(f"  Cards in 'Paint complete' list:   {len(trello_paint_cards):,}")

        # --- Build reverse lookup: card_id -> Releases (all active) ---
        all_active = Releases.query.filter_by(is_archived=False, is_active=True).all()
        all_release_by_card_id = {r.trello_card_id: r for r in all_active if r.trello_card_id}

        # =================================================================
        # CATEGORY A: DB says Paint Complete, Trello disagrees
        # =================================================================
        cat_a_wrong_list = []   # card exists but in wrong list
        cat_a_not_on_board = [] # card ID set but card not found on board

        for card_id, rel in release_by_card_id.items():
            card = board_card_lookup.get(card_id)
            if not card:
                cat_a_not_on_board.append(rel)
            elif card["list_name"] != "Paint complete":
                cat_a_wrong_list.append((rel, card))

        # =================================================================
        # CATEGORY B: Trello says Paint Complete, DB disagrees
        # =================================================================
        cat_b_wrong_stage = []  # card in Paint complete list, DB stage differs
        cat_b_orphan = []       # card in Paint complete list, no matching release

        for card in trello_paint_cards:
            rel = all_release_by_card_id.get(card["id"])
            if not rel:
                cat_b_orphan.append(card)
            elif rel.stage not in PAINT_COMPLETE_VARIANTS:
                cat_b_wrong_stage.append((rel, card))

        # =================================================================
        # CATEGORY C: Outbox diagnostics for Paint Complete moves
        # =================================================================
        failed_outbox = (
            db.session.query(TrelloOutbox, ReleaseEvents)
            .join(ReleaseEvents, TrelloOutbox.event_id == ReleaseEvents.id)
            .filter(
                ReleaseEvents.action == "update_stage",
                TrelloOutbox.action == "move_card",
                TrelloOutbox.status.in_(["failed", "pending"]),
            )
            .all()
        )

        # Filter to paint complete related events
        paint_outbox = []
        for outbox, event in failed_outbox:
            payload_to = (event.payload or {}).get("to", "")
            if payload_to.lower() == "paint complete":
                paint_outbox.append((outbox, event))

        # =================================================================
        # RESULTS
        # =================================================================
        # Collect all rows for CSV
        csv_rows = []

        # --- Summary ---
        in_sync = len(release_by_card_id) - len(cat_a_wrong_list) - len(cat_a_not_on_board)
        print(f"\n{'=' * 70}")
        print("SUMMARY")
        print(f"{'=' * 70}")
        print(f"  DB Paint Complete releases in sync with Trello:  {in_sync:,}")
        print(f"  [A] DB=Paint Complete, wrong Trello list:        {len(cat_a_wrong_list):,}")
        print(f"  [A] DB=Paint Complete, card missing from board:  {len(cat_a_not_on_board):,}")
        print(f"  [A] DB=Paint Complete, no trello_card_id:        {len(no_card_id):,}")
        print(f"  [B] Trello=Paint complete, DB stage differs:     {len(cat_b_wrong_stage):,}")
        print(f"  [B] Trello=Paint complete, orphan card (no DB):  {len(cat_b_orphan):,}")
        print(f"  [C] Failed/pending outbox items (Paint Comp):    {len(paint_outbox):,}")

        # --- Category A: Wrong list ---
        if cat_a_wrong_list:
            print(f"\n{'=' * 70}")
            print(f"[A] DB = PAINT COMPLETE, TRELLO IN DIFFERENT LIST ({len(cat_a_wrong_list)})")
            print(f"{'=' * 70}")
            print(f"  {'Job':<8} {'Rel':<6} {'Job Name':<30} {'DB Stage':<20} {'Trello List':<25}")
            print(f"  {'---':<8} {'---':<6} {'--------':<30} {'--------':<20} {'-----------':<25}")
            for rel, card in sorted(cat_a_wrong_list, key=lambda x: (x[0].job, x[0].release)):
                job_name = (rel.job_name or "")[:28]
                print(f"  {rel.job:<8} {rel.release:<6} {job_name:<30} {rel.stage:<20} {card['list_name']:<25}")
                csv_rows.append({
                    "Mismatch": "A: Wrong Trello list",
                    "Job": rel.job, "Release": rel.release,
                    "Job Name": rel.job_name or "",
                    "DB Stage": rel.stage, "DB Stage Group": rel.stage_group or "",
                    "Trello List": card["list_name"],
                    "Card ID": rel.trello_card_id or "",
                    "Detail": "",
                })

        # --- Category A: Card not on board ---
        if cat_a_not_on_board:
            print(f"\n{'—' * 70}")
            print(f"[A] DB = PAINT COMPLETE, CARD NOT FOUND ON BOARD ({len(cat_a_not_on_board)})")
            print(f"{'—' * 70}")
            print(f"  {'Job':<8} {'Rel':<6} {'Job Name':<30} {'Card ID':<28}")
            print(f"  {'---':<8} {'---':<6} {'--------':<30} {'-------':<28}")
            for rel in sorted(cat_a_not_on_board, key=lambda x: (x.job, x.release)):
                job_name = (rel.job_name or "")[:28]
                print(f"  {rel.job:<8} {rel.release:<6} {job_name:<30} {rel.trello_card_id:<28}")
                csv_rows.append({
                    "Mismatch": "A: Card not on board",
                    "Job": rel.job, "Release": rel.release,
                    "Job Name": rel.job_name or "",
                    "DB Stage": rel.stage, "DB Stage Group": rel.stage_group or "",
                    "Trello List": "(not on board)",
                    "Card ID": rel.trello_card_id or "",
                    "Detail": "",
                })

        # --- Category A: No card ID ---
        if no_card_id:
            print(f"\n{'—' * 70}")
            print(f"[A] DB = PAINT COMPLETE, NO TRELLO CARD ID ({len(no_card_id)})")
            print(f"{'—' * 70}")
            print(f"  {'Job':<8} {'Rel':<6} {'Job Name':<30} {'Source':<15}")
            print(f"  {'---':<8} {'---':<6} {'--------':<30} {'------':<15}")
            for rel in sorted(no_card_id, key=lambda x: (x.job, x.release)):
                job_name = (rel.job_name or "")[:28]
                source = (rel.source_of_update or "")[:13]
                print(f"  {rel.job:<8} {rel.release:<6} {job_name:<30} {source:<15}")
                csv_rows.append({
                    "Mismatch": "A: No card ID",
                    "Job": rel.job, "Release": rel.release,
                    "Job Name": rel.job_name or "",
                    "DB Stage": rel.stage, "DB Stage Group": rel.stage_group or "",
                    "Trello List": "(no card)",
                    "Card ID": "",
                    "Detail": f"source={rel.source_of_update or ''}",
                })

        # --- Category B: Wrong stage ---
        if cat_b_wrong_stage:
            print(f"\n{'=' * 70}")
            print(f"[B] TRELLO = PAINT COMPLETE, DB STAGE DIFFERS ({len(cat_b_wrong_stage)})")
            print(f"{'=' * 70}")
            print(f"  {'Job':<8} {'Rel':<6} {'Job Name':<30} {'DB Stage':<20} {'Stage Group':<18}")
            print(f"  {'---':<8} {'---':<6} {'--------':<30} {'--------':<20} {'-----------':<18}")
            for rel, card in sorted(cat_b_wrong_stage, key=lambda x: (x[0].job, x[0].release)):
                job_name = (rel.job_name or "")[:28]
                sg = (rel.stage_group or "")[:16]
                print(f"  {rel.job:<8} {rel.release:<6} {job_name:<30} {rel.stage:<20} {sg:<18}")
                csv_rows.append({
                    "Mismatch": "B: DB stage differs",
                    "Job": rel.job, "Release": rel.release,
                    "Job Name": rel.job_name or "",
                    "DB Stage": rel.stage or "", "DB Stage Group": rel.stage_group or "",
                    "Trello List": "Paint complete",
                    "Card ID": card["id"],
                    "Detail": "",
                })

        # --- Category B: Orphan cards ---
        if cat_b_orphan:
            print(f"\n{'—' * 70}")
            print(f"[B] TRELLO = PAINT COMPLETE, NO MATCHING DB RELEASE ({len(cat_b_orphan)})")
            print(f"{'—' * 70}")
            print(f"  {'Card Name':<45} {'Card ID':<28}")
            print(f"  {'---------':<45} {'-------':<28}")
            for card in sorted(cat_b_orphan, key=lambda x: x["name"]):
                card_name = card["name"][:43]
                print(f"  {card_name:<45} {card['id']:<28}")
                csv_rows.append({
                    "Mismatch": "B: Orphan card",
                    "Job": "", "Release": "",
                    "Job Name": card["name"],
                    "DB Stage": "(no release)", "DB Stage Group": "",
                    "Trello List": "Paint complete",
                    "Card ID": card["id"],
                    "Detail": "",
                })

        # --- Category C: Outbox ---
        if paint_outbox:
            print(f"\n{'=' * 70}")
            print(f"[C] FAILED/PENDING OUTBOX ITEMS FOR PAINT COMPLETE ({len(paint_outbox)})")
            print(f"{'=' * 70}")
            print(f"  {'Job':<8} {'Rel':<6} {'Status':<12} {'Retries':<9} {'Error':<45}")
            print(f"  {'---':<8} {'---':<6} {'------':<12} {'-------':<9} {'-----':<45}")
            for outbox, event in sorted(paint_outbox, key=lambda x: x[1].created_at, reverse=True):
                err = (outbox.error_message or "")[:43]
                print(f"  {event.job:<8} {event.release or '':<6} {outbox.status:<12} {outbox.retry_count:<9} {err:<45}")
                csv_rows.append({
                    "Mismatch": f"C: Outbox {outbox.status}",
                    "Job": event.job, "Release": event.release or "",
                    "Job Name": "",
                    "DB Stage": "", "DB Stage Group": "",
                    "Trello List": "",
                    "Card ID": "",
                    "Detail": outbox.error_message or "",
                })

        # --- All clear ---
        total_issues = (
            len(cat_a_wrong_list) + len(cat_a_not_on_board) + len(no_card_id)
            + len(cat_b_wrong_stage) + len(cat_b_orphan) + len(paint_outbox)
        )
        if total_issues == 0:
            print("\n  All Paint Complete releases are in sync with Trello.")

        # --- CSV export ---
        csv_path = os.path.join(os.path.dirname(__file__) or ".", "paint_complete_diff.csv")
        with open(csv_path, "w", newline="") as f:
            fieldnames = ["Mismatch", "Job", "Release", "Job Name", "DB Stage",
                          "DB Stage Group", "Trello List", "Card ID", "Detail"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"\n  CSV exported: {csv_path} ({len(csv_rows)} rows)")

        # =================================================================
        # FIX MODE: Move mismatched cards to "Paint complete" list
        # =================================================================
        if args.fix and cat_a_wrong_list:
            print(f"\n{'=' * 70}")
            print(f"FIX MODE — Moving {len(cat_a_wrong_list)} cards to 'Paint complete'")
            print(f"{'=' * 70}")

            paint_list = get_list_by_name("Paint complete")
            if not paint_list or "id" not in paint_list:
                print("  ERROR: Could not resolve 'Paint complete' list ID from Trello")
                return

            paint_list_id = paint_list["id"]
            moved = 0
            failed = 0

            for rel, card in sorted(cat_a_wrong_list, key=lambda x: (x[0].job, x[0].release)):
                try:
                    update_trello_card(rel.trello_card_id, new_list_id=paint_list_id)
                    rel.trello_list_id = paint_list_id
                    rel.trello_list_name = "Paint complete"
                    moved += 1
                    print(f"  MOVED  {rel.job}-{rel.release}  {card['list_name']} -> Paint complete")
                except Exception as e:
                    failed += 1
                    print(f"  FAILED {rel.job}-{rel.release}  {e}")

            if moved:
                db.session.commit()

            print(f"\n  Moved: {moved}  Failed: {failed}")
        elif args.fix and not cat_a_wrong_list:
            print("\n  --fix: No cards to move (Category A is empty).")

        print()


if __name__ == "__main__":
    main()
