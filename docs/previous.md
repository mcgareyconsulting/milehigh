# Sync Trello Member IDs to Users Table

## What was built

`app/trello/scripts/sync_member_ids.py` — a one-off script that populates the `trello_id` column on the `users` table by matching local users against Trello board members.

## How it works

1. Calls `get_membership_by_board()` to get all board memberships, then `get_member_by_id()` for each to retrieve the full member object (including `fullName` and `id`).
2. Builds a lookup dict keyed by `fullName.strip().lower()`.
3. Loads all `User` records from the database.
4. For each user, constructs `"{first_name} {last_name}".strip().lower()` and looks it up in the Trello dict.
5. Fallback: if no match, tries looking up just `first_name.lower()` — handles cases where a Trello member's `fullName` is only a first name (e.g. `"gary"`) while the users table has both first and last name (`Gary Almeida`).
6. Sets `user.trello_id = member["id"]` for each match and commits.

## CLI flags

| Flag | Behaviour |
|------|-----------|
| `--dry-run` | Print what would change without writing to the DB |
| `--force` | Overwrite `trello_id` even if already set |

## Usage

```bash
# Preview matches
python -m app.trello.scripts.sync_member_ids --dry-run

# Apply
python -m app.trello.scripts.sync_member_ids
```

## Output

The script prints each update, then a summary table:

```
Fetching Trello board members...
  Found 5 board member(s): ...

  set trello_id for 'jsmith' → 5f1a2b3c...
  set trello_id for 'gary.almeida' → 6g2b3c4d...

============================================================
SUMMARY
============================================================
  Matched / updated : 2
  Skipped (already set, no --force): 1
  Unmatched (no Trello board member with same full name): 1
```

## Matching logic

Primary: `"{first_name} {last_name}"` == Trello `fullName` (case-insensitive)

Fallback: `first_name` == Trello `fullName` (handles Trello members with only a first name set)
