# #62 — Pause sorting button for Review / Production meeting — PULLED

**Source:** Board item #62 (in_progress / high / Job Log)
**Author:** Bill — 2026-04-20
**Description:** "Can we pause sorting with a button for review during the Production meeting. This way things don't move until we click to authorize a resort. Set a timer on the button say 1 hour. The doc will resort..."

---

## Status: PULLED — superseded by stash session (#75)

**Decision (2026-04-26):** Bill confirmed after testing the stash session implementation that a separate pause-sort feature is unnecessary. The stash session accomplishes the same workflow goal.

## Why the stash session covers it

Bill's intent in #62: during a Production meeting, edits shouldn't reshuffle the visible row order until he authorizes it.

How the stash session (#75) satisfies this:

- An admin starts a **Review stash session** in Review mode (`Start Review Session` button, `JobLog.jsx:952`).
- Subsequent edits to stage / fab_order / notes / start_install / job_comp / invoiced are **queued server-side** rather than applied to the live row (`JobsTableRow.jsx:407, 473, 521, 566, 617, 650, 705`).
- Because queued edits don't update the underlying values, **no resort fires** during the meeting.
- The admin reviews queued changes via `Stop & Preview`, then either applies them as a batch or discards.

The "click to authorize a resort" semantic Bill described maps directly onto "Stop & Preview → Apply" in the stash flow.

## What was built

No standalone pause-sort feature was implemented. The work that addressed Bill's underlying need is the stash session (PR #146 — `stash-review-changes`). That stays.

## What needs to be done

1. **Code:** Nothing to remove. The stash session is independent and remains in production.
2. **Board:** Close the in_progress #62 item with a note pointing at #75 / the stash session as the resolution.
3. **Documentation:** This file flags the decision.

## Out of scope

- Building a separate sort-freeze toggle on top of the stash session. If a future need emerges for "edits apply live, but visual order is frozen" (different semantic from stash), that's a new ticket.

## Notes for future-you

If you find yourself thinking about resurrecting a pause-sort feature, first re-read this file and confirm the intent isn't already covered by the stash session. The two features look superficially similar but solve different shapes of the same workflow problem; Bill's needed shape was the stash one.
