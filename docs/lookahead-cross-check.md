# GC Lookahead Cross-Check — Playbook

**Branch:** `feature/lookahead-schedule`
**Status:** Reusable playbook. No app feature yet — this is the manual method.
**Date:** July 20, 2026

> The GC emails a 3-week lookahead schedule (a Gantt/task PDF). We cross-check its
> dates against where our work actually sits — installed, in fab, or still in
> drafting — so we catch anything that won't be ready when the site needs it.
> Bill's framing: *"cross check our green dates and production projections to make
> sure we are meeting the project schedule."* This doc is how to run that check by
> hand for any job. If/when it becomes a feature, this is the spec.

---

## 1. The three layers you're comparing against

A single scope (e.g. "Building C Structural Steel") moves through three states in
the Brain. A lookahead check has to look at **all three**, because the release
view alone hides the drafting pipeline.

1. **GC-approval submittal** — `Submittals` row, `type = 'Submittal for GC Approval'`.
   The GC blessing the design. `status = 'Closed'` = approved.
2. **Drafting Release Review (DRR)** — `Submittals` row, `type = 'Drafting Release
   Review'`. Our internal shop-drawing release. Carries a `rel` number,
   `submittal_drafting_status` (`'STARTED'` vs `''`), and often a `start_install` /
   `due_date`. When drawings finish, it's **released into a `Releases` row** whose
   `release` matches the DRR's `rel`. A DRR that's still `status='Open'` /
   `'STARTED'` = **not yet released — still on the board**.
3. **Release** — `Releases` row (the job log). This is the fab + install record:
   `stage` / `stage_group`, `start_install` (the "green date"), `comp_eta`,
   `ship_date`, `fab_order`, `job_comp`, `invoiced`.

Lifecycle: **GC-approval (Closed) → DRR (drafting, then released) → Release (fab →
install → complete)**. GC approval and our DRR are independent — design can be
approved while our drawings are still in progress (that's exactly the Building D
gap in the worked example below).

Models: `Releases` — `app/models.py:445`. `Submittals` — `app/models.py:102`.
Event streams: `ReleaseEvents` — `app/models.py:604`, `SubmittalEvents` — `:621`.

## 2. Find the job on both tables

The job log and submittals are linked by **string job number**, not an FK.

- `Releases.job` (int) + `Releases.job_name` (str)
- `Submittals.project_number` (str) + `Submittals.project_name` (str)

The GC's project name won't match ours verbatim — search loosely on a keyword
(`ILIKE '%alta%'`) to pin the number, then pull everything by number.

## 3. Read-only prod access

The analysis is **read-only**. Never run DDL or writes for a lookahead check —
see [User runs migrations] rule. Two gotchas:

- **Verify the DB target first.** The worktree `.env` is a symlink to
  `milehigh/.env`, and its `ENVIRONMENT` flips between `sandbox` and `prod`. Don't
  trust the flag — **force the prod URL explicitly** so the pull is prod-accurate
  regardless of what `ENVIRONMENT` currently says.
- **Belt-and-suspenders read-only:** open the connection with
  `default_transaction_read_only=on` so a stray write can't land.

```python
import os
from dotenv import load_dotenv
import sqlalchemy as sa

load_dotenv('.env')
url = os.environ['PRODUCTION_DATABASE_URL']  # explicit — not the ENVIRONMENT-resolved one
eng = sa.create_engine(url, connect_args={
    'sslmode': 'require', 'connect_timeout': 10,
    'options': '-c statement_timeout=30000 -c default_transaction_read_only=on',
})
```

Run with the repo venv: `.venv/bin/python`.

## 4. What to pull

For a job number `N`:

- **Releases** — `stage`, `stage_group`, `start_install`, `start_install_asap`,
  `comp_eta`, `ship_date`, `fab_order`, `install_hrs`, `num_guys`, `job_comp`,
  `invoiced`, `is_archived`, `notes`. Include inactive/archived (`WHERE job=N`, no
  `is_active` filter) so nothing hides.
- **DRR submittals** — `WHERE project_number='N' AND type='Drafting Release Review'`,
  select `title, rel, status, submittal_drafting_status, ball_in_court, due_date,
  start_install, created_at, last_updated`. **The one(s) still `Open`/`STARTED` are
  your not-yet-released scopes.**
- **GC-approval submittals** — same filter with `type='Submittal for GC  Approval'`
  (note the double space in the stored value). `Open` = still waiting on the GC;
  check `ball_in_court` — sometimes it's sitting in *our* court.
- **Event timelines** (optional, for "is it actually moving?") — `ReleaseEvents`
  / `SubmittalEvents` by `job`+`release` / `submittal_id`, ordered by `created_at`.
  Join `users` for who did what. `upload_drawing` / `save_drawing_version` events
  reveal drawing revisions; absence of `update_stage` events = no fab progress.

## 5. Gap signals to look for

Match each GC lookahead activity to its scope, then flag:

| Signal | Where | Means |
|---|---|---|
| **`fab_order = 80.555`** on a released item | `Releases.fab_order` | Placeholder default (`DEFAULT_FAB_ORDER`) — **never sequenced into the shop queue**, even if plates/drawings are ready. |
| DRR still `Open` / `STARTED` | `Submittals` | Scope **not yet released**; check its `created_at` vs its siblings and `last_updated` for staleness. |
| DRR with **no `start_install` / `due_date`** | `Submittals` | Nothing scheduling it — won't be prioritized against a GC need date. |
| Release `start_install` **later than** the GC's need date | vs lookahead | Our green date slips the site. |
| Queue **inversion** | compare `fab_order` vs need dates | A later-needed release queued ahead of an earlier-needed one. |
| Combined-scope release | `description` spans buildings (e.g. "Bld B-D …") | See §6 — a "missing" scope may be **combined**, not missing. |
| Drawing revised (`save_drawing_version`) | `ReleaseEvents` | Confirm the shop is building to the latest version. |

## 6. The "combine" gotcha — don't false-alarm

The shop **combines near-identical scopes into one submittal/release to cut Brain
bloat.** A building that appears to lack its own release is *not automatically a
gap* — it may be riding on a combined record. Precedent: Alta Metro's "Bld B-D
Structural Embeds" is a single release covering three buildings.

So when a scope looks missing or is being drafted separately from a near-twin,
**frame it as a question to the PM/Bill** ("is D identical to B — combine, or
intentionally separate?") rather than a schedule-miss alarm. Verify combine intent
before flagging.

## 7. Worked example — Alta Metro (job 560), snapshot 7/20/26

*Illustrative only — these numbers are a point-in-time snapshot, not living status.*

- Scope = structural steel + embeds, Buildings A–D. GC = Wood Partners.
- **Done/installed:** Bld A embeds (459), B-D embeds (526, *combined*), A columns &
  beams (524), base-plate fix (910). All FC submittals Closed.
- **In fab:** Bld C steel (923) — green date 7/24 but `fab_order = 80.555`
  (**not queued**); Bld B steel (941) — 8/28, queued (`fab_order = 26`), drawing at v2.
- **Still in DRR:** Bld D steel (944) — `Open`/`STARTED`, no dates, GC-approval
  already Closed. The *only* steel package not yet released, yet the GC needs it
  (8/4) **earlier** than B (8/28).
- **Gaps surfaced:** (1) sequence 923 into the fab queue; (2) push 944 through DRR
  with dates — *or* confirm it combines with B per §6; (3) confirm shop builds 941 v2.

---

**Related:** the `Config.FAB_ORDER_FIELD_ID` / `renumber_fabrication.py` machinery
owns `fab_order`; DRR→release date transfer runs through `PendingStartInstall` at
release creation (see the `Submittals.start_install` comment in `app/models.py`).
