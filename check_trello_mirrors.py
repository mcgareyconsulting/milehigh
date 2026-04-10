"""
Check which active Job Log releases have a Trello card missing its mirror.

Every release should have a primary card (in Released, Fit Up Complete., etc.)
and a mirror card (in another list like Unassigned, a fab-guy list, Complete., etc.).
Mirrors are copies with the same card name. This script matches by name.

Usage:
    python check_trello_mirrors.py
"""
import csv
import os
import sys
from urllib.parse import urlparse, urlunparse

from app import create_app
from app.config import Config as cfg
from app.models import Releases, db
from app.trello.api import get_all_trello_cards


TARGET_LISTS = [
    "Released",
    "Fit Up Complete.",
    "Paint complete",
    "Store at MHMW for shipping",
    "Shipping planning",
    "Shipping completed",
]


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
    app = create_app()

    with app.app_context():
        # --- Environment info ---
        environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
        db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        print("=" * 70)
        print("TRELLO MIRROR CHECK — Active releases missing mirror cards")
        print("=" * 70)
        print(f"\n  Environment : {environment}")
        print(f"  Database URI: {redact_uri(db_uri)}")
        print(f"  Trello Board: {cfg.TRELLO_BOARD_ID}")

        # --- Get active releases from DB ---
        active_releases = Releases.query.filter_by(
            is_archived=False, is_active=True
        ).all()
        releases_with_cards = [r for r in active_releases if r.trello_card_id]
        release_by_card_id = {r.trello_card_id: r for r in releases_with_cards}
        print(f"\n  Active releases in DB:    {len(active_releases):,}")
        print(f"  With Trello card IDs:     {len(releases_with_cards):,}")

        # --- Fetch all board cards ---
        print(f"\n{'—' * 70}")
        print("Fetching all cards from Trello board...")
        print(f"{'—' * 70}")
        all_cards = get_all_trello_cards()
        board_card_lookup = {c["id"]: c for c in all_cards}
        print(f"  Total open cards on board: {len(all_cards):,}")

        # Split into primary and other lists
        primary_cards = [c for c in all_cards if c["list_name"] in TARGET_LISTS]
        other_cards = [c for c in all_cards if c["list_name"] not in TARGET_LISTS]
        other_names = set(c["name"] for c in other_cards)

        print(f"  Cards in primary lists:    {len(primary_cards):,}")
        print(f"  Cards in other lists:      {len(other_cards):,}")

        # --- Match active releases to board cards ---
        active_primary = []
        not_on_board = []

        for rel in releases_with_cards:
            card = board_card_lookup.get(rel.trello_card_id)
            if not card:
                not_on_board.append(rel)
            elif card["list_name"] in TARGET_LISTS:
                active_primary.append((rel, card))

        # --- Check for mirrors by name match ---
        has_mirror = []
        missing_mirror = []

        for rel, card in active_primary:
            if card["name"] in other_names:
                has_mirror.append((rel, card))
            else:
                missing_mirror.append((rel, card))

        # --- Results ---
        print(f"\n{'—' * 70}")
        print("Results (active DB releases in primary lists)")
        print(f"{'—' * 70}")
        print(f"  Total checked:               {len(active_primary):,}")
        print(f"  WITH mirror (name match):    {len(has_mirror):,}")
        print(f"  WITHOUT mirror:              {len(missing_mirror):,}  <-- MISSING")
        if not_on_board:
            print(f"  Card not found on board:     {len(not_on_board):,}")

        # --- Split missing into shipped vs in-progress ---
        missing_shipped = [(r, c) for r, c in missing_mirror if c["list_name"] == "Shipping completed"]
        missing_active = [(r, c) for r, c in missing_mirror if c["list_name"] != "Shipping completed"]

        if missing_active:
            print(f"\n{'=' * 70}")
            print(f"MISSING MIRRORS — IN-PROGRESS ({len(missing_active)} cards)")
            print(f"{'=' * 70}")
            print(
                f"  {'Job':<8} {'Rel':<8} {'Job Name':<35} {'List':<25} {'Description'}"
            )
            print(
                f"  {'---':<8} {'---':<8} {'--------':<35} {'----':<25} {'-----------'}"
            )
            for rel, card in sorted(missing_active, key=lambda x: (x[0].job, x[0].release)):
                job_name = (rel.job_name or "")[:33]
                desc = (rel.description or "")[:45]
                list_name = card["list_name"][:23]
                print(
                    f"  {rel.job:<8} {rel.release:<8} {job_name:<35} {list_name:<25} {desc}"
                )

        if missing_shipped:
            print(f"\n{'—' * 70}")
            print(f"MISSING MIRRORS — SHIPPING COMPLETED ({len(missing_shipped)} cards)")
            print(f"{'—' * 70}")
            print(
                f"  {'Job':<8} {'Rel':<8} {'Job Name':<35} {'Description'}"
            )
            print(
                f"  {'---':<8} {'---':<8} {'--------':<35} {'-----------'}"
            )
            for rel, card in sorted(missing_shipped, key=lambda x: (x[0].job, x[0].release)):
                job_name = (rel.job_name or "")[:33]
                desc = (rel.description or "")[:45]
                print(
                    f"  {rel.job:<8} {rel.release:<8} {job_name:<35} {desc}"
                )

        if not missing_mirror:
            print("\n  All active releases in primary lists have mirror cards.")

        # --- Export CSV ---
        csv_path = os.path.join(os.path.dirname(__file__) or ".", "missing_mirrors.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Job", "Release", "Identifier", "Job Name", "Description", "Stage"])
            for rel, card in sorted(missing_mirror, key=lambda x: (x[0].job, x[0].release)):
                writer.writerow([
                    rel.job,
                    rel.release,
                    f"{rel.job}-{rel.release}",
                    rel.job_name or "",
                    rel.description or "",
                    card["list_name"],
                ])
        print(f"\n  CSV exported: {csv_path} ({len(missing_mirror)} rows)")
        print()


if __name__ == "__main__":
    main()
