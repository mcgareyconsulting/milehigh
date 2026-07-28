# Submittal status drift — findings and remediation

**Scanned:** 2026-07-28, read-only, against production.
**Trigger:** client reported the Drafting Work Load showing submittals as Open
that were already closed in Procore.
**Verdict:** confirmed, and larger than the two rows reported — but it is a
*historical backlog that has stopped growing*, not an active leak.

Reproduce any figure below with `scripts/reconcile_status_drift.py` (dry-run is
the default and touches nothing).

---

## 1. Headline numbers

| Measure | Count |
|---|---|
| DB rows with `status='Open'` at scan time | 249 |
| …of those, **Closed in Procore** (stale) | **131** (53%) |
| …genuinely in sync | 117 |
| Ball-in-court-only drift among still-open rows | 0 |
| Rows unscannable (missing `procore_project_id`) | 1 (`65206107`) |

**Every single drift is the same shape: `Open` → `Closed`.** No other status
transition drifted in either direction.

### The reverse direction is clean

A second scan walked **all 46 Procore projects / 3,892 submittals** and compared
Procore's Open set against ours:

| Check | Result |
|---|---|
| Open in Procore, Closed in our DB | **0** |
| Open in Procore, missing from our DB entirely | **0** |

This is the reassuring half. **No work has silently dropped out of anyone's
queue.** The failure mode is strictly *"we missed a close,"* never *"we lost a
job."* Drafters may see finished work they should ignore; they will not have
live work hidden from them.

---

## 2. The drift stopped in May

Of the 130 stale rows still outstanding, sorted by when Procore actually closed
them:

| Age of the missed close | Stale rows |
|---|---|
| Under 30 days | **0** |
| 30–90 days | 25 |
| 90–180 days | 54 |
| Over 180 days | 51 |

- Oldest missed close: **2025-12-15**
- Newest missed close: **2026-05-22**

**Nothing closed in Procore after 2026-05-22 is stale.** Close events have been
landing correctly for roughly nine weeks. That reframes the problem: this is a
backlog to be cleared once, not a bug to be chased. Whatever broke the webhook
path appears to have been fixed sometime around late May.

> **Before running the cleanup, re-run the dry-run scan.** If the newest
> `closed_at` has moved past 2026-05-22, the leak has reopened and the fix
> belongs in the webhook path first — clearing the backlog would just mask it.

---

## 3. Blast radius is small

Order slots are what actually distort the DWL. Only **two** stale rows still
hold one:

| Job | Submittal | Drafter | Order held |
|---|---|---|---|
| 480 | `67501266` — Structural Steel Beams Area 3 | Gary Almeida | 5.0 |
| 560 | `68843528` — Loose Lintels | Bill O'Neill | 0.7 |

Plus `68843525` ("Cabanas", job 560, Gary Almeida, order 0.9), which is stale
and holds slot 0.9.

The other ~127 have `order_number = NULL`. They are clutter in the Open list —
visually noisy, not queue-blocking.

### Concentration

| Ball-in-court | Stale rows |
|---|---|
| Dalton Rauer | 83 |
| Colton Arendt | 33 |
| Gary Almeida | 5 |
| Rourke Alvarado | 3 |
| Rich Losasso | 2 |
| Danny Riddell | 2 |
| David Servold | 1 |
| Bill O'Neill | 1 |

Two drafters carry 116 of 130. Worth checking whether their queues share a
Procore project or notification path that the others don't.

### By job

| Job | Stale | Job | Stale | Job | Stale |
|---|---|---|---|---|---|
| 440 | 22 | 340 | 5 | 510 | 2 |
| 170 | 18 | 480 | 5 | 610 | 2 |
| 410 | 11 | 190 | 4 | 900 | 2 |
| 330 | 8 | 320 | 4 | 290 | 1 |
| 450 | 8 | 380 | 4 | 470 | 1 |
| 500 | 7 | 390 | 3 | 490 | 1 |
| 370 | 6 | 550 | 3 | 530 | 1 |
| | | 560 | 3 | 545 | 1 |
| | | 999 | 3 | 590 | 1 |

---

## 4. What was already fixed

One row was reconciled on 2026-07-28 — the one the client pointed at directly:

**`62145570`, job 380 Marshall Pointe, "Garage - Roof Canopy"**

| Field | Before | After |
|---|---|---|
| `status` | `Open` | `Closed` |
| `ball_in_court` | `Gary Almeida` | `Brian Panning, Gary Almeida, David Servold` |
| `order_number` | `None` | `None` (unchanged) |

Procore had closed it **2026-03-24** — stale for over four months. A
`SubmittalEvents` row was written with `backfill: True` and reason
`"reconcile_status_drift: Procore is source of truth"`, tagged `source=Brain`
so it reads as a correction rather than a Procore echo. Compress was suppressed,
so no drafter queue was renumbered.

Command used:

```bash
ENVIRONMENT=production .venv/bin/python -m scripts.reconcile_status_drift \
  --only 62145570 --no-compress --apply
```

### The second reported row was a false alarm

`73364625` (job 560, "Building B Structural Steel") was **already Closed** in the
DB — closed correctly by a Procore webhook on 2026-07-08. The client's screenshot
predated that. Nothing to fix.

---

## 5. Remediation — the run to schedule

The remaining 130 clear in one pass:

```bash
# Always dry-run first — confirm the count and that closed_at still tops out in May.
ENVIRONMENT=production .venv/bin/python -m scripts.reconcile_status_drift \
  --report /tmp/status_reconcile.json

# Then commit.
ENVIRONMENT=production .venv/bin/python -m scripts.reconcile_status_drift --apply
```

For each drifted row the script sets `status` to Procore's value, clears
`order_number` when the row leaves Open (freeing the DWL slot, same rule as
`check_and_update_submittal`), syncs `ball_in_court` when it also drifted, and
writes a `backfill: True` `SubmittalEvents` row.

**Drop `--no-compress` on the full run.** Compress renumbers each affected
drafter's remaining Open queue — urgency 0.1–0.9 packed to the high end, regular
renumbered 1..N preserving order, identical math to the DWL "Resort" button.
Doing that *once, after every slot is freed* is correct. Doing it per-row (as a
`--only` run would) shuffles a drafter's queue under them for no benefit, which
is why the single-row fix above suppressed it.

Expected compress effects, from the 2026-07-28 dry-run:

- **Gary Almeida** — urgency 0.5–0.8 → 0.6–0.9; regular 8, 9 → 2, 3
- **Colton Arendt** — 5, 7, 8, 9, 10… → 2, 3, 4, 5, 6…
- **Danny Riddell** — urgency 0.2–0.9 → 0.1–0.8; regular 3, 4, 7, 8, 19, 22, 33… → 2, 3, 4, 5, 6, 7, 8…
- **Rourke Alvarado** — 5, 6, 7 → 1, 2, 3
- Dalton Rauer, David Servold, Rich Losasso, Bill O'Neill — single-row shifts

Tell the affected drafters before running it. Their queue positions will move.

### Script flags added 2026-07-28

- `--only ID[,ID…]` — scan and reconcile named submittals only
- `--no-compress` — close and clear without renumbering any queue

---

## 6. Follow-ups this surfaced

1. **Root cause is unconfirmed.** We know close events stopped being missed
   around 2026-05-22; we do not know what fixed it. Until that is understood,
   the leak could reopen silently. Worth a look at webhook delivery history
   (`get_webhook_deliveries`) over Dec 2025 – May 2026.

2. **There is no drift alarm.** This was found because a client noticed. A
   periodic read-only scan emitting a count would have caught it in December.
   The dry-run path is cheap and already written.

3. **`65206107` has no `procore_project_id`** and cannot be scanned at all.
   Needs manual attention.

4. **Audit-log divergence, separate issue.** `72974122` (job 560) has
   `last_updated = 2026-07-08 19:59` but no `SubmittalEvents` row newer than
   2026-07-07 — the row was updated without an event being written. The row
   value is correct; the event stream under-records. This matches the known
   Procore event-divergence behaviour under rapid BIC re-flips and is *not* part
   of the status drift above.
