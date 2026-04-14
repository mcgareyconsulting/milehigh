# Agent-Optimized File Header Generation — Mile High

You are going to add structured, agent-readable headers to source files in this repo. These headers exist to let future agent runs (Claude Code spawned on bug-fix and feature tasks) load context faster — they should answer "why does this file exist, what does it expose, what depends on it, what are the gotchas" without the agent having to explore.

This is a Flask backend + React 19 frontend repo. Read `CLAUDE.md` at the repo root before you begin — it has the architectural context you'll need to write good `purpose` lines and identify real invariants. The examples below are drawn from that context.

This is a careful, high-stakes pass. You will touch many files. Follow the rules exactly.

## The format

Every processed file gets a structured header block at the top. The field names and structure are identical across languages so the headers are uniformly grep-able.

For Python files, the header lives inside the module docstring at the top of the file. If the file already has a module docstring, prepend the header fields to it (header block, blank line, then preserve the original docstring text). If there's no existing docstring, create one containing only the header.

```python
"""
@milehigh-header
schema_version: 1
purpose: <ONE sentence. The WHY, not the WHAT.>
exports:
  <SymbolName>: <one-line semantic>
  <SymbolName>: <one-line semantic>
imports_from: [<relative paths or package names, max 8>]
imported_by: [<relative paths in this repo that import this file>]
invariants:
  - <non-obvious rule a future editor must not violate>
updated_by_agent: <ISO8601 timestamp> (commit <short SHA>)

<original module docstring text, if any, preserved here verbatim>
"""
```

For TypeScript/JavaScript files:

```typescript
/**
 * @milehigh-header
 * schema_version: 1
 * purpose: <ONE sentence. The WHY, not the WHAT.>
 * exports:
 *   <SymbolName>: <one-line semantic>
 *   <SymbolName>: <one-line semantic>
 * imports_from: [<relative paths or package names, max 8>]
 * imported_by: [<relative paths in this repo that import this file>]
 * invariants:
 *   - <non-obvious rule a future editor must not violate>
 * updated_by_agent: <ISO8601 timestamp> (commit <short SHA>)
 */
```

## Rules per field

### purpose
- One sentence, ~20 words max.
- The *why*, not the *what*. State the responsibility or invariant this file owns.
- BAD: "This module provides functions for processing Trello webhooks."
- GOOD: "Drains the Trello webhook queue on a thread pool, holding the sync lock to prevent OneDrive contention."
- BAD: "Defines the Submittals model."
- GOOD: "ORM model for Procore submittals; table was renamed from `procore_submittals`, so old scripts import via the `ProcoreSubmittal` alias."
- For barrel/index/`__init__.py` files that only re-export: "Re-exports <X> for <reason>." and move on. (See special cases below for init files that do real work.)

### exports
- Public exports only. For Python: top-level functions, classes, and constants intended to be imported elsewhere. Skip private (`_prefixed`) helpers.
- For Flask blueprints, list the blueprint object and route handlers that are referenced by name elsewhere (most aren't — usually just the blueprint itself matters).
- For React components, list the default export and any named exports that are used outside the file.
- Max 5. If more, list the 5 most important and add `...and N more`.
- One symbol per line, one-line semantic. No type signatures — the code has those.

### imports_from
- External packages and internal relative imports. Max 8.
- Internal imports as paths from repo root (e.g. `app/models`, `app/services/outbox_service`), not Python's relative import syntax.
- Skip type-only imports unless they're the point of the file.

### imported_by
- Files in THIS repo that import this file.
- Discover them with grep. Do NOT guess.
- For Python files: compute the file's dotted module path (e.g. `app/services/outbox_service.py` → `app.services.outbox_service`) and grep for both `from app.services.outbox_service` and `from app.services import outbox_service`. Also grep for `import app.services.outbox_service` for the rare absolute-import case.
- For TS/TSX files: grep for the file's path (without extension) inside `from '...'` and `require('...')` strings, both relative and absolute.
- Filter out the file itself and test files (`test_*.py`, `*_test.py`, `*.test.ts`, `*.test.tsx`, `*.spec.*`).
- Max 10. If more, list the 10 most architecturally significant and add `...and N more`.
- If zero files import it, write `[]`. If it's clearly an entry point (`run.py`, `app/__init__.py`) note that in invariants instead of flagging dead code.

### invariants
- Non-obvious rules. Things that cause bugs if violated and aren't enforced by types or obvious from reading the code.
- 0–4 entries. Zero is fine. Do not invent invariants to fill space.
- These should come from reading the actual file and recognizing real gotchas, not from generic best practices.
- BAD: "Functions should have docstrings." / "Uses type hints." / "Logs errors."
- GOOD examples grounded in this codebase:
  - "Imports `Submittals` not `ProcoreSubmittal` — the table was renamed in M2; old name is an alias for backwards compat."
  - "`Job` here means job log entries (table `jobs`), NOT the geofence model `Jobs` (table `job_sites`)."
  - "Must hold `sync_lock` before processing — Trello and OneDrive cannot run concurrently."
  - "Webhook handler must be idempotent; check `WebhookReceipt` before processing."
  - "Outbox writes must use `OutboxService`, not direct DB inserts, so retry semantics are preserved."
  - "Background job; `get_current_user()` will return None — do not call it here."
  - "Scheduler job; only runs on the process where `WERKZEUG_RUN_MAIN` or `IS_RENDER_SCHEDULER` is set."
  - "Burst dedup window is 15 seconds — events with the same payload hash within that window are dropped."
  - "All routes require `@admin_required`; do not add public routes to this blueprint."

### updated_by_agent
- Current ISO8601 timestamp.
- Run `git rev-parse --short HEAD` to get the SHA.

## Process for each file

1. Read the file in full.
2. Identify public exports by scanning for `def`, `class`, `export`, etc. at the top level.
3. Run grep from the repo root to find files that import this one (see `imported_by` rules above for the patterns). Filter out the file itself and test files.
4. Write the header block.
5. Insert the header block at the top of the file.
   - **Python:** The header goes inside the module docstring at the very top of the file. Order is: `#!` shebang (if present) → encoding declaration (if present) → module docstring containing the header → `from __future__` imports → other imports. If a module docstring already exists, prepend the header fields to it (preserve the original prose text after the header fields, separated by a blank line).
   - **TS/TSX/JS:** The header goes in a `/** */` JSDoc block at the very top, after any shebang or license header, before any imports.
6. If a `@milehigh-header` block already exists, REPLACE it entirely. Do not merge.
7. Run `git diff <filepath>` and verify the ONLY change is the header insertion (and, for Python files with existing docstrings, the merge of the header into that docstring). If anything else changed, revert the file and stop — something went wrong.
8. Print one line: `✓ <filepath>` and move to the next file.

## Hard rules — do not violate

- **Do not modify any other part of any file. Ever.** Headers only. If you find a bug, do not fix it. If you find dead code, do not delete it. If you find a typo in a comment, leave it. Opportunistic edits are forbidden because they make this PR unreviewable.
- Never invent imports, exports, or `imported_by` entries you didn't verify by reading or grepping.
- If you are uncertain about a field, prefer empty/shorter over speculative.
- Do not commit. I'll handle git operations.
- Do not modify any file under: `node_modules/`, `frontend/dist/`, `frontend/build/`, `__pycache__/`, `.venv/`, `venv/`, `migrations/versions/` (autogenerated alembic), `logs/`.
- Skip entirely: test files (`test_*.py`, `*_test.py`, `*.test.ts`, `*.test.tsx`, `*.spec.*`), generated files (look for `# AUTOGENERATED` or `// @generated`), files under 20 lines, JSON/YAML/markdown/config files, alembic migration files, `conftest.py` files (these are fixtures, not application code).

## Special cases

A few files need different handling:

- **`app/__init__.py`** — This is the Flask app factory and does substantial work (blueprint registration, scheduler setup, outbox worker startup). Do NOT treat it as a barrel file. Write a full header capturing what it sets up, what depends on `WERKZEUG_RUN_MAIN` / `IS_RENDER_SCHEDULER`, and the threading model (APScheduler 3-worker pool, daemon outbox thread).

- **`app/models.py`** — If this file contains more than 5 model classes, do not try to capture per-model invariants in the file header. Write a `purpose` line that identifies it as the central ORM module, list up to 5 of the most important models in `exports` with a final `...and N more` if applicable, and put only the *file-wide* invariants in `invariants` (e.g. the `Job` vs `Jobs` naming collision, the `Submittals` rename and alias, the `Job as Releases` integration alias). Do not list per-model invariants — those belong on individual classes if anywhere.

- **`run.py`** — Entry point. `imported_by: []` is correct; note "Application entry point — invoked directly, not imported" in invariants.

- **Blueprint `__init__.py` files** (e.g. `app/trello/__init__.py`) — These usually export the blueprint object and wire up routes. Write a full header; do not use the barrel shortcut. The `purpose` should describe what the blueprint does, not just "package init."

## How we're going to run this

This is a multi-stage process. Do NOT start processing the whole repo immediately.

**Stage 0 — Read the architecture.** Before anything else, read `CLAUDE.md` at the repo root. The architectural notes there (blueprints, sync lock, naming collisions, migration order, scheduler gotchas) should directly inform the invariants you write. If you write a header for a file in `app/trello/` and don't reference the sync lock or queue patterns where relevant, you're not paying attention.

**Stage 1 — Plan.** Before touching anything:
- List the top-level directories under `app/` and under `frontend/src/`.
- Count the eligible files in each (apply the skip rules above). Distinguish Python (`.py`) from TS/TSX so I can see the split.
- Estimate roughly how many files total.
- Pick 6 files for the sample pass that span the difficulty range:
  1. One Python `__init__.py` or barrel that re-exports
  2. One model file. **If `app/models.py` is the monolith (more than 5 classes), pick a smaller more typical service or utility module instead so the sample shows the format at its best — `app/models.py` will be handled as a special case during the full pass.**
  3. One blueprint route file (e.g. something under `app/trello/`, `app/procore/`, or `app/brain/board/`)
  4. One service module (e.g. under `app/services/`)
  5. One React page or component under `frontend/src/`
  6. One frontend service/hook file under `frontend/src/services/` or `frontend/src/hooks/`
- Tell me which 6 you picked and why.
- Stop and wait for me to say "go".

**Stage 2 — Sample pass.** When I say go:
- Process ONLY those 6 files.
- After each one, print `✓ <filepath>` so I can see progress.
- After all 6, stop and wait. I'll review the headers by hand and either tell you to adjust the format, redo specific files, or proceed to the full pass.

**Stage 3 — Full pass.** Only after I explicitly approve the sample:
- Process directory by directory. Do `app/` subdirectories first (one at a time), then `frontend/src/` subdirectories. After each directory, print a one-line summary (`Finished app/trello/ — 8 files`) and continue.
- If you hit any file where the dirty-check in step 7 fails, stop immediately and tell me which file and what changed.
- If you're unsure about a file (unusual structure, can't determine purpose, ambiguous exports), skip it and add it to a list to show me at the end rather than guessing.

Begin Stage 0 now.
