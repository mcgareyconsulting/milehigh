"""
Seed script to import brain-notes.csv into board_items and board_activity tables.

Run with:
    python migrations/seed_board_from_csv.py

Walks through every item and comment, asking who authored each one (Daniel or Bill).
"""

import sys
import os
import csv
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, BoardItem, BoardActivity, User

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'brain-notes.csv')


def infer_status(text):
    if not text:
        return 'open'
    t = text.lower()
    if any(w in t for w in ['deploying', 'deployed', 'production']):
        return 'deployed'
    if any(w in t for w in ['complete', 'fixed', 'improved', 'updated']):
        return 'deployed'
    if any(w in t for w in ['working', 'in progress', 'started']):
        return 'in_progress'
    return 'open'


def pick_user(users, role_label):
    print(f"\n  Who is {role_label}?")
    for i, u in enumerate(users, 1):
        name = f"{u.first_name or ''} {u.last_name or ''}".strip() or '(no name)'
        print(f"    {i}) {name}  ({u.username})  [id={u.id}]")
    while True:
        choice = input(f"  Enter number (1-{len(users)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(users):
            return users[int(choice) - 1]
        print(f"  Invalid choice. Pick 1-{len(users)}.")


def confirm(prompt):
    while True:
        answer = input(f"  {prompt} (y/n): ").strip().lower()
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False


def ask_author(daniel_name, bill_name, label, text_preview):
    """Quick 1/2 prompt: who wrote this?"""
    # Truncate long text for display
    preview = text_preview.replace('\n', ' ')
    if len(preview) > 120:
        preview = preview[:117] + '...'

    print(f"\n    {label}:")
    print(f"    \"{preview}\"")
    print(f"      1) {daniel_name}   2) {bill_name}   s) skip this entry")
    while True:
        choice = input("      -> ").strip().lower()
        if choice == '1':
            return 'daniel'
        if choice == '2':
            return 'bill'
        if choice == 's':
            return 'skip'
        print("      Pick 1, 2, or s")


def seed():
    app = create_app()
    with app.app_context():
        existing = BoardItem.query.count()
        if existing > 0:
            print(f"\n  Board already has {existing} items.")
            if not confirm("Wipe existing board data and re-seed?"):
                print("  Aborted.")
                return True
            BoardActivity.query.delete()
            BoardItem.query.delete()
            db.session.commit()
            print(f"  Cleared {existing} items.")

        users = User.query.order_by(User.id).all()
        if not users:
            print("  ERROR: No users found. Create at least one user first.")
            return False

        print("\n=== Bug Tracker Seed ===")
        print(f"  Found {len(users)} user(s) in the database.\n")

        daniel = pick_user(users, "Daniel McGarey")
        daniel_name = f"{daniel.first_name or ''} {daniel.last_name or ''}".strip() or daniel.username

        bill = pick_user(users, "Bill O'Neill")
        bill_name = f"{bill.first_name or ''} {bill.last_name or ''}".strip() or bill.username

        people = {
            'daniel': {'id': daniel.id, 'name': daniel_name},
            'bill': {'id': bill.id, 'name': bill_name},
        }

        print(f"\n  Daniel = {daniel_name} (id={daniel.id})")
        print(f"  Bill   = {bill_name} (id={bill.id})")
        print(f"\n  For each item and comment, pick 1={daniel_name} or 2={bill_name} or s=skip.")
        print("  ─" * 30)

        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)

        created_count = 0
        skipped_count = 0

        for i, row in enumerate(rows):
            if i < 2:
                continue

            while len(row) < 6:
                row.append('')

            dwl_desc = row[0].strip()
            dwl_response = row[1].strip()
            jl_desc = row[3].strip()
            jl_response = row[4].strip()
            jl_feedback = row[5].strip()

            # ── Drafting WL item ──
            if dwl_desc:
                print(f"\n  ── Drafting WL (row {i+1}) ──")
                author = ask_author(daniel_name, bill_name, "FEATURE/BUG", dwl_desc)
                if author == 'skip':
                    skipped_count += 1
                else:
                    status = infer_status(dwl_response)
                    item = BoardItem(
                        title=dwl_desc[:300],
                        category='Drafting WL',
                        status=status,
                        priority='normal',
                        author_id=people[author]['id'],
                        author_name=people[author]['name'],
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.session.add(item)
                    db.session.flush()

                    if dwl_response:
                        comment_author = ask_author(daniel_name, bill_name, "COMMENT", dwl_response)
                        if comment_author != 'skip':
                            db.session.add(BoardActivity(
                                item_id=item.id,
                                type='comment',
                                body=dwl_response,
                                author_id=people[comment_author]['id'],
                                author_name=people[comment_author]['name'],
                            ))

                    created_count += 1

            # ── Job Log item ──
            if jl_desc:
                print(f"\n  ── Job Log (row {i+1}) ──")
                author = ask_author(daniel_name, bill_name, "FEATURE/BUG", jl_desc)
                if author == 'skip':
                    skipped_count += 1
                else:
                    status = infer_status(jl_response)
                    item = BoardItem(
                        title=jl_desc[:300],
                        category='Job Log',
                        status=status,
                        priority='normal',
                        author_id=people[author]['id'],
                        author_name=people[author]['name'],
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.session.add(item)
                    db.session.flush()

                    if jl_response:
                        comment_author = ask_author(daniel_name, bill_name, "COMMENT 1", jl_response)
                        if comment_author != 'skip':
                            db.session.add(BoardActivity(
                                item_id=item.id,
                                type='comment',
                                body=jl_response,
                                author_id=people[comment_author]['id'],
                                author_name=people[comment_author]['name'],
                            ))

                    if jl_feedback:
                        comment_author = ask_author(daniel_name, bill_name, "COMMENT 2", jl_feedback)
                        if comment_author != 'skip':
                            db.session.add(BoardActivity(
                                item_id=item.id,
                                type='comment',
                                body=jl_feedback,
                                author_id=people[comment_author]['id'],
                                author_name=people[comment_author]['name'],
                            ))

                    created_count += 1

        db.session.commit()
        print(f"\n  ─" * 30)
        print(f"  Done! Seeded {created_count} items ({skipped_count} skipped).")
        return True


if __name__ == '__main__':
    success = seed()
    sys.exit(0 if success else 1)
