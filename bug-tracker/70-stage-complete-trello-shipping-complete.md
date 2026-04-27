# #70 — Stage Complete moves Trello to Shipping Complete (real fix: rank-gated bidirectional sync)

**Source:** Board item #70 (open / urgent / Job Log)
**Author:** Daniel — 2026-04-21
**Description:** "When moving a release to stage complete on the Job Log, we want to ensure this moves to Shipping Complete."

---

## Reframing — what the real bug is

Originally read as a forward-mapping issue. The mapping exists in `list_mapper.py:83`. The actual bug is the **round-trip clobber**:

1. User sets DB `stage = Complete` in the Job Log.
2. Trello card ends up on "Shipping completed".
3. Trello fires a webhook back at us with the new list.
4. Our inbound handler **unconditionally rewrites `job.stage` from the Trello list name**, replacing `Complete` with the literal `Shipping completed`.
5. User's edit is silently undone.

The same loop affects every DB stage that's finer-grained than its Trello list zone (Welded QC, Paint Start, Hold, etc., which all share Trello list "Fit Up Complete.").

## The insight that simplifies everything

Both DB stages and Trello lists are **ordered positions on the release lifecycle**. Trello lists are coarser zones than DB stages (many DB stages share one list). The forward map satisfies the invariant:

> **`rank(db_stage) ≥ rank(forward_map(db_stage))`** for every DB stage.

If we adopt **"only apply inbound when `rank(db_stage) < rank(inbound_list)`"** as the universal rule, the clobber bug, echo loops, skip-aheads, and backward-drag concerns *all collapse to the same check*. No echo table, no provenance plumbing, no member-ID gate.

## Confirmed policy decisions (Daniel, 2026-04-26)

1. **Hold** — moving DB to Hold leaves the Trello card wherever it was. Trello drags on a Hold release are ignored. Only Brain can transition out of Hold.
2. **Backward drags on Trello are blocked.** Rollbacks happen in Brain. Trello drags can only advance.
3. **Canonical DB stage = Trello list name** where they overlap (e.g., `"Fit Up Complete."` with the dot is canonical for both).
4. **Skip-ahead is fine.** Brain can jump from DB Cut Complete → Welded QC; the Trello card moves to "Fit Up Complete." (the correct zone), and DB retains the finer-grained Welded QC.
5. **No backfill of existing divergent rows.** Future webhooks won't reconcile drift; that's acceptable for now.

---

## Implementation

### 1. `STAGE_PROGRESSION_RANK` in `app/api/helpers.py`

Single source of truth for "how far along is this stage / list in the lifecycle."

```python
STAGE_PROGRESSION_RANK = {
    "Released": 0,
    "Material Ordered": 1,
    "Cut start": 2,
    "Cut Complete": 3,
    "Fitup Start": 4,
    "Fitup Complete": 5, "Fit Up Complete.": 5,
    "Weld Start": 6,
    "Weld Complete": 7,
    "Welded QC": 9,
    "Paint Start": 10,
    "Paint Complete": 11, "Paint complete": 11,
    "Store at Shop": 12, "Store at MHMW for shipping": 12,
    "Shipping Planning": 13, "Shipping planning": 13,
    "Shipping Complete": 14, "Shipping completed": 14,
    "Complete": 15,
    "Hold": 99,   # sentinel — Hold blocks all inbound; only Brain transitions out
}
```

Variants share a rank so `Fit Up Complete.` and `Fitup Complete` resolve identically.

### 2. Derived `TRELLO_LIST_RANK`

Computed once at module import from `STAGE_PROGRESSION_RANK` and the existing `STAGE_TO_LIST` forward map:

```python
TRELLO_LIST_RANK = {
    list_name: min(
        STAGE_PROGRESSION_RANK[s]
        for s, target in STAGE_TO_LIST.items()
        if target == list_name and s in STAGE_PROGRESSION_RANK
    )
    for list_name in VALID_TRELLO_LISTS
}
```

Each Trello list's rank = the lower bound of its zone (the earliest DB stage whose forward-map is this list). Adding a new stage updates the rank table automatically.

### 3. Replace `apply_trello_list_to_db` body (`app/trello/list_mapper.py:189`)

Before the existing `job.stage = trello_list_name`, insert the rank gate:

```python
db_rank = STAGE_PROGRESSION_RANK.get(job.stage, -1)
trello_rank = TRELLO_LIST_RANK[trello_list_name]

if db_rank >= trello_rank:
    logger.info(
        "Inbound Trello move skipped — DB progression at or ahead of Trello zone",
        operation_id=operation_id, job_id=job.id,
        db_stage=job.stage, db_rank=db_rank,
        trello_list=trello_list_name, trello_rank=trello_rank,
    )
    return

# DB is behind — Trello has advanced. Catch up.
job.stage = trello_list_name
job.stage_group = get_stage_group_from_stage(trello_list_name)
```

The existing `job.stage = trello_list_name` is preserved as the apply path; canonical DB stage names match Trello list names per policy decision #3.

### 4. Outbound gate fix (`app/brain/job_log/features/stage/command.py:198`)

Replace the broken `is_milestone_stage = self.stage in VALID_TRELLO_LISTS` check with the target-list-differs rule, plus the Hold guard:

```python
# Hold is a pause — never push to Trello. Card stays wherever it was.
if self.stage == "Hold":
    should_push = False
else:
    target_list = TrelloListMapper.STAGE_TO_LIST.get(self.stage)
    should_push = (
        target_list is not None
        and target_list != job_record.trello_list_name
    )
```

This makes DB-driven `Complete` actually push (forward-maps to "Shipping completed", which differs from any current list except itself), preserves the anti-bounce intent for sub-stage changes that don't move the card's list, and makes Hold a true pause.

---

## Why this is leakproof

- **Echoes are mathematically impossible to apply.** By construction of the forward map, `rank(forward_map(db_stage)) ≤ rank(db_stage)`. So any echo arrives with `inbound_rank ≤ db_rank` → gate skips. No echo table needed.
- **Concurrent edits resolve cleanly.** Postgres MVCC ensures the webhook handler reads committed DB state. The rank rule is a pure function of two integers — order-independent and replay-safe.
- **Backward Trello drags blocked.** Inbound rank < DB rank → skip.
- **Hold is sticky.** Sentinel rank 99 blocks all inbound; outbound guard prevents card movement.
- **Skip-ahead works.** Brain can jump DB stage; the Trello card lands in the right *zone*, DB retains the finer-grained stage.
- **No new infrastructure.** No table, no sweep job, no API call to fetch action IDs, no service account, no env var. One constant + one rank lookup + one inequality.

## Test plan

### Inbound rank gate

- [ ] DB Welded QC (rank 9), webhook "Fit Up Complete." (rank 4) → skip.
- [ ] DB Cut Complete (rank 3), webhook "Paint complete" (rank 11) → apply, DB updates.
- [ ] DB Welded QC (rank 9), webhook "Released" (rank 0) → skip (backward drag blocked).
- [ ] DB Hold (rank 99), webhook "Paint complete" (rank 11) → skip (Hold sticky).
- [ ] DB null / empty (rank -1), webhook "Released" (rank 0) → apply, seeds.
- [ ] Unknown Trello list → existing `VALID_TRELLO_LISTS` guard rejects, behavior unchanged.

### Outbound Hold guard

- [ ] Brain: stage X → Hold → no outbox row created; card untouched.
- [ ] Brain: Hold → Welded QC → outbox push to "Fit Up Complete.".
- [ ] Brain: Welded QC (card on "Fit Up Complete.") → Paint complete → outbox push to "Paint complete".

### Outbound target-list-differs

- [ ] Brain: stage Complete → outbox push to "Shipping completed".
- [ ] Brain: Paint Start when card on "Fit Up Complete." → no push (target == current).
- [ ] Brain: Store at Shop → outbox push to "Store at MHMW for shipping".

### End-to-end

- [ ] Brain: Welded QC → outbox pushes "Fit Up Complete." → webhook returns → rank gate skips → DB stays Welded QC. **Loop broken.**
- [ ] Brain: Complete → outbox pushes "Shipping completed" → webhook returns → rank gate skips (15 ≥ 14) → DB stays Complete. **Loop broken.**
- [ ] User drags Trello forward (Welded QC card → "Paint complete") → DB advances to "Paint complete".
- [ ] User drags Trello backward (Paint complete card → "Released") → DB unchanged; skip log emitted.
- [ ] User drags Hold release on Trello → DB unchanged; skip log emitted.

## Out of scope

- Backfill of currently-divergent rows (Daniel: not now).
- Echo provenance / action-ID table / member-ID gate / service account — all replaced by the rank gate.
- Reconciliation job to detect long-tail drift.

## Risks

- **Hold rank chosen as 99.** Any rank above the highest real progression value (15) works. 99 is forgiving headroom in case new stages get added later between Complete and the sentinel.
- **Trello list rank derivation depends on `STAGE_TO_LIST` being complete.** If a new DB stage is added without updating `STAGE_TO_LIST`, the new stage gets a default `STAGE_TO_LIST.get(...) = None` and falls into the existing skip-push branch. Safe failure mode.
- **Backward-drag policy is enforced silently.** Users who drag a card backward on Trello won't see DB change and may not know why. If this becomes a confusion vector, surface a notification or admin alert. Not in v1.
- **No reconciliation.** Existing drift in prod is not fixed. Acceptable per #5 above; revisit if drift causes user-visible issues.
