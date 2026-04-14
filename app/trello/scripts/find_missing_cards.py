"""
@milehigh-header
schema_version: 1
purpose: Sync Release stages from Trello and archive releases not present in live_jobs.csv.
exports:
  diff_stage_vs_trello: Compare Releases.stage against Trello card lists and update mismatches.
  archive_inactive_releases: Archive Releases rows whose (job, release) is NOT in live_jobs.csv.
  _read_csv: Read live_jobs.csv and return dict keyed by (job_int, release_str).
  _parse_job_release: Extract (job_int, release_str) tuple from a Trello card name.
imports_from: [app, app.models, app.trello.api, app.api.helpers, csv, dotenv, argparse]
imported_by: []
invariants:
  - diff_stage_vs_trello treats Trello as source of truth for stage values.
  - Contains large blocks of commented-out code from earlier iterations.
  - Requires Flask app context (created via create_app at __main__).
  - Invoked directly: python -m app.trello.scripts.find_missing_cards [--dry-run]
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Archive inactive releases: sets is_archived=True on Releases rows
whose (job, release) is NOT in live_jobs.csv.

Usage:
    python -m app.trello.scripts.find_missing_cards [--dry-run]
"""

import argparse
import csv
import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import Releases, db
from app.trello.api import get_all_trello_cards
from app.api.helpers import get_stage_group_from_stage


CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "live_jobs.csv")


# TARGET_LISTS = [
#     "Released",
#     "Fit Up Complete.",
#     "Paint complete",
#     "Store at MHMW for shipping",
#     "Shipping planning",
#     "Shipping completed",
# ]


# def _auth_params():
#     return {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}


# def confirm_board():
#     """Fetch and display the Trello board name to confirm access."""
#     url = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}"
#     resp = requests.get(url, params=_auth_params())
#     resp.raise_for_status()
#     board = resp.json()
#     print(f"Board name: {board['name']}")
#     print(f"Board ID:   {board['id']}")
#     print(f"Board URL:  {board['url']}")


# def count_cards_in_lists():
#     """Count cards in each target list."""
#     url = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/lists"
#     resp = requests.get(url, params=_auth_params())
#     resp.raise_for_status()
#     lists = resp.json()
#
#     list_map = {}
#     for lst in lists:
#         if lst["name"] in TARGET_LISTS:
#             list_map[lst["name"]] = lst["id"]
#
#     missing = set(TARGET_LISTS) - set(list_map.keys())
#     if missing:
#         print(f"WARNING: Lists not found on board: {missing}")
#
#     total = 0
#     print("\nCard counts by list:")
#     print("-" * 45)
#     for name in TARGET_LISTS:
#         if name not in list_map:
#             continue
#         url = f"https://api.trello.com/1/lists/{list_map[name]}/cards"
#         resp = requests.get(url, params={**_auth_params(), "fields": "id"})
#         resp.raise_for_status()
#         count = len(resp.json())
#         total += count
#         print(f"  {name:<35} {count:>4}")
#     print("-" * 45)
#     print(f"  {'TOTAL':<35} {total:>4}")


# def compare_csv_to_releases():
#     """Compare live_jobs.csv against the Releases table."""
#     csv_records = _read_csv()
#
#     print(f"\n--- CSV vs Releases Table ---")
#     print(f"  CSV records: {len(csv_records)}")
#
#     all_releases = Releases.query.all()
#     db_keys = {(r.job, str(r.release)) for r in all_releases}
#     print(f"  Releases table records: {len(all_releases)}")
#
#     in_csv_not_db = set(csv_records.keys()) - db_keys
#     in_db_not_csv = db_keys - set(csv_records.keys())
#
#     print(f"\n  In CSV but NOT in Releases table: {len(in_csv_not_db)}")
#     if in_csv_not_db:
#         print("-" * 65)
#         for job, rel in sorted(in_csv_not_db):
#             info = csv_records[(job, rel)]
#             print(f"    {job}-{rel:<6} {info['name'][:30]:<32} {info['description'][:25]}")
#
#     print(f"\n  In Releases table but NOT in CSV: {len(in_db_not_csv)}")
#     if in_db_not_csv:
#         print("-" * 65)
#         for job, rel in sorted(in_db_not_csv):
#             match = next((r for r in all_releases if r.job == job and str(r.release) == rel), None)
#             if match:
#                 print(f"    {job}-{rel:<6} {(match.job_name or '')[:30]:<32} {(match.description or '')[:25]}")
#             else:
#                 print(f"    {job}-{rel}")
#
#     print()


# def _parse_job_release(card_name):
#     """Parse job-release from a card name like '170-287 Garrett ...'"""
#     parts = card_name.split(" ", 1)
#     if not parts:
#         return None
#     token = parts[0]
#     if "-" not in token:
#         return None
#     job_str, release_str = token.split("-", 1)
#     try:
#         return (int(job_str), release_str)
#     except ValueError:
#         return None


# def compare_csv_to_trello():
#     """Compare live_jobs.csv against actual Trello cards on the board."""
#     csv_records = _read_csv()
#     print(f"\n--- CSV vs Trello Cards ---")
#     print(f"  CSV records: {len(csv_records)}")
#
#     url = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/lists"
#     resp = requests.get(url, params=_auth_params())
#     resp.raise_for_status()
#     lists = resp.json()
#
#     target_list_ids = {}
#     for lst in lists:
#         if lst["name"] in TARGET_LISTS:
#             target_list_ids[lst["id"]] = lst["name"]
#
#     all_cards = []
#     for list_id, list_name in target_list_ids.items():
#         url = f"https://api.trello.com/1/lists/{list_id}/cards"
#         resp = requests.get(url, params={**_auth_params(), "fields": "name,idList"})
#         resp.raise_for_status()
#         all_cards.extend(resp.json())
#     print(f"  Cards in target lists: {len(all_cards)}")
#
#     trello_keys = {}
#     unparsed = []
#     for card in all_cards:
#         parsed = _parse_job_release(card["name"])
#         if parsed:
#             trello_keys[parsed] = {
#                 "card_name": card["name"],
#                 "list_name": target_list_ids.get(card["idList"], "Unknown"),
#             }
#         else:
#             unparsed.append(card["name"])
#
#     print(f"  Parsed cards: {len(trello_keys)}")
#     if unparsed:
#         print(f"  Unparsed card names: {len(unparsed)}")
#
#     in_csv_not_trello = set(csv_records.keys()) - set(trello_keys.keys())
#     in_trello_not_csv = set(trello_keys.keys()) - set(csv_records.keys())
#     matched = set(csv_records.keys()) & set(trello_keys.keys())
#
#     from collections import Counter
#     list_counts = Counter()
#     list_items = {}
#     for key in matched:
#         lname = trello_keys[key]["list_name"]
#         list_counts[lname] += 1
#         list_items.setdefault(lname, []).append(key)
#
#     print(f"\n  Active CSV records by Trello list ({len(matched)} matched):")
#     print("-" * 50)
#     for lname, count in list_counts.most_common():
#         print(f"    {lname:<35} {count:>4}")
#     print("-" * 50)
#     print(f"    {'TOTAL':<35} {sum(list_counts.values()):>4}")
#
#     print(f"\n  In CSV but NOT in target lists: {len(in_csv_not_trello)}")
#     if in_csv_not_trello:
#         print("-" * 70)
#         for job, rel in sorted(in_csv_not_trello):
#             info = csv_records[(job, rel)]
#             print(f"    {job}-{rel:<6} {info['name'][:30]:<32} {info['description'][:30]}")
#
#         print(f"\n  Checking {len(in_csv_not_trello)} missing cards against all board lists...")
#         all_list_map = {lst["id"]: lst["name"] for lst in lists}
#         url = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/cards"
#         resp = requests.get(url, params={**_auth_params(), "fields": "name,idList"})
#         resp.raise_for_status()
#         board_cards = resp.json()
#
#         board_keys = {}
#         for card in board_cards:
#             parsed = _parse_job_release(card["name"])
#             if parsed:
#                 board_keys.setdefault(parsed, []).append({
#                     "card_name": card["name"],
#                     "list_name": all_list_map.get(card["idList"], "Unknown"),
#                 })
#
#         found_elsewhere = []
#         truly_missing = []
#         for key in sorted(in_csv_not_trello):
#             if key in board_keys:
#                 for hit in board_keys[key]:
#                     found_elsewhere.append((key, hit))
#             else:
#                 truly_missing.append(key)
#
#         if found_elsewhere:
#             print(f"\n  Found in mirror/crew lists: {len(found_elsewhere)}")
#             print("-" * 80)
#             for (job, rel), hit in found_elsewhere:
#                 print(f"    {job}-{rel:<6} [{hit['list_name']:<25}]  {hit['card_name'][:45]}")
#
#         if truly_missing:
#             print(f"\n  TRULY MISSING (not on board at all): {len(truly_missing)}")
#             print("-" * 70)
#             for job, rel in truly_missing:
#                 info = csv_records[(job, rel)]
#                 print(f"    {job}-{rel:<6} {info['name'][:30]:<32} {info['description'][:30]}")
#
#     print(f"\n  On Trello board but NOT in CSV: {len(in_trello_not_csv)}")
#
#     print()


def _read_csv():
    """Read live_jobs.csv and return dict keyed by (job_int, release_str)."""
    records = {}
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            job = row["Job "].strip() if "Job " in row else row["Job"].strip()
            release = row["Release"].strip()
            name = row["Name"].strip()
            desc = row["Description"].strip()
            key = (int(job), release)
            records[key] = {"name": name, "description": desc}
    return records


def _parse_job_release(card_name):
    """Parse job-release from a card name like '170-287 Garrett ...'"""
    parts = card_name.split(" ", 1)
    if not parts:
        return None
    token = parts[0]
    if "-" not in token:
        return None
    job_str, release_str = token.split("-", 1)
    try:
        return (int(job_str), release_str)
    except ValueError:
        return None


TARGET_LISTS = [
    "Released",
    "Fit Up Complete.",
    "Paint complete",
    "Store at MHMW for shipping",
    "Shipping planning",
    "Shipping completed",
]


def diff_stage_vs_trello(dry_run=False):
    """Compare Releases.stage against actual Trello card list for non-archived rows.

    Only considers cards in the 6 target lists. Cards in other lists (mirror/crew)
    are ignored. Updates mismatched stages to match Trello (source of truth).
    """
    print("\n--- Sync Release Stages from Trello ---")
    print(f"  Database: {db.engine.url}")

    # Fetch all Trello cards, keep only those in target lists
    print("Fetching Trello cards...")
    board_cards = get_all_trello_cards()
    target_cards = [c for c in board_cards if c["list_name"] in TARGET_LISTS]

    card_by_id = {c["id"]: c for c in target_cards}

    # Also build a lookup by (job, release) from card names
    card_by_key = {}
    for c in target_cards:
        parsed = _parse_job_release(c["name"])
        if parsed:
            card_by_key[parsed] = c

    print(f"  Trello cards on board: {len(board_cards)}")
    print(f"  Cards in target lists: {len(target_cards)}")

    # Query non-archived releases
    releases = Releases.query.filter(Releases.is_archived == False).all()
    print(f"  Non-archived Releases: {len(releases)}")

    matched = []
    mismatched = []
    no_card = []

    for rel in releases:
        # Try matching by trello_card_id first, then by job-release
        card = None
        if rel.trello_card_id:
            card = card_by_id.get(rel.trello_card_id)
        if not card:
            key = (rel.job, str(rel.release))
            card = card_by_key.get(key)

        if not card:
            no_card.append(rel)
            continue

        trello_list = card["list_name"]
        db_stage = rel.stage or "(none)"

        if db_stage == trello_list:
            matched.append(rel)
        else:
            mismatched.append((rel, db_stage, trello_list))

    print(f"\n  Already correct: {len(matched)}")
    print(f"  Mismatched (to update): {len(mismatched)}")
    print(f"  No card in target lists: {len(no_card)}")

    if mismatched:
        print(f"\n  {'Job-Rel':<14} {'DB Stage':<30} {'Trello List':<30}")
        print("  " + "-" * 74)
        for rel, db_stage, trello_list in sorted(mismatched, key=lambda x: (x[0].job, x[0].release)):
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"  {prefix}{rel.job}-{rel.release:<8} {db_stage:<30} -> {trello_list:<30}")

        if not dry_run:
            for rel, _old, trello_list in mismatched:
                rel.stage = trello_list
                rel.stage_group = get_stage_group_from_stage(trello_list)
            db.session.commit()
            print(f"\n  Updated {len(mismatched)} release stages")

    if no_card:
        print(f"\n  Releases with no card in target lists (skipped):")
        print("  " + "-" * 50)
        for rel in sorted(no_card, key=lambda r: (r.job, r.release)):
            print(f"  {rel.job}-{rel.release:<8} stage={rel.stage or '(none)'}")

    print()


def archive_inactive_releases(dry_run=False):
    """Archive Releases rows whose (job, release) is NOT in live_jobs.csv."""
    csv_records = _read_csv()
    active_keys = set(csv_records.keys())  # set of (int, str)

    non_archived = Releases.query.filter(Releases.is_archived == False).all()
    db_uri = db.engine.url
    print(f"\n--- Archive Inactive Releases ---")
    print(f"  Database: {db_uri}")
    print(f"  Active CSV records: {len(active_keys)}")
    print(f"  Non-archived Releases rows: {len(non_archived)}")

    to_archive = []
    for rel in non_archived:
        key = (rel.job, str(rel.release))
        if key not in active_keys:
            to_archive.append(rel)

    print(f"  Releases to archive: {len(to_archive)}")
    print(f"  Releases to keep: {len(non_archived) - len(to_archive)}")

    if not to_archive:
        print("  Nothing to archive.")
        return 0

    if dry_run:
        print("-" * 65)
        for rel in sorted(to_archive, key=lambda r: (r.job, r.release)):
            print(f"  [DRY RUN] Would archive: {rel.job}-{rel.release} {(rel.job_name or '')[:30]}")
        return len(to_archive)

    for rel in to_archive:
        rel.is_archived = True

    db.session.commit()
    print(f"  Archived {len(to_archive)} rows")
    return len(to_archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Release stage vs Trello diff check")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no changes")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        diff_stage_vs_trello(dry_run=args.dry_run)
