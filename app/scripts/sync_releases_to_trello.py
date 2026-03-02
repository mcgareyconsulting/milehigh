"""
Create/update Trello cards relative to releases in the database.

This script fills in missing Trello data for releases:
- Creates Trello cards for releases without trello_card_id
- Refreshes Trello data in DB for releases that have cards (fetches from API)

Use --clear-board before syncing to avoid duplicates when repopulating from DB.

Usage:
    python -m app.scripts.sync_releases_to_trello                  # Preview only (dry run)
    python -m app.scripts.sync_releases_to_trello --execute          # Actually sync
    python -m app.scripts.sync_releases_to_trello --execute --clear-board  # Clear board first (prompts to confirm)
    python -m app.scripts.sync_releases_to_trello --execute --clear-board --yes  # Skip confirmation prompt
    python -m app.scripts.sync_releases_to_trello --create-only     # Only create new cards
    python -m app.scripts.sync_releases_to_trello --update-only     # Only refresh DB from Trello
    python -m app.scripts.sync_releases_to_trello --limit 20        # Limit to 20 releases
    python -m app.scripts.sync_releases_to_trello --job 123 --release V001  # Single release
"""

import argparse
from app.trello.scanner import sync_releases_to_trello
from app.logging_config import get_logger

logger = get_logger(__name__)


if __name__ == "__main__":
    from app import create_app

    parser = argparse.ArgumentParser(
        description="Create/update Trello cards relative to releases in the DB"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create/update (default: dry run only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of releases to process",
    )
    parser.add_argument(
        "--job",
        type=int,
        help="Only process releases for this job number",
    )
    parser.add_argument(
        "--release",
        type=str,
        help="Only process this release (requires --job)",
    )
    parser.add_argument(
        "--create-only",
        action="store_true",
        help="Only create cards for releases without them; skip refreshes",
    )
    parser.add_argument(
        "--update-only",
        action="store_true",
        help="Only refresh DB from Trello for releases with cards; skip creates",
    )
    parser.add_argument(
        "--clear-board",
        action="store_true",
        help="Delete all cards from Trello board and clear DB before syncing (avoids duplicates)",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt when using --clear-board",
    )

    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        # Confirm board name from API before clearing (when execute + clear-board and not --yes)
        if args.execute and args.clear_board and not args.yes:
            from app.trello.api import get_board_info
            board = get_board_info()
            if not board or not board.get("name"):
                print("\n❌ ERROR: Could not fetch board name from Trello API. Aborting.")
                exit(1)
            print(f"\n⚠️  About to CLEAR board: {board['name']!r}")
            print(f"   All cards will be deleted. Trello data will be cleared from DB.")
            confirm = input("Type the board name to confirm: ").strip()
            if confirm != board["name"]:
                print(f"\n❌ Confirmation failed. Expected {board['name']!r}. Aborting.")
                exit(1)
            print("")

        results = sync_releases_to_trello(
            dry_run=not args.execute,
            limit=args.limit,
            job_filter=args.job,
            release_filter=args.release,
            create_only=args.create_only,
            update_only=args.update_only,
            clear_board_first=args.clear_board,
        )

        # Print summary
        print("=" * 80)
        print("SYNC RELEASES TO TRELLO RESULTS")
        print("=" * 80)

        if "error" in results:
            print(f"\n❌ ERROR: {results['error']}")
        else:
            if results.get("clear_result"):
                cr = results["clear_result"]
                print(f"\n🗑️  BOARD CLEARED:")
                if cr.get("board_name"):
                    print(f"  Board: {cr['board_name']!r}")
                print(f"  Cards deleted: {cr.get('cards_deleted', 0)}")
                print(f"  DB records cleared: {cr.get('db_cleared', 0) or cr.get('db_would_clear', 0)}")
            print(f"\n📊 SYNC SUMMARY:")
            print(f"  Total releases: {results.get('total', 0)}")

            if args.execute:
                print(f"  ✅ Created: {results.get('created', 0)} cards")
                print(f"  🔄 Updated: {results.get('updated', 0)} DB records")
                print(f"  ❌ Failed: {results.get('failed', 0)}")
                print(f"  ⚠️  Skipped: {results.get('skipped', 0)}")
            else:
                print(f"  Would create: {results.get('created', 0)} cards")
                print(f"  Would update: {results.get('updated', 0)} DB records")
                print(f"\n💡 TIP: Run with --execute to actually sync")

            if results.get("failed_details"):
                print(f"\n❌ FAILED:")
                for item in results["failed_details"][:10]:
                    print(f"  - {item.get('identifier', 'Unknown')}: {item.get('error', 'Unknown')}")

        print("\n" + "=" * 80)
