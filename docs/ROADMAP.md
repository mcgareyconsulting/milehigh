---
project: MHMW
updated: 2026-09-16
verified: origin/main @ e6719b1 (PR #383 splice modal v2)
config:                       # inputs to derived math — store inputs, never results
  horizon:
    - 2027-10 Procore absolute dead date (renewed 2026-08-15)
  effort_midpoints: {S: 0.5, M: 3, L: 7.5, XL: 15}
classes:                      # what KIND of work an item is — orthogonal to effort
  fix: discrete, shippable, no client sign-off needed
  audit: document current → agree target with client → change
  build: structural, multi-week
  lane: ongoing, never "done"
  deferred: off the active path, with a stated re-check trigger
queue:                        # agent-maintained, set by agreement in session
  now: [BUG-24, BUG-25, BUG-26, T11]
                        # 2026-09-16: order unchanged. The 9/16 session answered the two rulings
                        # BUG-24/25 were waiting on (hand-adjusted bars; mirror keeps start+due)
                        # and REVERSED Open question 5 — default crew back to 2 (PR #381).
                        # 2026-09-15: BUG-27 complete (ASAP kept through Ship Complete) and off
                        # the queue. BUG-24 awaits the hand-shortened bars ruling; BUG-25 awaits
                        # Bill's date confirmation (expected 2026-09-16).
                        # 2026-09-14: Bill's weekly request package (thisweek-2026-09-14) takes
                        # the front — Daniel: "probably these elevate to highest urgency". Its own
                        # P0 pair leads: schedule integrity (BUG-24..27, filed as fixes — each is
                        # small and measured against code this session) and the Release Issue
                        # Register (T11). Package P1–P3 sit at the head of next in the package's
                        # order. AUD2 steps back to next, NOT dropped — its measurement is done and
                        # its change step was already waiting on Bill's ruleset confirm.
                        # Previous now, retained for the trail:
  # now (2026-09-05): [AUD2]  # set in session by Daniel — "build now". The release-number
                        # ruleset (AUD2) and the tagged hours-released prompt (N16) took the front;
                        # N16 was built the same day, so only AUD2 is left standing here.
                        # T1 drops to next with its core shipped (PR #361/#366) and its 2026-09-02
                        # scope unlanded. First time since 2026-08-15 that W5 is not queue.now —
                        # a deliberate pause on the front lane, not a re-ranking of it.
  next: [T12, T13, T9, N19, T14, AUD2, T1, N9, T2, AUD1]
                        # 2026-09-16 (late): T9 keeps its slot — the 9/16 splice modal spec shipped
                        # (PR #383), but outcome (c) punch mirror is still unbuilt.
                        # 2026-09-16: N19 home page added (un-parks D2) — Daniel: "elevating home
                        # page behavior". Placed behind the three items the 9/16 session re-specified
                        # (T12 Ready-to-Ship column, T13 QC gate, T9 splice modal), ahead of T14.
                        # 2026-09-14: T12 release flow → T13 photo evidence gate → T9 splicing →
                        # T14 iPad parity is the package's own P1→P3 order. T1 keeps its place
                        # behind them but most of the package IS T1's surface (Timeline), so T1's
                        # open 2026-09-02 defects get picked up where they overlap (weekend drop →
                        # BUG-26). N9 sits behind T13 deliberately: the gate captures the photos,
                        # the stamp makes them self-describing — build the capture path once.
  # next (2026-09-05): [T1, N9, T2, AUD1]  # 2026-08-21: N9 elevated by Bill ("short timeline"); A1 deliberately stalled behind T1 [bill-2026-08-21#L169]
                        # 2026-08-29: N9 unblocked (Open question 3 answered) — order unchanged. Its
                        # individual-logins answer needs accounts, which T2 makes self-serve, but Daniel
                        # can create them by hand today, so N9 does not move behind T2.
  awaiting: [N11]
                        # 2026-09-02: session reordered NOTHING. T1 stays now — the meeting was a
                        # live timeline demo that closed T1's open design questions (date model,
                        # drop behavior, ordering, lanes). Bill's stated "next real big push" is sub
                        # access = T3, which carries deps T2 — so T2 already sitting in next is the
                        # correct chain, not a coincidence. [bill-2026-09-02#L912]
                        # 2026-09-05: reordered. Both new front items are small and were measured
                        # against live data this session before being queued — AUD2's allocator is
                        # already stuck in gap-fill mode, and N16's tool exists but is locked to
                        # Mon–Sun weeks. Neither needs Bill before it starts; both need him before
                        # they finish (AUD2's ruleset confirm, N16's untagged-backlog call).
---

# MHMW · ROADMAP

**Status authority for the MHMW Brain.** Canonical path: `docs/ROADMAP.md`.
This file supersedes `docs/roadmap-2026-08-06.md` (the 2026-08-06 prose
roadmap — renamed from `docs/roadmap.md` on 2026-08-10 when this file took the
canonical name) and `docs/feature-catalog.md`; both are retained for reasoning
only — all state changes land here.
`docs/procore-decommission-plan.md` holds the Workstream 1 data model and slice
detail; Bill's written spec
(`MHMW_Brain_Procore_Decommission_Submittal_System_Developer_Handoff.md`) is his
deliverable, not a repo artifact. Its W5 counterpart — the Trello-replacement /
field-ops spec
(`MHMW_Brain_Trello_Replacement_Subcontractor_Field_Operations_Build_Package.md`,
delivered 2026-08-20) — is likewise a deliverable kept outside the repo; see the
Sources table. Procore integration teardown (webhooks, outbox,
`fc_retry_worker`) is tracked on a separate map, not here.

**Tier key.** Tier numbers are stable identifiers, **not** priority order —
priority is the order-of-work line below. W5 was added 2026-08-15; W1 was
deferred the same day.

| Tier | Workstream |
|---|---|
| W0 | Preconditions — everything else sits on these |
| W1 | Procore exit — **deferred 2026-08-15**; horizon moved to Oct 2027 |
| W2 | Money — ongoing cost lane, sits behind W5 |
| W3 | Daily use — the tool everyone is in; fixes and audits live here |
| W4 | Carmen |
| W5 | **Trello exit — the front lane** (added 2026-08-15) |

**Order of work as of 2026-08-15:** W5 → W3 (fixes, then audits) → W2 → W0 → W1 deferred.

**Class key.** Every item carries a class in its status line (`config.classes`):
**fix** (discrete, shippable, no sign-off) · **audit** (document current → agree
target with client → change) · **build** (structural, multi-week) · **lane**
(ongoing) · **deferred**. Class says what *kind* of work it is; effort says how
big. They are independent — a fix can be L, a build can be S.

---

## 🔧 Fix queue — pick-up-and-go

Small, self-contained, no client sign-off. Entry points included so a session can
start cold (phone included) without exploring first.

**Queue cleared 2026-08-15** (branch `claude/roadmap-review-bugs-uinik2`).
BUG-10's config half landed the same day and **elevated A1**.
**Re-stocked 2026-08-21** from the pre-Alaska standup (BUG-11 through BUG-15);
BUG-15 and BUG-12 both shipped the same day. **Re-stocked again 2026-08-29**
from Daniel's own list (BUG-16 through BUG-18).

**BUG-16, BUG-18 and BUG-11 all built 2026-08-29** (branch
`claude/bug-16-18-fixes-eqqca9`; the branch name predates BUG-11 joining it).
**BUG-20 built 2026-09-03** (branch `fix/asap-behavior`) — the ASAP half of the
date rules, Bill's 2026-09-02 ask and a direct follow-on to BUG-11. **BUG-22
found by prod audit and half-built the same day** on the same branch; **BUG-23
opened 2026-09-04** by the audit of that fix. Note the numbering: this branch
filed its items as 19/20/21 before `main` had independently taken those IDs
(PR #363) — they were renumbered on merge, and BUG-20 is where the ASAP rework
landed because `main`'s BUG-20 was already the same request.


**Re-stocked 2026-09-02** from the 9/2 session: BUG-19 (DWL unnumbered returns — active data loss) and BUG-20 (ASAP shows a date). **BUG-17's re-check trigger fired the same day.**

**BUG-21 added 2026-09-04** — Daniel, from live use; not from the 9/2 session.

**BUG-19 built 2026-09-03** (`feature/dwl-bounce-back`, PR #360) — filed 9/2, shipped
9/3, the fastest turn the queue has had.

**Open as of 2026-09-04:** BUG-23 (med — stage-cascade debt, its own branch) and
nothing else. **BUG-13 and BUG-14 were dropped 2026-09-04** (Daniel) — both are
low, neither is reproducible from this desk, and both re-enter the queue the
moment someone hits them again. **BUG-19, BUG-20, BUG-21 and BUG-22 all came off
this list 2026-09-03/04** — BUG-19 on `feature/dwl-bounce-back`, BUG-20/BUG-22 on
`fix/asap-behavior`, BUG-21 on `fix/timeline-zoom-anchor`.

**BUG-23 was re-checked against `main` on 2026-09-04 and is still open** — it was
filed *by* the audit of the ASAP work, so the ASAP work does not close it; the one
finding that could have ridden along was deliberately pulled back out (`e10feee`).
~~**BUG-17 is parked** (Daniel, 2026-08-29) and is not part of this pass.~~ **BUG-17 unparked and half-built 2026-09-04** (PR #369) — the two-column to-dos/mentions page shipped; only the editability half is still open. **Open as of 2026-09-05: BUG-23 and BUG-17's remainder.**

**Re-stocked 2026-09-14** from Bill's weekly request package
(`thisweek-2026-09-14`, §4 "P0 — Schedule integrity"): **BUG-24 through BUG-27**,
all `queue.now`. The package's framing is the reason they outrank everything else:
*"so the team does not continue operating two schedules that disagree"* [§2].
Each was checked against `main` @ 1c3d09a before filing, and **two of the four
are not what they sound like** — the installer count was never a Brain control to
restore (BUG-24), and the Trello date bug is on the mirror card, not the primary
(BUG-25).

**Re-stocked 2026-09-16** from the 9/16 shop session (Bill, Louie): **BUG-28** PDF
modal empty-load, **BUG-29** issue mentions missing from to-dos, **BUG-30** verbal
release job picker (Daniel's notes), **BUG-31** Timeline card text. The same session
**answered BUG-24's and BUG-25's pending rulings** and reversed BUG-24's default crew
back to 2 (PR #381).

**BUG-32 filed and built 2026-09-18** — Bill, from live use of the shipped splice
modal: spliced install hours netted out only in the Splices tab, so the Job Log, the
release modal and Subs → Invoice Paid each showed a spliced release at its gross pool
and the sub budget billed the same hours twice.

| ID | Fix | Entry point | Pri |
|---|---|---|---|
| BUG-24 | **2026-09-16 [bill-2026-09-16#L967–L1112]: DEFAULT REVERSED TO 2** (*"three is the wrong number, it should be two"*), no backfill — PR #381. **Hand-adjust ruling given:** a Timeline edge-drag keeps `start_install` fixed, moves `comp_eta` and syncs Trello, and does **not** recompute hours/guys; hand-adjusted releases must be listable and the bar marked (diagonal hatching). Whether a later crew edit overwrites a hand-adjusted `comp_eta` was not asked directly — read the ruling as *hand adjustment wins*. **BUILT 2026-09-15. Open question 5 answered the same day — default crew is 3 (24 labor-hrs/day). AWAITING one ruling: hand-shortened bar behavior — does a crew edit recompute over a Timeline edge-compressed `comp_eta` (current build: yes, it overwrites)? Existing rows saved at 2 deliberately NOT backfilled (2026-09-15); only edits and new cards get 3. The "default conflict, not decided" text below is historical.** **Installer count per release — a Brain control, not a restore** [thisweek-2026-09-14#§4.1]. Bill: the card-level control *"has disappeared and must be restored."* **Found in code: the Brain has never had a write path for `num_guys`.** It is read everywhere (`_comp_eta_effective`, `routes.py:488`; the hub footnote `JobDetailsBody.jsx:629`; the outbox mirror push `outbox_service.py:746`) but the only writer is **inbound Trello** — `sync.py:308` parses it out of the card *description* and `sync.py:164` re-pushes the mirror bar. The "control that disappeared" was a line in a Trello description, and it has been drifting out of sight as the crew moves to the Timeline. So this is: a scheduler-gated edit on the release hub / Timeline card → write `num_guys` → recompute `comp_eta` → `ReleaseEvents` row (Change Log) + undo → outbound description write so Trello stays consistent until T4. Sub users never see the control [§4.1 "No unauthorized exposure"]. **Default conflict, not decided — see Open question 5:** the package restates the baseline as **3 installers = 24 labor-hrs/day** (as did fieldops §5), but the code default is **2** in both halves (`DEFAULT_NUM_GUYS = 2`, `scheduling.js:25`, which says *"change both together"*; `num_guys or 2` server-side). Changing it moves every unset release's `comp_eta`. **Also collides with an open BUG-11 note:** a Timeline edge-compress writes `comp_eta` directly (2026-09-02), so "does a crew edit recompute over a compressed `comp_eta`?" now has to be answered to ship this | `app/brain/job_log/routes.py` (new PATCH beside the start-install one), `_comp_eta_effective` (`:488`); `frontend/src/utils/scheduling.js`, `JobDetailsBody.jsx:629`, `GanttChart.jsx`; Trello `set_num_guys_in_description` (`api.py:1789`) for the outbound write | **high — client P0** |
| BUG-25 | **2026-09-16 RULING [bill-2026-09-16#L854–L911]: the mirror card is EXEMPT — it keeps Start = `start_install` and Due = `comp_eta`, because collapsing Due onto start install kills the range bar. Primary cards stay Due-only. **Built 2026-09-16 (PR #381): `MIRROR_DUE_ONLY` and its point-push path REMOVED, not flipped** (Daniel: *"that path should not exist"*), together with the inbound writeback guard that only existed to support it. Mirror cards pushed as points since 196015c get their range back on the next outbound push.** **BUILT 2026-09-15 behind a one-line switch (`MIRROR_DUE_ONLY`) — AWAITING date confirmation from Bill, expected 2026-09-16 (is the mirror card Due-only too, or exempt as a range bar?).** **Brain → Trello dates: Start Install goes to the Trello Due Date only, never Start** [thisweek-2026-09-14#§4.2]. **Found in code: the primary card is already right; the mirror card is the offender.** The primary-card writers (`start_install/command.py:133`, `routes.py:3083`) push `new_due_date=start_install` and nothing else. But the **mirror-card range** push — `update_card_date_range(short_link, start_date, due_date)` (`api.py:2162`), called from `api.py:1619`, `api.py:2463` and `sync.py:209` — writes `start = start_install` **and** `due = comp_eta`. So Trello's Due on the mirror is the *completion* day, and the install day lands in Start — the exact inversion Bill describes. **Design tension to settle before the one-line fix:** the mirror card is a range bar *by design* (`project_mirror_cards_timeline`); "Due Date only" makes it a point on the install day and loses the duration in Trello. Read the rule as applying to every Brain-originated card write unless Bill says the mirror is exempt. **Calendar-day check:** `mountain_due_datetime` (`utils.py:213`) is documented as 6 pm but builds `time(6, 0)` = **6 am** Mountain — still the same calendar day in any US zone, so not the bug, but fix the docstring or the time while in there. **"No silent mismatch"** [§4.2] is net-new: a failed/mismatched push must be visible to an authorized user, not only logged — `TrelloOutbox` exhaustion already logs ERROR; it needs a surface. Leave inbound Trello behavior alone [§4.2 "Current inbound behavior"]. Dies with T4 — do not gold-plate | `app/trello/api.py` (`update_card_date_range` + its three callers), `app/trello/utils.py:213`; tests `tests/test_trello_stage_sync.py` neighborhood | **high — client P0, two schedules disagree** |
| BUG-26 | **BUILT 2026-09-15, all four asks.** **Weekends on the Timeline — dark, never auto-picked, manually allowed, bridged** [thisweek-2026-09-14#§4.3]. Today: weekend columns carry `bg-gray-200/40` (`GanttChart.jsx:1369`) — present but too faint to read as "dark". **Four asks:** (1) visibly darker weekend columns; (2) scheduling/duration math never *auto*-places a start on Sat/Sun; (3) an authorized scheduler **can** deliberately drop onto Sat/Sun; (4) a multi-day installer bar **bridges** the weekend as one continuous bar. Plus a guard: rendering never moves a hard date, projected date, ship date or capacity [§4.3 "No date corruption"]. **Absorbs T1's open 2026-09-02 defect** — *"install hours don't compute on a weekend drop"* [bill-2026-09-02#L471] — which is ask (3) failing today. Watch the N4 two-calendar split (business days vs calendar days) — a weekend drop must not get snapped forward by the business-day helpers | `frontend/src/components/GanttChart.jsx` (column build `:997`, column render `:1369`, bar packing), `frontend/src/utils/timelineDrop`, `utils/scheduling.js` (`installCompleteDate`) | **high — client P0** |
| BUG-27 | **COMPLETE 2026-09-15 — ASAP is kept through Ship Complete** (the drop rule moved to `Install Start` or later the same day; red now holds on both ship lanes). **ASAP red on Shipping Planning cards** [thisweek-2026-09-14#§4.4]. **Found in code:** the red/amber/green border (`TRAY_BORDER` / `trayDateState`, `GanttChart.jsx:371–400`) is applied **only in the Unassigned tray** — *"Dropped onto a lane it takes that lane's installer colour"* (`:376`). The ship lanes' only ASAP awareness is sort order (`:213–218`). So a rush release pulled into Shipping Planning loses its red the moment it arrives. Fix: ship-lane cards wear the ASAP treatment (red over the real hard date, per BUG-20 semantics), surviving drag, vertical reorder (T12), refresh and filters until the flag clears. ~~Rule interactions already settled and unchanged: ASAP drops at `Ship Complete` (`asap_drop.py`), so the red naturally disappears on the second ship lane~~ **Superseded 2026-09-15 (Daniel): ASAP persists through Ship Complete; `asap_drop.py` now fires at `Install Start` or later (stage change or Install Prog entry)** | `frontend/src/components/GanttChart.jsx` (ship-lane card render; reuse `classifyInstallDate`) | **high — client P0** |
| BUG-28 | **PDF modal intermittently loads empty** [bill-2026-09-16#L223–L232] — the drawing/PDF modal sometimes opens without its content; closing and reloading doesn't clear it, a right-click refresh of the frame does. Reads as a cache/stale-load issue. Tracked separately from the Issues tab it was seen near (Daniel, 2026-09-16) | PDF modal viewer (`fix/improved-pdf-modal` lineage) | med |
| BUG-29 | **An issue @mention doesn't reach the mentioned user's to-dos/mentions view** [bill-2026-09-16#L615–L631] — Zach was mentioned on a new issue; filtering the to-dos page by Zach showed nothing. Issue mentions feed the bell but not the BUG-17 two-column page | `app/brain/release_issues/`, to-dos/mentions page (PR #369) | med |
| BUG-30 | **Verbal release order: job picker** (Daniel's notes, 2026-09-16) — the job # / job name field tabs get a dropdown of existing jobs (# + name) that fills both fields on select | `/job-log/release` paste/verbal entry form | low |
| BUG-31 | **Timeline card text** [bill-2026-09-16#L1418–L1515] — drop the photo thumbnail and the PM initials from Timeline cards; job-release, name and description must be **fully visible (wrap, never truncate)**. Table keeps a camera icon for photos. Hover-to-see-cover-sheet was floated and **dropped** (Daniel's notes) | `frontend/src/components/GanttChart.jsx` card render | med |
| BUG-32 | ~~**Spliced install hours only net out in the Splices tab.** Bill, 2026-09-18, from live use: splice 50 hrs off a 150-hr release and the Splices tab reads *"100 of 150 remaining"*, but the Job Log, the release modal's Details pane and Subs → Invoice Paid all still show the original at **150** — and the splice's own row shows 50 beside it, so the group reads as 200 hrs of install work and Invoice Paid budgets $11,000 against $8,250 of actual scope. **Cause is by design and stays that way:** the parent keeps the WHOLE pool in `install_hrs` (subtracting on create would shrink the pool every time it was drawn on, and `install_pool` / `validate_field_edits` both measure against it), so the netting has to happen in the read paths, and only the `/splices` endpoint did it~~ **built 2026-09-18.** `splice_allocations` + `install_hours_view` (`features/splice/command.py`) are now the one definition of "what this release still installs itself", batched one query per page so no list view goes N+1, and every serializer carries `spliced_install_hrs` / `remaining_install_hrs` beside the untouched pool: both job-log feeds, `subs/service.py`, the field-edit PATCH response, and `install_schedule/service.py`'s `est_hours` (each splice is its own card with its own crew, so crew capacity was double-counting the pool too). Frontend reads them through one `utils/installHours.js` — Job Log cell (netted, with the pool in the tooltip and the ✂ marker), the row-edit modal (still edits the **pool**, and now says so), Details pane, Subs Invoice Paid + its CSV/PDF export (Budget and Est. Billable follow the netted hours, never the gross), the Splices tab's Original line, and the Job Log / Archive `Install HRS` KPI total. **One catch worth keeping in mind:** a splice never touches its parent's row, so the Job Log's `?since=` delta poll would never have re-sent the original — the cursor query now carries parents of changed splices along, or the fix would be invisible until a full reload. **Deliberately NOT changed:** the parent's stored `install_hrs`, its `comp_eta` (still derived from the gross pool — a spliced release's projected install window is now longer than its own hours imply, and wants a ruling), and Trello card content | `app/brain/job_log/features/splice/command.py`, `app/brain/job_log/routes.py` (both serializers + the cursor filter), `app/brain/subs/service.py`, `app/brain/install_schedule/service.py`, `scheduling/hours_summary.py`; `frontend/src/utils/installHours.js` (new), `JobsTableRow.jsx`, `JobDetailsBody.jsx`, `SplicesPane.jsx`, `pages/Subs.jsx`, `utils/subsInvoiceExport.js`, `hooks/useJobsFilters.js`; tests `tests/brain/test_splice_release.py::TestSplicedHoursNetOutEverywhere`, `tests/test_hours_summary.py`, `frontend/src/utils/installHours.test.js` | **high — billing reads double** |
| BUG-23 | **Stage-cascade debt, found by the 2026-09-04 audit of BUG-22 — not yet built.** Three findings, one shape. (1) **The inbound Trello list move skips N5's `apply_shipping_stage_date_discipline`** — it can set `Ship Planning` and `Ship Complete` (`list_mapper.py:118`), both `SHIPPING_STAGES`, so a formula-dated release dragged to "Shipping planning" keeps stale estimated dates that a Brain stage change would have blanked and locked. **This is the fourth instance of the bug class, on the very path BUG-20 just patched.** (2) **`update_invoiced` skips the ASAP drop** — `invoiced='X'` on a formula-dated ASAP row leaves the flag set, because that path gets its clear only as a side effect of the neutralize cascade, which no-ops without a hard date. The same asymmetry the job-comp `X` branch just had fixed, 50 lines away. (3) **`start_install_asap` is now cleared in three modules under three rules with three audit shapes** (`asap_drop.py`, `neutralize_install_date_cascade.py:113`, `shipping_stage_date_discipline.py:96`) — BUG-20 consolidated the *callers* but added a fourth *clearer*. Recommended shape: an `apply_stage_cascades(record, new_stage, ...)` owning the four stage-keyed cascades (ASAP drop, colour dump, fab re-tier, N5 discipline) that all four writers call, with the two writer-specific ones (job_comp complete-zone sync, Trello outbox push) deliberately excluded; then strip the flag write out of the other two clearers so `update_invoiced` closes by itself. **(4) The lookahead classifier has the install-schedule bug too** — `lookahead/pipeline.py:classify_install_date` returns `KIND_ASAP` off the flag alone, before the hard-date test, and `schedule_builder._install_source` maps `KIND_ASAP` to `SOURCE_HARD` — so an ASAP flag on a *projected* date reports an estimate as a commitment in the lookahead schedule. Fixed in `install_schedule/service.py` on the ASAP branch (where the same shape was newly introduced and affects live crew-conflict output); the lookahead half was **deliberately pulled back out of that PR 2026-09-04** (Daniel) — it is pre-existing behaviour in a module unrelated to ASAP, it affects zero prod rows today (all 5 live ASAP rows carry hard dates), and its existing test encodes the opposite contract, so it belongs with the rest of the classifier work rather than riding a merge-ready branch. **A SQLAlchemy attribute hook was considered and rejected** — three of four writers pass a `parent_event_id` only the caller knows, and it would fire on the eight ops/migration scripts that deliberately want raw writes. The risk is the test surface, not the code: five test files pin per-call-site behavior. Its own branch and review, not a rider | `app/trello/sync.py` (add the N5 call), `routes.py:1742` (`update_invoiced`), `features/stage/` (the orchestrator; the three rule modules also want moving there out of `features/start_install/`) | **medium — known debt, no live prod row yet** |
| BUG-22 | ~~A Trello card drag never drops the ASAP flag; nor does an Install Prog percentage~~ **both halves built — Trello 2026-09-03, Install Prog 2026-09-04.** Found by a read-only prod audit of the 5 live ASAP rows: `640-121` and `190-188` were both sitting at `Ship Complete` still flagged red. Cause — `asap_dropped_on_ship_complete` lived **inside** `UpdateStageCommand`, and that command is not the only writer that advances a stage. An inbound Trello list move writes the stage itself (`sync.py:604`) and emits its own `update_stage` event, so it skipped the drop entirely; since the shop advances work by dragging cards, that is the common path, and a finished release kept its red until someone cleared it in Brain by hand. Exactly the shape BUG-9 already patched here for `fab_order` and BUG-16 for the drafting status — so the fix is theirs too: the rule moved out to `features/start_install/asap_drop.py` and **both writers now call the one function**. Scoped deliberately to the ASAP drop: inbound lands on the **floor** of a list's zone (`list_mapper.py:282`), so "Shipping completed" floors at `Ship Complete` and no drag can reach `Install Start` or later — the colour dump is unreachable from this path and wiring it would be dead code. An integrity test asserts that disjointness, so a mapping change that opens the door fails the build instead of silently reopening the hole. **Third writer closed 2026-09-04:** the Install-Prog **percentage** branch of `update_job_comp` moved the stage to `Install Start` itself and ran neither cascade, while the `X` branch right below it had always called the colour one — the *later* state cleaned up and the *earlier* one did not. Backwards from BUG-11's own reasoning, too: a percentage typed into Install Prog is the most explicit "work began" statement in the system, and it was the one path that kept the row red (live prod row `190-917`, moved 08-31, i.e. after BUG-11 shipped). Both cascades now run there, guarded on the percentage rather than on whether the stage moved, so a release that reached `Install Start` by any other route is cleaned up the next time someone reports progress on it. **The `X` branch gained the flag-only drop as well:** its neutralize cascade clears ASAP only on a row that has a hard date and no-ops entirely on a formula-dated one, so a formula-dated rush row could reach `Install Complete` still red. Rare under BUG-19 (every ASAP row now has a hand-set date) but it is the asymmetry that breeds the next bug | `features/start_install/asap_drop.py` (new), `features/stage/command.py`, `app/trello/sync.py`, `routes.py` (both Install Prog branches); tests `tests/test_trello_stage_sync.py::TestInboundAsapDrop` + the Install Prog block in `tests/brain/test_install_start_color_dump.py` | **high — silent data drift** |
| BUG-21 | ~~**Timeline zoom loses your place.** Zooming in or out dumps the scroll position and lands at the **left end of the chart** — reported as "snaps to July 3rd", which is just wherever the leftmost column sits; nothing anchors to that date. **Mechanism:** the re-anchor at `GanttChart.jsx:853–866` derives the left-edge date from `el.scrollLeft / prevPx` inside a `useLayoutEffect` — which runs *after* React has already committed the new column width. On zoom-out the chart narrows, so the browser **clamps `scrollLeft` to the new smaller max before the effect reads it**, and the anchor math then runs on an already-corrupted value. Capturing pixels after the re-render cannot work. **Fix direction:** capture the anchor as a **date before the state change** — in `zoomIn`/`zoomOut` (~line 1038) or from a scroll-tracked ref — then restore `scrollLeft` from that date after render. **Scoped to zoom** (Daniel, 2026-09-04): restoring `viewStart`/`zoomIdx` across navigation is deliberately *not* in scope, though note neither persists today — only lane- and tray-collapse reach `localStorage`. **Worth a glance while in there:** `chartRange.firstDay` is documented as `mondayOf(...)` *"so week columns align"* (line 807), but the leftmost column read as a **Friday**; if the origin is not landing on a Monday, week alignment is independently wrong. Related to T1, which is active work on this surface~~ **built 2026-09-04** on `fix/timeline-zoom-anchor` — the anchor date is now captured in the zoom handler, before the state change, and the effect restores it; the px math stays as the fallback for width changes that are not zooms. The Monday question resolved as a non-issue: `mondayOf` is correct and `chartRange.firstDay` is a Monday — the Friday on screen was just where the corrupted scroll landed | `frontend/src/components/GanttChart.jsx` — zoom anchor `useLayoutEffect` (~853), `zoomIn`/`zoomOut` (~1038); test `GanttChart.zoom.test.jsx` | med |
| BUG-19 | ~~**DWL: an unnumbered item that gets returned is invisible.** A *numbered* item that bounces back jumps to the top of the drafter's list with a decimal; an item worked **without** a number is returned into the unnumbered bucket and nobody notices — *"they don't look at their unnumbered stuff"* [bill-2026-09-02#L1590]. **Colton has already missed work this way** [#L1594]~~ **built 2026-09-03** (PR #360). The promotion is a **second entry point**, not a loosened condition on the existing one: `UrgencyService.promote_group_return` runs the same urgency ladder as `bump_order_number_to_urgent` but accepts `order_number is None`, with the shared mechanics factored out to `_apply_ladder_bump` so the two cannot drift — deliberately the opposite shape to the copied-clause pattern that brought BUG-8/BUG-9/BUG-16 back. **Scoped to the multiple-assignees → single return** (Daniel, 2026-09-03): a single → single ball-in-court move is a drafter reassignment the engineering lead communicates directly, not a bounce-back, and must not jump the queue. The row arrives unnumbered because `check_and_update_submittal` clears `order_number` on the way *out* of 'Open' — so the bucket is where the pipeline puts it, not where a user left it | `app/brain/drafting_work_load/service.py` (`promote_group_return`, `_apply_ladder_bump`); caller `app/procore/procore.py:1253`; tests `tests/dwl/test_dwl_service.py` + `tests/procore/test_unnumbered_group_return.py` | **high — active data loss** |
| BUG-20 | ~~**ASAP drops its text and shows a real date.** Today the card reads "ASAP" [bill-2026-09-02#L732]. Bill's complaint: *"what's the point of bringing dates if we have ASAP… then the ASAP lands and then we don't know what the date is"* [#L1032]. Final behaviour (Daniel, 2026-09-02): **the entry point is unchanged — the user hits ASAP mode — but from there it behaves exactly like a hard date.** The user sets a date, the card shows that date, the cell renders **red**. "ASAP" as displayed text is dropped; red carries the urgency. Semantics: *"if we can get it faster [great], but this is the absolute drop-dead date"* [#L1043]. Touches N5/BUG-11's ASAP paths — read those notes first~~ **built 2026-09-03 on `fix/asap-behavior`.** ASAP is now a **rush flag over a hand-set hard date**: it paints the cell red, the user types the date, and the cell shows that date. `set_asap` writes the flag and the colour bit and nothing else — the date, `comp_eta`, the Trello due push and the scheduling recalc all belong to the user's own date save, which already did every one of them. **Four consequences, all built:** setting a hard date **no longer clears ASAP** (it used to, because the date was ASAP's to own — under the new rule that would cancel the flag one keystroke after setting it); the **ASAP date rewrite on entering the dump zone is deleted** along with the `install_started_on` plumbing (it existed only because the +1wk date was a placeholder — rewriting a hand-set date destroys a real commitment); **undo is flag-only**, with the legacy branch kept and tested so events that *did* stamp a date still roll it back; and the modal **refuses ASAP without a date** rather than disabling the date field. Daniel's call on the ripple: an ASAP date is hand-set, so **ASAP counts as a hard date everywhere** — back into both EOS denominators, anchoring material-order lead time, sorting ahead of plain hard on the install schedule. Colour-drop (`COLOR_DUMP_STAGES`), the per-PM cap, the `asap_after_install_start` refusal, the Paint Complete intercept, the Ship Complete drop and Break/Link are all untouched | `routes.py` (`set_asap` + undo), `start_install/command.py`, `neutralize_install_date_cascade.py`, `stage/command.py`, `eos_metrics.py`, `material_orders/service.py`, `install_schedule/service.py`; `StartInstallDateModal.jsx`, `JobsTableRow.jsx`, `StartInstallEditor.jsx`, `JobDetailsBody.jsx`, `utils/asap.js`, `utils/jobLogPdf.js`; tests `test_asap_mode.py` + `test_install_start_color_dump.py` | **high — client-decided** |
| BUG-11 | ~~Hard-date color dump fires too early — moves from the ship stages to `Install Start` or later [bill-2026-08-21#L109/#L113/#L115]~~ **built 2026-08-29** to the 2026-08-29 spec exactly: the dump fires on a stage transition whose destination is in `COLOR_DUMP_STAGES` = {`Install Start`, `Install Complete`, `Complete`}, never on the `start_install` date arriving. **The triage's "add one reason, remove two" reduction was one site short** — `start_install/command.py:114` set `start_install_no_color = stage in SHIPPING_STAGES` when a user typed a hard date, a third independent encoding of the old boundary (the BUG-8/9/16 second-caller shape again). All three now read the one `COLOR_DUMP_STAGES` constant. The ship-stage hard-date branch in `shipping_stage_date_discipline.py` is now a **deliberate no-op that must not be deleted** — it is the guard keeping hard dates out of the formula-blanking path below it, which would null the date; its docstring says so. Formula blanking untouched, per Bill. "Or later" is enforced by an integrity test asserting `COLOR_DUMP_STAGES` equals the tail of the canonical stage order from `Install Start`, so a stage inserted later can't silently fall out of the set. **Five sites, not the two triaged** — after Daniel confirmed the rule (*"hard date setting unaffected, we wipe color for ASAP or other hard date Install Start or later. Date not changed, just color"*) two more hardcoded `no_color = False` on a hard-date write and would have repainted a dumped row: the **ASAP toggle** (`routes.py:1834`, which stamps a hard date one week out) and the **Trello mirror-card date slide** (`trello/sync.py:256`). Both now read the same constant. The `set_asap` **undo** is deliberately left alone — it restores `prev_no_color` from its own event payload, which is correct. **Side effect worth knowing:** ASAP red now survives Ship Planning (it was being cleared by the wash); the separate `asap_dropped_on_ship_complete` rule still drops it at Ship Complete | `.../start_install/neutralize_install_date_cascade.py` (`COLOR_DUMP_STAGES`, `reason_for_stage`); callers `stage/command.py`, `start_install/command.py`, `shipping_stage_date_discipline.py`; tests `tests/brain/test_install_start_color_dump.py` + updated `test_shipping_stage_date_discipline.py` | **high — client-decided** | **Two follow-on decisions from Daniel, 2026-08-29 (both built):** (1) **ASAP is refused once install has started** — `PATCH /brain/update-start-install` returns `409 asap_after_install_start` when the stage is in the dump zone, and the modal disables the toggle rather than offering a control that 409s. Clearing a stale flag is still allowed. (2) **An ASAP row's date is rewritten to the day install started** when it crosses into the dump zone — the ASAP date was an anchor five business days out, never a plan, so the stage event's own date is the truer value. Scoped to ASAP rows only: a hand-set hard date is a real commitment and still keeps its value ("date not changed, just color" holds for those). The ASAP test is the **caller's**, deliberately — `UpdateStageCommand` drops `start_install_asap` earlier in the same command, so the cascade can't re-derive it and reads a stale False; `had_asap` is captured before that block. **The frontend had its own copy of the old rule and made all of this invisible** — `atShippingStage` was hardcoded in three render paths (`StartInstallEditor`, and the Start install + Ship Date cells of `JobsTableRow`), forcing neutral at the ship stages whatever the DB said. Extracted to one `frontend/src/utils/installDateColor.js` mirroring the backend's `_classify_date`, with the stage check still covering the optimistic pre-refetch window. **Open question, not decided:** `comp_eta` is still whatever was computed from the old ASAP anchor when the date is rewritten — the Gantt bar end may now disagree with its start. **Sharpened 2026-09-02** [bill-2026-09-02]: Daniel's timeline decision is that a drag or edge-compress writes **`start_install` and `comp_eta` only** — no install hours, fab hours or num guys. That makes `comp_eta` directly settable, so a card can hold a duration its hours and crew size do not imply. The same divergence, now reachable by two paths. **Still not decided, and now needs an explicit rule:** does a later hours/crew edit recompute over a manually compressed `comp_eta`, or is a compressed card pinned? Whichever writes last currently wins by accident.
| BUG-16 | ~~DWL **HOLD** must drop when a submittal's ball-in-court changes [daniel-2026-08-29]~~ **built 2026-08-29**. The drop is now one shared rule — `drop_drafting_status_for_bic_change` in `app/procore/helpers.py` — that every BIC writer calls, rather than the same clause copied per caller (which is how BUG-8/BUG-9 came back). It clears **any** drafter-scoped status (HOLD, STARTED, NEED VIF), not just HOLD: all three are set against whoever held the ball and are equally stale once it moves, and the ask named the field, not the value. **Three live call sites, not the two triaged** — the webhook, the CLI health scan, and `POST /procore/health-scan/update` (a second copy of the audit fix loop in `app/procore/__init__.py`, missed at triage). Each folds the drop into the `SubmittalEvents` payload it already emits, so it is auditable. **`app/procore/scripts/reconcile_bic.py` deliberately left alone** — a one-off backfill for the 2026-06-30 webhook outage whose header invariant is explicitly "silent data backfill, emits no SubmittalEvents"; hardcoded to that incident's projects and imported by nothing. Re-check if it is ever generalised. **Found and fixed en route:** the order-compression loop bound its variable to `submittal_id`, shadowing the function parameter of the same name, so after any compression every later log line, the urgency bump and the `SubmittalEvents` row were attributed to the last compressed sibling instead of the submittal that moved | `app/procore/helpers.py` (`drop_drafting_status_for_bic_change`); callers `app/procore/procore.py` + `app/procore/__init__.py`; tests `tests/procore/test_bic_drops_drafting_status.py` | **high — client-asked** |
| BUG-17 | ~~To-Do page cleanup~~ **PARKED 2026-08-29 by Daniel — *"I'll circle back on that"*.** Class `deferred`, not dropped: the reference arrived, was scoped, and the scope was narrowed to frontend/QoL, all on 2026-08-29 — then the whole item came out of the bug pass before any of it was built. **Nothing is lost and nothing needs re-deriving.** The scope doc lives beside the reference tree at `~/Desktop/Reference/eos-todos-reference/SCOPE-for-MHMW.md` (out of the repo with its source material, same as the transcripts). It already carries the seven in-scope frontend items, the one item with a fetch tradeoff, what was ruled out and why, and the finding that reframes the task — **we have no to-do table**; ours are `ChecklistItem` rows the meeting extractor creates. **Re-check trigger: Daniel raises it again.** → **TRIGGER FIRED 2026-09-02** [bill-2026-09-02#L1607]: Bill asked for it unprompted — the To-Dos page gets **two columns, your to-dos and mentions, defaulting to yours**, with the ability to see others'; **@mention from anywhere you can write a note** raises a notification; and to-dos must be **editable after creation** — today *"the only thing you can do is [complete] it"* [#L1624]. He also framed the eventual home: to-dos, **rocks** for your team, and **my metrics** (the scorecard with a graph), plus a **company announcement** slot [#L1630] — *"you guys use 90s, figure out what you like about it, and then we probably fold it in your brain"*. ~~Unparking is Daniel's call.~~ **UNPARKED AND HALF-BUILT 2026-09-04** (PR #369, v2.0.369) — Bill's first two asks landed together: the page is now **two equal columns**, your to-dos on the left and the **@mentions of that same person** on the right, with one page-level owner control driving both and scope **server-enforced on each** (an admin may view any user or everyone; a non-admin only themselves). Mentions carry the sentence that was written, not just *"X mentioned you"* — `Notification.to_dict` now surfaces the source comment's body (280-char excerpt) and `author_name`, with a regex fallback that reads the mentioner out of the message for the **DWL** case, which has no comment row to read an author off. The mentions column requests `MENTION_TYPES` only, so a burst of to-do notifications cannot push mentions past the row cap. **@mention-from-anywhere is effectively there** — board comments, PDF drawing markups and DWL notes are all mention producers feeding the one bell. **Still open, and the reason this stays on the list: to-dos are not editable after creation** [#L1624]. Filtering, scoping and reading all improved; grab/move/reorder/edit did not ship, and that is the ask Bill phrased as *"literally the only thing you can do is [complete] it"*. **The home-page shape (rocks · my metrics · company announcement) remains unstarted and unscoped** — it is a page, not a cleanup, and wants its own ID when it starts | scope doc `~/Desktop/Reference/eos-todos-reference/SCOPE-for-MHMW.md`; page `frontend/src/pages/ToDos.jsx`, `app/brain/notification_routes.py`, `Notification.to_dict` | **open — editability half** |
| BUG-18 | ~~Left icon rail pops in extra rows on load [daniel-2026-08-29]~~ **built 2026-08-29**. Took the triage's first candidate — cache the last-known role in `localStorage` and hydrate optimistically — over reserving space, because reserving would leave a non-admin staring at six blank slots on every load to spare admins one reflow. `AppShell`'s three role `useState(false)` calls collapse into one `useState(readCachedRoleFlags)`; `checkAuth` still decides and overwrites. `canUseBBChat` (Carmen) was gated the same way and had the same pop-in, so it rides along. **The cache is a first-paint hint, never an authorization decision** — the server gates every route — and `logout()` clears it so the next user on a shared browser cannot inherit the previous one's rail; a null `checkAuth` (expired session) clears it too. Reads/writes are try/catch'd for private-mode Safari, falling back to the old all-false start | `frontend/src/utils/auth.js` (`roleFlagsFor`, `readCachedRoleFlags`, `cacheRoleFlags`), `frontend/src/components/AppShell.jsx` | low — cosmetic |
| BUG-15 | ~~Meeting-bot transcription autodetects language — mis-detected a production standup as Portuguese and translated a line [bill-2026-08-21#§2]~~ **built 2026-08-21**: `language_code: "en"` + explicit `prioritize_accuracy` mode pinned on every dispatch (covers the calendar poller and the on-demand route, which share `dispatch_bot`) | `app/brain/meetings/recall.py` (`TRANSCRIPT_LANGUAGE`); test `tests/brain/test_calendar_recall.py::test_dispatch_bot_pins_transcription_to_english` | med |
| BUG-12 | ~~Carmen lookahead tool returns a stale window — Novel Flatirons pull starts in May [bill-2026-08-21#L133]~~ **built 2026-08-21** (PR #348): the symptom was the rendered Gantt axis, not the data. `_chart_range` expanded the x-axis *backwards* to cover any past-dated phase bar, so one stale bar rewound the whole chart to May. It now starts at the declared window and only extends forward — the window is a viewport, not a row filter. The other two halves of Bill's ask were **already true and predate the bug**: the schedule window is 3 weeks from `today` (`schedule_builder.py:427`), and the phase labels (Drafting / Fabrication / Paint / Shipping / Installation) landed 2026-07-25 | `app/brain/lookahead/export_pdf.py` (`_chart_range`); test `tests/lookahead/test_export_pdf.py` | med |
| BUG-13 | ~~Backspace intermittently dead in the meeting-notes to-do input [bill-2026-08-21#L95]. Unreproduced — Bill and Daniel have both seen it; instrument before fixing~~ **DROPPED 2026-09-04 by Daniel — "unless we hear otherwise".** Class `deferred`. Never reproduced by anyone trying; it has sat at the bottom of the queue since 8/21 on two sightings and no repro. **Re-check trigger: the next time it is seen** — a fresh sighting with what was typed re-opens it, and nothing needs re-deriving from this row | `frontend/src/pages/Meetings.jsx` (to-do note input) | low |
| BUG-14 | ~~iPad rotation dumps modal/scroll state — *"you're like, where was I?"* [bill-2026-08-21#L145]. **First pass 2026-08-30 (no physical iPad).** Root cause tracked down without the device: `useBreakpoint` buckets at 1024 (lg) and 1280 (xl) swap the mounted cards/table tree on rotate (10.2" iPad with Table picked: portrait cards → landscape table; 12.9" iPad Pro Auto: 1024 cards → 1366 table). The open `ReleaseHubModal` lived *inside* the unmounted tree (`JobLogCardGrid` / `JobsTableRow`), so the dialog and list scroll both died. First-pass fix (branch `fix/iPad-rotation-bug`): host the hub on the page that survives the swap (`JobLogContent`, plus Archive and DWL which have the same remount), persist list + modal-pane scroll across `orientationchange`, stash the open dialog in `sessionStorage`. Did **not** rotation-lock.~~ **DROPPED 2026-09-04 by Daniel — "unless we hear otherwise".** Class `deferred`. The build is done and on `main`; what remained was a verification pass that needs the physical iPad, and it is not worth holding a queue slot for. **Re-check trigger: the next rotation complaint, or the next time the iPad is on the desk** — the same device gate T1's drag is waiting on, so the two verifications should ride together | `frontend/src/pages/JobLogContent.jsx` (hosted hub); `frontend/src/utils/viewportView.js` (the remount matrix); `frontend/src/hooks/usePersistScroll.js` | low |
| BUG-9 | ~~Fab order not flipping 2→1 at paint → complete; order cleared inconsistently~~ **built** | `app/brain/job_log/features/fab_order/tier.py` (tier logic: Complete=NULL, 0, 1, 2, dynamic 3+) | **high** |
| BUG-10 | ~~Sub invite email ships a `localhost:5173` link — `APP_BASE_URL` unset~~ **built** (code + Render config) | `app/config.py:76`, `app/brain/tm/subcontractors/command.py`. Acceptance test — one real invite to Bill — still to run | **high — unblocked A1** |
| BUG-8 | ~~DWL release-number generator doesn't check the archive; job log rejects the number later~~ **built** | `app/procore/procore.py` (`_archived_rel_numbers_for_job`) | med |

**BUG-8 note:** shipping this as a **fix** ahead of its own audit (AUD2) is a
deliberate call — it makes the generator agree with a rule that is already
enforced and already confirmed correct, so it is closing a gap, not introducing
behavior that needs sign-off. Block-vs-auto-advance and long-term identity stay
in AUD2.

**Redaction:** MHMW staff first names (Bill, Colton, Katie, David, Dalton) may
appear. GC/customer companies appear only as job numbers (e.g. 500-998) or
project names already in the record (660 Fox Hill, 645). No contract dollar
values are committed to this file.

**Effort key:** S = under a day · M = 2–4 days · L = 1–2 weeks · XL = 3+ weeks.
Each item states its effort letter in its Now paragraph. **Fit is no longer the
binding constraint** — the October window it was computed against is gone (see
below). The `effort_midpoints` stay for sizing a lane, not for proving a date.

## The 2026-08-15 reset

**Procore was renewed. October 2026 is dead as a deadline; the absolute Procore
dead date is October 2027.** Bill volunteered why, unprompted: he was nervous
about the *cutover*, not the capability — *"not that we wouldn't be functional…
but I would worry that we would have a lot of growing pains and adaptation of
the fine details"* [bill-2026-08-15#L31]. He bought time to do it properly.

Two consequences, both large:

1. **The entire Procore ecosystem is deferred** (Daniel's call, 2026-08-15) —
   P0, P1, P2, P4, P7, P10, P11, C3-narrow and D1-minimal come off the active
   path as one block, joining the already-parked P3/P5/P6/P8. The October
   cut-list decision — the top Owed row since 2026-08-06 — is **dissolved**: the
   window it was cutting against no longer exists.
2. **Trello takes the front.** Bill named the replacement priorities in one
   sentence: *"revamp the **Trello** focus and **subcontractor integration** into
   the Brain **for the invoicing**, and just completing all of the back end
   connections"* [#L31]. Trello is **dead, not read-only** — decommission
   expedited (Daniel's call; Bill's literal words were *"abandon Trello, except
   for read only to some extent"* [#L69], which makes read-only an available
   staging step, not the goal).

**One flag carried, not re-litigated:** P11 (Procore document export) is inside
the deferred block and is the only item whose deferral is **irreversible** — our
hosted PDFs, markups and correspondence die at the lapse and there is no second
attempt. It must resurface with real lead time, not in September 2027.

**A governing principle came out of the same meeting** and now applies past the
item that produced it: **lean on user control; do not automate out user agency
in the short term.** Users have a clear ruleset — the system should not infer
commitments on their behalf (see AUD1).

---

## Workstream 5 — Trello exit *(the front lane)*

Opened 2026-08-15. **End state is Trello dead**, not Trello read-only. Bill
described the current state as *"kind of brutal"* — *"we have so much like things
that are disconnected because it was causing this data overload and bad data
information coming through… we just left this thing behind"* [#L69] — plus a
one-way sync gap: *"if we change something on Trello, it's not updating to the
job log"* [#L69]. His workaround is weekly retraining of the crew onto the job
log. T1 is the gate: the timeline has to do Trello's job before Trello can go.

**The written spec arrived 2026-08-20** — the Owed "Trello phase-1 spec doc,"
delivered as the Manus-prepared field-ops build package (see Sources,
`fieldops-2026-08-20`). It confirms T1–T4/A1 as scoped and adds net-new scope
now carried as **T5–T8** below: field work foundation (assignments / My Work /
mobile work package), punch + field issues + Safety Hold, subcontractor
compliance profiles, and the sub work-authorization + invoicing workflow. Its
phase order (A field foundation → B dispatch → C punch/issues → D T&M → "A.1"
sub financial → F reporting) puts the field foundation *ahead of* the dispatch
timeline — the reverse of Bill's spoken 8/15 priority (T1 first). That
sequencing tension, the mislabeled "A.1" phase, and the cover-email items the
doc doesn't contain are all in one Owed reconciliation row; **T1 stays
`queue.now` until Bill says otherwise.**

**Bill said: T1.** The sequencing thread resolved itself the next morning —
*"it's still more important to get the scheduling piece for the timeline sorted
out first. Just to kind of get out of the Trello piece"* [bill-2026-08-21#L169]
— which also deliberately stalls A1 behind the timeline. The other two
reconciliation threads (cover-email items, the "A.1" label) remain Owed.
**Mobile target for the whole package: iPad first, phone gets "some function"**
[bill-2026-08-21#L155].

**The 2026-09-14 weekly request package took the front of this lane**
(`thisweek-2026-09-14`, Manus-prepared, *"Requested for the current weekly update
cycle"*). Daniel: *"probably these elevate to highest urgency."* It is a
narrower, sharper cut of the 8/20 field-ops spec, with its own build order:
**P0** Issue & Error Register (→ **T11**) and schedule integrity (→ **BUG-24…27**);
**P1** Paint Complete queue, Drop Ship Only, shipping load order (→ **T12**) and
the two-stage Photo Evidence Gate (→ **T13**); **P2** card splicing (→ **T9**,
elevated); **P3** iPad/PC parity (→ **T14**). Three rules it states that govern
everything below:

- **"A timeline card is a release-aware operating record, not a visual sticky
  note"** [§1] — every change writes the authoritative Job Log record, keeps the
  release link, respects capacity, and lands in the Change Log.
- **No parallel scheduler, no separate card database** [§9] — every result is a
  view or a *controlled child* of the project/release/assignment record. That
  sentence is what licenses T9's child records and T13's shipment events while
  forbidding a Trello-style copy.
- **Procore-replacement stays paused** [§1] — explicitly no Submittal Manager or
  Scope Breakdown work this cycle. Consistent with the 2026-08-15 W1 deferral;
  nothing to change.

**Definition of done is a demo, then a live check** [§8]: each request shown on a
real non-production test release, then verified on the live workflow by MHMW. Its
§8 acceptance table is carried into each item below.

### T1 · Timeline assignment — drag, assign, unassigned lane
*W5 · in_progress · class build · due — · deps — · owner daniel · src bill-2026-08-15#L75 · upd 2026-09-16*

Effort L. **Priority 1 of the whole lane** and Bill's top ask, stated twice:
*"being able to **move the cards around and assign them**, and then **the vertical
column of unassigned so we can plug and play**"* [#L61]; *"**we're so close already
with the timeline view**… getting the **mirror cards**, and then being able to
**assign the cards and the dates into those individual people, is going to be the
most critical bit of it**"* [#L75].

The job it must do, in his words: see what's ready to ship, see what's **stored at
Mile High**, grab anything **past paint complete** and drop it where it goes —
*"use that for visual planning for the guys."* **Base is confirmed and, as of 2026-08-29,
is already on `main`** — `feature/jay-view` (day-bucket timeline, PR #286) and
`feature/mirror-cards` (installer lanes as gantt range bars, PRs #300/#301) both
merged in July. There is no branch reconciliation to do: T1 starts from a clean
worktree off `main`, in `frontend/src/components/GanttChart.jsx`. **Un-parks D4**,
which dissolves into this item.

**Drag is a real scheduling write** (confirmed intent, 2026-08-15) — dropping a
card writes the installer field that drives `comp_eta` / `num_guys`, not a
view-local arrangement. That is the point of the feature, not a side effect.

**Two build facts found in the code 2026-08-29, before the first line is written:**

1. **The drag has been built once and pulled once.** The Timeline is declared
   READ-ONLY in its own header — *"The Phase-5 drag interactions — installer-day
   reschedule and shipping-lane stage change — were REMOVED 2026-07-12 for the
   prod-stability release: **native HTML5 drag was dead on iPad anyway**"*
   (`GanttChart.jsx:17-23`). Against Bill's 2026-08-21 **iPad-first** target that
   makes T1 a *rebuild on `@dnd-kit`* (pointer sensors), **not** a revert of the
   removal commit. `Board.jsx` is the only dnd-kit precedent in the codebase and is
   the pattern to copy; the same native-drag rot is logged across ~10 components in
   `docs/tablet-tuning.md`. **Prove drag works on the physical iPad before building
   surface on top of it.**
2. **There is no unassigned lane to filter into.** Lanes are the two fixed shipping
   stages plus the installer roster, and *"a release with no shipping stage and no
   installer appears nowhere"* (`GanttChart.jsx:32`). Bill's *"vertical column of
   unassigned so we can plug and play"* is net-new construction, not a filter toggle
   on an existing lane. **Membership rule decided 2026-08-29 (Daniel): no installer
   assigned AND (ready to ship OR stored at Mile High OR past paint complete)** —
   Bill's stated intake, verbatim. Deliberately *not* "any release with no
   installer": that pulls in everything still in drafting and fab and the column
   stops being a work surface. The three conditions are shop-state, so confirm how
   each maps onto `stage` at build time.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L61 — move/assign cards + a vertical unassigned lane to plug and play from
- 2026-08-15 · transcript · src bill-2026-08-15#L75 — mirror cards + assigning cards and dates to individual people is "the most critical bit"; purpose is visual planning off ready-to-ship / stored-at-Mile-High / past-paint-complete
- 2026-08-15 · decision · src — — priority 1 of W5; base = jay-view + mirror-cards; drag writes the real schedule; absorbs parked D4
- 2026-08-20 · spec · src fieldops-2026-08-20#§5 — written spec confirms the shape (Field Dispatch Timeline: crew/company lanes, unassigned plug-and-play, hard-date-first) and adds Phase-B detail for later: finite capacity baseline **3 installers / 24 labor-hrs per day per crew** (overridable per release via existing `num_guys`), drag restricted to PM/Field Super (a sub admin may only move cards between their own teams), look-ahead attachment, and per-card readiness flags (§12: FC / materials / shipping / equipment / site / crew)
- 2026-08-21 · transcript · src bill-2026-08-21#L169 — priority reconfirmed over the spec's Phase-A-first ordering: the timeline scheduling piece comes first, "to kind of get out of the Trello piece"
- 2026-08-29 · note · src — — base verified **already merged to `main`** (jay-view PR #286, mirror-cards PRs #300/#301); the roadmap's "base is confirmed" read as two branches to reconcile, and that work does not exist. T1 starts from a clean worktree off `main`
- 2026-08-29 · decision · src — — drag rebuilds on `@dnd-kit`, not restored from the 2026-07-12 removal: the removed implementation was native HTML5 drag, dead on iPad, and iPad is now the stated target [bill-2026-08-21#L155]. iPad drag is the first thing to prove, on the physical device
- 2026-08-29 · note · src — — the unassigned lane is net-new: no lane today holds a release with neither a shipping stage nor an installer (`GanttChart.jsx:32`)
- 2026-08-29 · decision · src — — unassigned-lane membership = **no installer AND (ready to ship OR stored at Mile High OR past paint complete)**, Bill's stated intake. "Any release with no installer" was considered and rejected — hundreds of drafting/fab rows would drown the column
- 2026-09-02 · transcript · src bill-2026-09-02#L442–L900 — **design closed.** A full live demo settled every open question: hard date == scheduled date, with projected a separate soft state [#L625]; drop with no hard date sets installer + `start_install` and promotes to scheduled [#L677]; drop on a card that **already holds a hard date snaps back to that date** and ignores the drop cell — *"we're forcing the hard date on the first pass"* [#L739]; order by date regardless of hard/projected, with project demoted to a **filter reusing the job-log search element** [#L646]; no per-day card cap — an overloaded day should look overloaded [#L449]; collapsed cards show job-release, hover for the rest [#L454]
- 2026-09-02 · transcript · src bill-2026-09-02#L525–L615 — **"unscheduled but assigned" is a required third state.** Work can belong to an installer with no scheduled date; today it would land on their lane at a meaningless projected date (Bill's case: something showing on Oscar's lane back in April). Shape agreed: a per-installer collapsed **tower** beside the lane; dragging out of it sets the date. The existing Unassigned lane pulls unassigned cards at **paint-complete or later** [#L546]
- 2026-09-02 · transcript · src bill-2026-09-02#L503–L524 — Shipping Planning follows the install card (start install − 1 business day minimum); **Shipping Complete locks** — *"that should be locked for eternity"*. Business days are **not** currently computed for start install [#L515]
- 2026-09-02 · notes · src bill-2026-09-02 — sharpened by Daniel's notes: **Ship Complete freezes at the drop and the card stays put** — `start_install` keeps moving as the install card moves, but never touches the Ship Complete card. Cards get a **red/yellow/green border keyed to date type** with the date shown on the card. A drag or edge-compress writes **`start_install` and `comp_eta` only** — no install hours, no fab hours, no num guys
- 2026-09-02 · notes · src bill-2026-09-02 — new UI defect for this lane: the **unassigned expand/contract sidebar hides when the table is scrolled down**
- 2026-09-02 · transcript · src bill-2026-09-02#L471–L510 — three defects found live in the demo: install hours don't compute on a **weekend** drop [#L471]; a **duplicate-event bug** blocks moving a card back to a position it held [#L509]; a card appeared to **stretch/jump ~3 days** on an early drag, not reproduced on retry [#L478]
- 2026-09-02 · decision · src — — endorsed: *"you got the right concept right in place here"* [bill-2026-09-02#L890]. T1 stays `queue.now` with its design no longer open
- 2026-09-04 · status · src — — **not-started → in_progress.** PR #361 shipped the core on `main`: drag rebuilt on `@dnd-kit` (MouseSensor 8px + TouchSensor 220ms press-and-hold, per the 2026-08-29 decision), the pinned **Unassigned tray** with membership in `utils/unassignedLane` matching the agreed rule, drag-to-assign both directions, and drag/modal tests (`GanttChart.drag.test.jsx`, `shipLaneDrop.test.js`). Follow-up 1956607 added the tray's start-install date, border color and ordering. **Not `built`** — the 2026-09-02 session added scope that has not landed: the per-installer **tower** for unscheduled-but-assigned work, the three defects found live in the demo (weekend drop, duplicate-event block, the ~3-day stretch), the sidebar hiding on scroll, and business days for start install. Physical-iPad drag is still unproven
- 2026-09-14 · spec · src thisweek-2026-09-14 — the weekly package lands almost entirely on this item's surface and goes ahead of it in the queue: weekend behavior (**BUG-26 absorbs the weekend-drop defect**), installer count on the card (BUG-24), ASAP red on ship-lane cards (BUG-27), a Paint Complete queue beside the Unassigned tray, Drop Ship Only lane and load order (T12), open-issue count on the card (T11). T1 keeps its remaining own scope (tower, duplicate-event block, stretch, sidebar-on-scroll). Note the Paint Complete queue double-books the tray's 2026-08-29 intake rule (Open question 7)
- 2026-09-16 · transcript · src bill-2026-09-16#L997–L1112 — **hand-adjusted bars ruled:** `start_install` is the budgeted anchor and never moves on an edge-drag; the far edge moves `comp_eta` (synced to Trello) with **no internal recompute** of hours or guys. Purpose: *"it actually gives us the ability to track over our installations"* [#L1063]. Hand-adjusted releases must be **listable** for later review [#L1109]; no special flag on `comp_eta` in the table
- 2026-09-16 · notes · src bill-2026-09-16 — the hand-adjusted bar gets a **visual mark** (e.g. diagonal hatching) showing it was stretched/compressed outside the budgeted timeline
- 2026-09-16 · transcript · src bill-2026-09-16#L1418–L1545 — card display: drop photo + PM initials, wrap job-release/name/description to full visibility (filed **BUG-31**); weekend-skipping confirmed as right, matches Trello [#L1540]; Trello member bubbles not needed — the home page (N19) replaces that filter use [#L1565]
- 2026-09-16 · transcript · src bill-2026-09-16#L1598–L1617 — **dropship lane** at the bottom of the Timeline, a normal lane (Doug's ask) — T12 ②

### T2 · Admin member management — permissions + onboarding, consolidated
*W5 · in_progress · class build · due — · deps — · owner daniel · src bill-2026-08-15#L83 · upd 2026-09-02*

Effort M–L. **Runs in tandem with T1**, not queued behind it. The problem is
scatter: sub invites live in the subs/T&M surface, staff roles are boolean flags
on `User` (`is_admin` / `is_drafter` / `is_active`) set by Daniel on request, and
there is no single place showing who has what. Bill's ask [#L83]: *"an **admin
view for users**… add people to the Brain and then **assign their permissions**,
and it just sends them an invite… **we can see all the users**… **reset their
password and block them**"* — motive stated plainly: *"I'm not having to ask you
to add this guy at this permission."*

**One page, one surface.** **Sub invite moves out of subs/T&M and into member
management** — a sub is just another member being onboarded. Permission *rules*
must be legible to admins, who can elevate or lower access themselves. There is
room to collapse other scattered admin surfaces into it. Whether `Subcontractor`
folds into the `User`/role table is a build-time call, not a roadmap decision.

**Bill self-deprioritized the page** (*"I'm not too concerned with that piece
yet, but long term I think that's a deal"*); it is elevated here because the
permission model underneath it is load-bearing for T3.

**Stage as of 2026-09-02:** Bill's six actions from [#L83], against this
page. **See all users and assign permissions have landed.** The other four are
not started.

| Bill's action | Status |
|---|---|
| See all users | **done** — admin-only `/admin/users` (`GET /brain/directory`). First / Last / email / role. Split Employees (`users`) vs Subcontractors (`subcontractors`). Shared `table-fixed` columns so the two sections line up. Rail item sits under Matching; also in the top bar and drawer |
| Add people | open |
| Assign permissions | **done** — per-employee role select on `/admin/users` (`PATCH /brain/directory/employees/<id>/role`, admin-only). Three mutually exclusive levels: `Admin` / `Drafter` / `Default`, written to the existing `User` booleans. Subs are untouched and stay labelled `Subcontractor` |
| Send invite | open — sub invite stays on the Subs roster until it relocates here |
| Reset password | open |
| Block | open |

Also still open, not in the spoken six: relocate sub invite onto this page, and
the role-model decision (boolean flags cannot express one person holding
multiple named roles). T3 visibility walls are unchanged.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L83 — admin user view: add, assign permissions, invite, see all users, reset password, block
- 2026-08-15 · decision · src — — one page covering staff + subs; sub invite relocates here; admins own elevation/deferral; consolidation of scattered admin surfaces invited; runs in tandem with T1
- 2026-08-20 · spec · src fieldops-2026-08-20#§3.2 — written spec confirms the Procore-style admin center (invite by email, first-time onboarding, role templates, checkbox permission overrides, MHMW/External/Vendor classification, audit log of who invited/changed what) and adds a load-bearing requirement: **one person may hold multiple roles** (e.g. PM + Field Super). Boolean flags on `User` cannot express that — the "build-time call" on whether `Subcontractor` folds into a `User`/role table now has a real constraint pushing toward an actual role model
- 2026-08-30 · build · src — — first pass landed on `feature/user-directory`: read-only admin directory (Employees from `users`, Subcontractors from `subcontractors`), First/Last/email/role, no controls. Tables stay separate. T3 visibility walls are unchanged
- 2026-08-30 · note · src — — **see all users** is the completed slice of Bill's six [#L83]. Add / assign permissions / invite / reset password / block remain open. Directory reviewed in-session: column widths locked so Employees and Subcontractors share one horizontal grid; Users rail icon moved under Matching. Status stays `in_progress`; queue.now stays T1
- 2026-09-02 · build · src — — **assign permissions landed**, second of Bill's six. Role is now an in-place select on each employee row (`PATCH /brain/directory/employees/<id>/role`, `@admin_required`), saving immediately and optimistically. **Decision: the three levels are mutually exclusive** — `Admin` / `Drafter` / `Default` — rather than independent checkboxes. That is lossless against the flags underneath, because every drafter gate in the app is `is_admin OR is_drafter` (`drafter_or_admin_required`), so an admin already holds every drafter permission and the legacy "both flags" rows collapse to `Admin` with nothing lost; writing a role normalizes the pair. `Employee` was renamed `Default` per the client's wording. Two guards keep admins from locking themselves out of this page: no one can change their own role, and the last remaining admin cannot be demoted. **The Subcontractor group is deliberately unaffected** — separate table, no role control, still labelled `Subcontractor`. This does **not** discharge the 2026-08-20 spec requirement that one person hold multiple named roles [fieldops-2026-08-20#§3.2]: the boolean pair still cannot express that, and the real role model remains open ahead of T3

### T3 · Subcontractor visibility — short-term scope
*W5 · in_progress · class build · due — · deps T2 · owner daniel · src bill-2026-08-15#L93 · upd 2026-09-23*

Effort M. **Short term:** subs see their **T&M tickets plus the relevant data for
that job release**, pulled into the sub view. **Mid term this item dissolves into
T2** — visibility becomes a property of a role (sub / drafter / PM / admin),
not a per-surface decision.

**The written scope arrived 2026-08-20** and hardens the walls: a sub is limited
to their company, assigned projects/releases, and explicitly shared documents;
never other subs' work, MHMW labor rates, budgets, O&P, or margin; **FC is the
default field drawing — DRR and internal review content are never exposed**;
every access-sensitive record must carry a project link plus an
assigned-user/crew/company link [fieldops-2026-08-20#§3.1]. Bill's *"mostly the
fab hour is the only thing they don't actually see"* [#L93] remains his eventual
posture, not the short-term scope — the spec's full sub *portal* (My Work,
mobile work package) is carried by T5, not here.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L93 — "give them everything that they need, but not show them what they shouldn't see"; fab hours named as the main exclusion; scope to be detailed in his doc
- 2026-08-15 · decision · src — — short term = T&M + that job release's data; mid term collapses into the T2 role model
- 2026-08-20 · spec · src fieldops-2026-08-20#§3.1 — permission rules written: company/project/release scoping, no financial visibility, FC-only drawings, mandatory project + assignee linkage on sensitive records
- 2026-09-02 · transcript · src bill-2026-09-02#L900–L1013 — **Bill named this the next real big push**: *"this is great for Doug, worthless for the subs because they can't see it… that'll be the next real big push is to get them access to see"* [#L912]. Full permission matrix specified: subs see the **timeline only, no job log table**, and only their own assignments [#L917]. Inside a release modal they get **full attachments** — view, mark up drawings, add attachments and photos [#L919] — plus **notes** [#L983]; they see install hours, stage, stage group, billing tag, materials ordered, PM, and **activity**. **Fab hours are the only field removed** [#L921]. **Changelog blocked** (Daniel's call; Bill was neutral) and **no undo button** [#L953]. No other data updates
- 2026-09-02 · transcript · src bill-2026-09-02#L986–L1008 — the *why*: the modal becomes the **direct channel to the billing team** — *"they don't have to even create invoices if they don't want to. They can just mark, hey, it's ready for invoicing"*, gated on photos and a written claim of completion. Subs get a **home page**, not a table: their T&M tickets and scheduled installs [#L1005]
- 2026-09-02 · decision · src — — sequencing confirmed: Bill's next-big-push runs through `deps T2`. You cannot invite subs without member management, so the chain is **T1 → T2 → T3** and T2's position in `queue.next` is load-bearing
- 2026-09-07 · decision · src — — **scoping key decided: crew, not per-release.** A sub account is scoped to one installer crew and sees that crew's releases. Chosen over a `ReleaseAssignment` join table because assignment today genuinely *is* crew-level — a crew works whatever is in its lane — and per-release grants need an assignment workflow that **T5** owns, not this item. Consequence accepted by Daniel: two accounts on the same crew see the same releases, which matches the spec's company-level scoping [fieldops-2026-08-20#§3.1]
- 2026-09-07 · build · src — — **slice 0 landed** (`fix/improved-subs-view`, `f4009e4`; migration run on sandbox). `Subcontractor.installer_team` holds the crew NAME, matching `Releases.installer` by value — deliberately the **same string key** the Subs tab, install schedule and timeline lanes already scope on, so sub visibility needs no new join and **no migration on the hot `releases` table**. NULL resolves to zero releases: the scope query **fails closed**, so existing accounts keep exactly today's access until an admin scopes them. Writes go through `command.set_installer_team`, which matches case-insensitively but **stores the roster's canonical casing** (the value is a join key and that comparison is exact — accepting "saul 2" verbatim yields an account that matches nothing while looking configured) and refuses anything off the roster, because a typo'd crew scopes to zero and presents as "the feature is broken" rather than as bad data. Options come from `assignable_installer_teams()` in `app/brain/subs/service.py` — the configured roster minus the existing `_SUBS_EXCLUDED_INSTALLERS` set (Oscar is MHMW staff) — **one function feeding both the dropdown and the validator** so they cannot drift. Admin control is a Crew column on the Subs roster; `GET/PATCH /brain/subcontractors/installer-team(s)`, admin-only. **No sub-visible effect yet** — slice 1 is what makes the key do anything
- 2026-09-07 · note · src — — **three findings from the code survey that shape the rest of the item.** (1) **The timeline has no server-side data route** — `/brain/gantt-data` is dead (its own docstring says so) and `GanttChart.jsx:634` builds everything client-side from `useReleases()` → `GET /brain/jobs`, the whole job log including fab hours. Bill's "fab hours are the only field removed" [#L921] therefore **cannot be a UI change**; it has to be a scoped server payload, which is slice 1. (2) **Two schema walls inside the stated scope**: `ReleaseDrawingVersion.uploaded_by_user_id` and `DrawingVersionComment.author_id` are both NOT NULL FKs to `users`, so a sub can author **neither a markup version nor a note** without an authorship-model change — the least obvious cost in the item, and it lands in slice 4. (3) **Two things are free**: `ReleaseDrawingVersion` is documented as one PDF per release and *is* the For-Construction drawing, so the spec's FC-only wall holds by construction; and drag is already role-gated (`canDrag = isAdmin`, every draggable `disabled` otherwise, hook order deliberately identical for both roles), with the detail modal already downgrading to `mode: 'view'` — a read-only timeline is an existing code path, not new construction. That modal gate is **display only**, though: the endpoints behind it are `@login_required`, so the wall still has to be server-side
- 2026-09-07 · decision · src — — **notes are a Notes Thread on every release** (Daniel's framing, and it is the one the code already implements). `Releases.notes` is the denormalized "latest message"; the thread itself is the `update_notes` event stream, rendered by `ReleaseNotesRail` — `buildTimeline` already pushes each event as `{kind:'note', author, at, body}` from the event's `to`, i.e. a **posted note, not a from→to diff**. Under this framing the job-log cell's overwrite is not data loss, it is "the cell shows the most recent post", so the editable-textarea affordance **stays as-is** (Daniel: revisit only if the client trips on it). **Subs write the same thread as everyone else.** Traced 2026-09-07 and the thread is sound: `features/notes/command.py:93` is the ONLY writer of `Releases.notes` on an existing release and it emits its event *before* assigning, so the field cannot move without an event — the opposite of the four-writer shape behind BUG-22/BUG-23. Trello never writes the field (every `notes=` in `app/trello/` is outbound to card creation or a comment); `seed.py` sets it only at INSERT. Creation-time notes therefore carry no event, which Daniel closed as a non-issue: **users cannot create a release with a filled note**
- 2026-09-07 · decision · src — — **`Releases.notes` widens from `String(256)` to `Text`.** The two write paths disagree today: `seed.py` wraps every write in `safe_truncate_string(..., 256)` while `UpdateNotesCommand` assigns straight through with no length check anywhere in the route — so a >256 note silently truncates on one path and raises on Postgres on the other, and in-memory SQLite tests cannot catch it (the `sqlite_postgres_varchar` trap). Latent for internal users (nobody types 256 chars into a shop cell) and near-certain for a sub describing a site problem on a phone. Metadata-only migration, lands in slice 2
- 2026-09-07 · decision · src — — **subs see Activity, never the Changelog** [#L953], and that is enforced as a PAYLOAD boundary, not a hidden tab. The rail is fed by `GET /brain/events`, which is `@login_required` and serves the whole filterable feed — a sub session could query any release's full history. So the sub view gets its own scoped route returning one release's events, limited to `ACTIVITY_ACTIONS` + `update_notes`, only for a release on their crew. Same shape as the fab-hours wall: the changelog is blocked by never having a route that serves it
- 2026-09-07 · note · src — — **notes need no schema change for attribution, but one resolver change.** `ReleaseEvents` already carries `external_user_id` (added for Trello/Procore webhook actors), so a sub note attributes with no migration. But `_resolve_event_user_names` (`job_log/routes.py:2690`) resolves ONLY `internal_user_id` against `users` and returns None otherwise, so the rail falls back to `e.source` — **a sub's note would post to the thread as "Brain"**. Teaching that resolver about subcontractor actors is slice 2 work, in a different place from the three content tables
- 2026-09-07 · note · src — — **`deps T2` is real for onboarding, not for building.** Slice 0 was built and tested against the one subcontractor already in sandbox; T2's add/invite flow is what makes enrolling subs self-serve, and is still required before this reaches real crews. **`queue.now` is unchanged at T1** — T3 work started without a queue decision, and reordering is a session agreement, not an agent call. T1 still carries unlanded scope (the per-installer tower, the three defects from the 9/2 demo, business days, iPad drag). The one real coupling: the **tower changes what a lane is composed of**, and the sub view constrains lane composition — so the sub timeline must reuse the existing lanes over a filtered roster and **must not grow its own lane logic**, or the tower will rework it
- 2026-09-16 · transcript · src bill-2026-09-16#L1618–L1642 — reconfirmed: sub view is **permanently filtered to what's assigned to them**, table + timeline (active / billed / paid); data = the Trello-card baseline (job, description, install hours, num guys, duration) + attachments/photos, **no fab hours**. Doug has been showing subs the Timeline — *"they're excited"*
- 2026-09-16 · notes · src bill-2026-09-16 — issue **owner** (T11) can be anyone, and will include subs — a sub-side issue path lands with this item
- 2026-09-23 · decision · src — — **fresh start on `feature/shipping-planning-mobile-column`** (worktree `worktree/feature/shipping-planning-mobile-column`), branched from `main` at `c7682a6`. `fix/timeline-mobile-view` had fully merged (PR #376, 2026-09-11) and carries nothing further. `fix/improved-subs-view` was 70 commits behind main; its slice 0 (`f4009e4`) is cherry-picked here and its uncommitted slice-1 read model (`app/brain/sub_portal/`, crew-scoped `GET /brain/subcontractor/releases` with an allowlist serializer) is carried as a WIP commit. The old branch stays untouched until this one lands. Item now spans the sub view, the mobile view and timeline behaviour together
- 2026-09-23 · build · src — — **sub portal built end to end for hand-testing** (`feature/shipping-planning-mobile-column`, not yet merged; migration `add_subcontractor_todos_and_mentions.py` NOT yet run anywhere). A sub logs in at `/sub/login` and lands in a phone-portrait shell with two bottom tabs. **Job Log** = the crew's Timeline as the day-row calendar from PR #376, fed by `GET /brain/subcontractor/install-schedule/by-day` with the crew **pinned server-side** (no query param can widen it; an unscoped account gets an empty window, never everything) and the internal `notes` key stripped from every card; a collapsible *Not yet scheduled* list covers crew releases with no install date; a card tap opens a **read-only bottom sheet** (`SubReleaseSheet`) from `GET /brain/subcontractor/releases/<id>` (404 off-crew) — the staff `ReleaseHubModal` is deliberately not reused because every endpoint behind it is `@login_required`. **To-Dos** = two segments: to-dos owned by the account and mentions/pings addressed to it. **Decision: subs become first-class to-do owners and mention targets via two nullable columns, not a join table** — `ChecklistItem.owner_subcontractor_id` (exactly one owner column set; `review_item` clears the other) and `Notification.subcontractor_id` with `user_id` made nullable and a CHECK that exactly one recipient is set. Staff pick a sub in the SAME owner dropdown (`/meetings/assignable-users` lists them as `sub:<id>`), and `@FirstName` resolves to a sub by the first word of `contact_name` on the two release-linked producers only (drawing comments, release issues) — a staffer and a sub sharing a first name both get notified rather than one being silently dropped. Assignment and due-date pings route to whichever owner column is set. All sub reads go through allowlist serializers in `app/brain/sub_portal/service.py`. Seed script `scripts/seed_subcontractor_login.py` (dry-run default) creates a login scoped to a crew. **Deferred to after hand-testing:** tests (Daniel's call), sub-authored notes/photos/markup (the NOT NULL authorship FKs from the 9/07 survey), Octavio's in-house status vs the assignable-crew list, phone/contact fields on the account

### T4 · Trello teardown
*W5 · not-started · class build · due — · deps T1 · owner daniel · src bill-2026-08-15#L69 · upd 2026-08-15*

Effort M, unknown until T1 lands. The actual decommission: mirror cards, the
board sync, `TrelloOutbox`, the list mapper, the webhook queue and its drainer.
Read-only is available as a staging step. Sequenced after T1 because the timeline
must be doing Trello's job before the plug comes out.

**Trail**
- 2026-08-15 · decision · src — — end state is dead, not read-only; expedited; teardown waits on T1

### A1 · T&M package — gated, then elevated
*W5 · not-started · class build · due — · deps BUG-10 · owner daniel · src bill-2026-08-15#L145 · upd 2026-09-03*

Effort M. **Unblocked 2026-08-15 — BUG-10 landed and this elevates with it, as
planned.** It was blocked on the invite link, since Bill cannot evaluate the sub
side without a sub in the system: *"I still can't get a sub added to it to see how
it looks on the back end yet"* [#L145]. `APP_BASE_URL` is now set in Render to the
service's public URL, so invites build a reachable link.

**One step stands between "unblocked" and "confirmed":** nobody has yet watched a
real invite arrive and open. Send Bill one before treating sub enrollment as
working — that is also the acceptance test for BUG-10.

**Delivery constraint, stated deliberately:** one package, not piecemeal —
*"there's definitely some things that we saw in the initial run through that we
kind of wanted to change, but [I want to] try and deliver it as one package…
instead of piecemealing it together"* [#L145]. **His change notes are lost**
(*"I did, but I don't know where they went"* [#L155]); he promised to reproduce
them, against three all-day meetings and a flight. Sentiment is positive: *"the
overall concept is right there… excited about being able to track that well."*

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L145 — blocked on sub enrollment; deliver as one package, not piecemeal
- 2026-08-15 · note · src bill-2026-08-15#L155 — Bill's original change notes lost; reproduction promised, treat as unlikely near-term
- 2026-08-15 · decision · src — — gated on BUG-10, elevates on landing
- 2026-08-15 · note · src — — unblocked: `APP_BASE_URL` set in Render; first real invite send is still the confirmation
- 2026-08-20 · spec · src fieldops-2026-08-20#§10 — written spec restates the T&M shape unchanged (Draft → Submitted → GC Signed → Internal Approval → CO Request → Distributed → GC Approved → SOV → Invoiceable; finger/pen signature + typed name; O&P from contract, shown separately on the CO Request PDF, hidden from subs; 14-day Carmen follow-up) and adds field-side entry: opening a ticket from an assignment auto-populates project, release, GC contact, foreman, and location — that last part is T5/T8 ground, not a change to this package
- 2026-08-21 · decision · src bill-2026-08-21#L169 — deliberately stalled behind T1 by Bill: *"the T&M ticket thing — I know we kind of just stalled out on where that's at. I think it's still more important to get the scheduling piece for the timeline sorted out first."* Demoted in `queue.next` accordingly; the one-package delivery constraint and the lost change notes stand
- 2026-09-02 · transcript · src bill-2026-09-02#L999–L1020 — T&M tickets **live separately from releases, optionally linked** — a ticket can carry just a job number, or attach to a release; clicking through opens the **release modal, not a table view**, with the same drawings / photo markup / add-note capability [#L1009]. The one gap Bill found: **a signature block with two planes, GC and subcontractor** [#L1017]. Routing (*"once they're done with it, it goes to this guy, this guy"*) is already written in the field-ops doc — Daniel to read that section and return with questions
- 2026-09-02 · notes · src bill-2026-09-02 — the signature must be an **actual finger signature** (touch capture), not a name field

### T5 · Field work foundation — assignments, My Work, mobile work package
*W5 · not-started · class build · due — · deps T2 · owner daniel · src fieldops-2026-08-20#§6 · upd 2026-08-20*

Effort L–XL. The spec's **Phase A** — its stated immediate priority — and the
largest genuinely new surface in the package. Three pieces: **Installation
Assignment** records (the field version of a Trello card: project + release +
crew/company + scheduled dates + capacity slot + current FC package, with
status Not Scheduled → Assigned → Confirmed → In Progress → Ready for
Verification → Complete / Blocked / Rescheduled) [§4, §5.3]; a **My Work**
queue (mobile-first: today / this week / overdue / blocked, same task engine as
project to-dos so a person has one trusted queue) [§5.2]; and the **mobile
release work package** (current FC or as-built — never a stale revision
mistaken for current — site contacts, readiness state, photo upload,
Job-Log-style low-friction status toggles that only prompt for hours/detail
when it earns its keep: T&M, blockers, completion) [§6, §7].

**Two rules worth pinning now:** a field "Complete" is a *request for
verification*, not a billing event — PM/Field Super verify before the Job Log
flips and the invoicing engine gets the completion signal [§7.2]; and
assignment cards are **release-linked views of the Job Log, not separately
maintained cards** [§2.1] — the exact one-way-sync disease Trello died of.

**Sequencing tension, on the record:** the spec ranks this ahead of dispatch
(T1 ≈ its Phase B); Bill's spoken 8/15 priority was T1 first. T1 holds
`queue.now` until the reconciliation conversation says otherwise (Owed).

**Trail**
- 2026-08-20 · spec · src fieldops-2026-08-20#§5–7 — Phase A scope written: assignment records, My Work, mobile work package, low-friction updates, complete-is-a-request rule
- 2026-08-20 · note · src — — spec's Phase-A-first order conflicts with Bill's spoken T1-first priority; parked in the Owed reconciliation row rather than silently reordered
- 2026-08-21 · decision · src bill-2026-08-21#L169 — sequencing resolved: T1 first, this follows; the spec's Phase-A-first order does not override the spoken priority
- 2026-08-21 · decision · src bill-2026-08-21#L155 — mobile target: **iPad first**, phone gets "some function"; Bill is pushing everyone to iPads (Procore's phone app is the cautionary tale). Field photo habit confirmed working: capture natively, upload after — keep the upload path first-class [#L147]

### T6 · Punch, field issues, and Safety Hold
*W5 · not-started · class build · due — · deps T5 · owner daniel · src fieldops-2026-08-20#§8 · upd 2026-08-20*

Effort L. The spec's **Phase C**, plus the safety layer it threads through.
**Punch items** get ownership (internal crew, sub company, or named worker),
location, evidence, priority/due date, and a verified closeout: Created →
Assigned → In Progress → Ready for Verification → Verified Closed, with
rejection bouncing back to Assigned and overdue items going red in the owner's
My Work [§8]. **Field issues** replace the phone-call/text black hole: ten
categories (material, shipping, drawing discrepancy, field condition, site
readiness, scope/T&M, quality, equipment, safety, other) with routing rules per
type — drawing issues route to PM + Lead Drafter and can carry an FC markup as
an as-built/clarification record [§9.1, §9.3]. **Un-parks A3** (punch list),
which dissolves into this item when it starts.

**Net-new and worth its own weight — Safety Hold** [§9.2]: *any* authorized
user can raise a safety issue (linkable to a project, release, assignment, or
person); accountability-chart roles are notified immediately; a stop-work
condition flips the connected assignment/release to **Blocked / Safety Hold**
across every view; **only a human leader clears it**, with resolution recorded
— Carmen tracks overdue safety items but never closes one or releases a hold.

**Trail**
- 2026-08-20 · spec · src fieldops-2026-08-20#§8–9 — punch lifecycle, field-issue categories + routing, universal safety issue + Safety Hold written; absorbs parked A3
- 2026-08-21 · decision · src bill-2026-08-21#L45 — **punch and field issues anchor to the RELEASE**, not the project ("any of that stuff should be to a release") — tightens the spec's "project required; release when applicable" for MHMW's actual use. Punch work on a finished release spawns a spliced work ticket — see T9
- 2026-09-14 · decision · src thisweek-2026-09-14#§3 — **field issues leave this item** as T11 (Release Issue & Error Register, package P0), release-anchored with department + cost. T6 keeps **punch** and **Safety Hold**. T11 v1 points at a Safety Hold that does not exist yet, which is a reason to pull Safety Hold's minimal form forward if the register lands first. T9's punch mirror card (package §6.1c) is the first punch artifact and will arrive before this item's lifecycle

### T7 · Subcontractor compliance profiles
*W5 · not-started · class build · due — · deps T2 · owner daniel · src fieldops-2026-08-20#§3.3 · upd 2026-08-20*

Effort M. Per-company profile holding work authorizations, insurance, workers'
comp, safety documentation, and a flexible extra-document type — each with
upload, effective/expiration dates, status, and renewal reminder. **Explicitly
a tracking-and-follow-up system in the first release, not a scheduling block**:
a PM sees the warning but is never prevented from assigning on an expired
document. Carmen surfaces missing/expiring documents, prepares the reminder
email, and logs the follow-up. Subs see and update only their own documents.

**Trail**
- 2026-08-20 · spec · src fieldops-2026-08-20#§3.3 — scope written: warn-don't-block, Carmen renewal follow-up, company-scoped visibility

### T8 · Sub work authorization + invoicing workflow
*W5 · not-started · class build · due — · deps T5,A1 · owner daniel · src fieldops-2026-08-20#§11 · upd 2026-08-20*

Effort L. The spec's **"A.1" phase** (sits where E would — whether that label
is a typo or a deliberate elevation behind Phase A is in the Owed
reconciliation row). Two halves. **Work authorization:** no sub receives a
release assignment without one — link an existing Sub Fab PO / subcontract or
create a lightweight record carrying company, project/release/scope, work
description, authorized value (visible only to authorized MHMW users + that
company), schedule commitment, and status Draft → Issued → Accepted → Active →
On Hold → Completed → Closed [§11.1]. **Invoicing:** sub drafts a payment
request against the authorization → submits with evidence (invoice PDF, daily
updates, photos, verified punch closeout, approved T&M) → PM + Field Super
review against assigned work (approve / partial / return / dispute with
reason) → Accounting sees the approved package and payment status. The system
validates **claimed ≤ authorized + approved changes** absent an authorized
override, and needs a **punch-work holdback** mechanism whose policy is still
open (Open question 4) [§11.2]. Approved invoices feed actual sub spend on the
project/release budget view.

**Inherits the I4 surface** — `installer_invoice_paid` / `_progress` /
`_numbers` on `Releases` (PR #339, plus the 2026-08-18 paid-behavior rework, `2ca3ff7`)
already track sub payment per release and caught ~$15k in week one. This item
is the structured workflow that surface was standing in for; reconcile rather
than duplicate, the same way N2b must.

**Trail**
- 2026-08-20 · spec · src fieldops-2026-08-20#§11 — authorization + invoice workflow written: no assignment without authorization, claimed-vs-authorized validation, punch holdback needed (policy open), evidence-backed review chain
- 2026-08-20 · note · src — — I4's Subs surface already covers the paid/progress slice; T8 formalizes the workflow around it
- 2026-08-21 · transcript · src bill-2026-08-21#L57 — intent hardened: *"I kind of want to **eliminate their invoices altogether**… they have to do it through the company's piece first"* — subs invoice inside the Brain, same format for everyone; a private copy in their own software is their business. Confirms the cover email's "system-generated MHMW PDF" as the doc's missing piece
- 2026-08-21 · transcript · src bill-2026-08-21#L51 — the remaining-value mechanic: at 90% progress the system offers "allocate remaining 10% of budget for this installation" against the spliced work ticket (T9), tying residual invoiceable value to whoever finishes the work

### T9 · Release splicing — fractional work tickets for the field
*W5 · in-progress · class build · due — · deps — (was T5,T6 — cut 2026-09-14) · owner daniel · src bill-2026-08-21#L45 · upd 2026-09-16*

> **Status 2026-09-16 — outcomes (a) and (b) shipped as numbered splices.**
> PR #380 (merged 2026-09-15) built `340.X` splices drawn from the original's
> install-hour pool; PR #383 (merged 2026-09-16) shipped Bill's 9/16 splice modal:
> Splices tab in the release hub with in-place navigation, required description ≠
> original + installer, stage and start install on create, **Budget Install Hours**
> from the pool and **additional install hours outside the pool with a required
> reason** (editable afterward). **Both migrations still to run:**
> `add_parent_release_id_to_releases.py` then `add_splice_additional_install_hrs.py`.
> **Left:** (c) punch mirror (T6 lifecycle / Open question 4), parent `comp_eta` on
> total vs remaining hours, what completing every splice means for the parent.
> **Test coverage was cut:** the pool-cap / splice-of-splice / number-reuse /
> PATCH-guard tests were deleted in #383 and have no replacement yet.

> **Elevated 2026-09-14 — package P2** [thisweek-2026-09-14#§6], third in
> `queue.next`. This reverses Bill's own 2026-09-02 "don't raise it" (trail below);
> the written package is the later word. The package pins a **Splice / Split Work
> action inside the release/assignment modal** with three outcomes:
> **(a) split existing hours** — move some of the original install hours to a new
> linked assignment; original + child totals equal the original budget;
> **(b) add additional hours** — a linked additional-install assignment carrying
> added hours separately, never silently reducing the original;
> **(c) create punch work** — a linked **punch mirror card**: the primary install
> can be marked Installed / Invoice-Eligible when accepted while the punch mirror
> stays under the responsible installer/sub until Final Complete / Closeout.
> Shared rules [§6.2]: each child stays linked to the same project + release with
> visible parent/child history; each child has its own crew/company, date,
> installer count, status, photos, **issues (T11)** and notes; moved/added hours
> update the right crew's Timeline capacity; **never a separate release** and never
> loses drawings/history (so no AUD2 collision — the child is not a release
> number); original / added / punch stay distinct for billing; Change Log records
> who spliced, when, hours moved or added, outcome, notes.
> **Deps cut:** T5's assignment records and T6's punch lifecycle are not built, and
> the package asks for this now — so the child is a **minimal controlled child of
> `Releases`** (the §9 boundary licenses exactly that) that T5 later generalizes,
> not a wait on T5. (a)/(b) match Bill's 9/2 "both directions" [bill-2026-09-02#L33];
> (c) is the first concrete punch artifact and pre-empts part of T6 — Open question
> 4 (does open punch block final complete / how is holdback computed) now bites
> here first.
> **Acceptance** [§8]: a card splits into existing hours, added hours, or a punch
> mirror, each preserving release lineage and correct capacity.

> **Tension to resolve with Bill (opened 2026-09-15):** the package above says the
> child is *never a separate release* and *not a release number*; the 2026-09-15
> decision and first build number it **`340.1`, `340.2`** as real job-log rows
> (Bill's own idea after `340.1` slipped in as a verbal release). The build
> delivers outcome **(a) split existing hours** only — pool-capped, lineage via
> `parent_release_id`, zero Trello. Outcomes **(b) add hours** and **(c) punch
> mirror** are not built and would need the pool rule relaxed (b) and T6's punch
> lifecycle (c). Whether the child stays a numbered release or becomes the
> package's non-release assignment child is the open call; the data model
> (`parent_release_id` on `Releases`) serves either.

Effort M–L. Bill's concept, volunteered when punch anchoring came up: a punch
or remaining-work item *"produce[s] effectively a **fractional or splice of a
release**"* [#L45] — an additional work ticket on the timeline carrying the
residual scope and value. His driving cases: a balcony-rail package where
floors 2–3 invoice while floor 1 waits; stair towers installed except the wall
handrail — flagged complete/90% in May, handrails installed in August, and the
last 10% of value needs an owner and an invoiceable number [#L51]. The splice
ties back to the Subs invoice-progress surface (Lexi's percentages, I4) so
"allocate remaining N%" is an offered action, not a spreadsheet.

**Field/timeline only** — Bill was explicit there's *"not really a lot of
function for that for the shop or anywhere else"* [#L45]. Design tension to
resolve at build time: a splice must not collide with the release-number
uniqueness ruleset (AUD2) or double-count value against the release's SOV line
(N1/N2 tagging) — the fab-only/install-split precedent is P5's FC Separator,
which stays parked but shares the apportionment shape.

**Trail**
- 2026-08-21 · transcript · src bill-2026-08-21#L45 — concept stated: punch/remaining work splices a fractional release as a field work ticket; balcony-rail and wall-handrail cases
- 2026-08-21 · transcript · src bill-2026-08-21#L51 — residual-value allocation ("allocate remaining 10% of budget") tied to the sub invoice-paid surface
- 2026-09-02 · transcript · src bill-2026-09-02#L2–L46 — named **"fractional install"** and shaped as a **mirror card**, numbered *"2 of 2", "3 of 2"* and onward. Install hours must split **both directions** — pull out of or add to the total — because which applies depends on whether it's a change order or billed against the original [#L33]. The **description is editable** so the fraction can be scoped (*"wall handrails only of this thing"*). Visible to the sub and on the sub tracking tab for invoicing, **not on the job log** — *"I don't think it needs to pop on the job log particularly"* [#L20]
- 2026-09-02 · decision · src bill-2026-09-02#L4 — **priority explicitly NOT raised.** Asked directly whether to bump it, Bill declined: it rides along with the sub/Trello backend work. `deps T5,T6` stand
- 2026-09-14 · spec · src thisweek-2026-09-14#§6 — **elevated by the weekly package (P2)**, superseding the 9/2 "not raised": Splice / Split Work action with three outcomes (split existing hours · add hours · punch mirror card), shared lineage/capacity/billing-distinct/Change Log rules
- 2026-09-14 · decision · src — — `deps T5,T6` cut: build the child as a minimal controlled child of `Releases` now, generalize under T5 later. Open question 4 now gates outcome (c)'s completion semantics
- 2026-09-15 · incident · src daniel-2026-09-15 — Bill created a **verbal release numbered `340.1`** in prod. Audit: not a validation slip — Release # is free-text by design (`String(16)`, the `V###` verbal convention; the paste validator only requires non-empty), so the dotted number was accepted as an opaque string with no link to 340. It then sat in the FABRICATION queue with no fab hours and its install hours were additive to 340's
- 2026-09-15 · decision · src daniel-2026-09-15 — **`340.X` dotted numbering supersedes the 9/2 mirror-card "2 of 2" shape; splices ARE on the job log.** Rules: the original carries fabrication and the TOTAL install-hour pool; each splice draws from that pool (sum never exceeds it, enforced on create and on every install-hours edit, both sides); a splice carries no fab hours; parent must exist — splices are created only from the original's modal (**+ Splice**, number derived server-side, description editable, install hours blank-to-fill); **no more `V` numbers expected**; start stage `Released` for now (likely `Install Start`, unconfirmed); **zero Trello interaction** (no card, no mirror, scanner skips them); prod `340.1` stays and is backfilled to its parent by the migration
- 2026-09-15 · built · branch audit/splice-behavior — `releases.parent_release_id` FK + `app/brain/job_log/features/splice/` (CreateSpliceCommand, pool math, PATCH guards), `POST/GET /brain/job-log/release/<id>/splice(s)`, paste path rejects free-typed dotted numbers, `SpliceReleaseModal` + Splices panel in the hub modal, `migrations/add_parent_release_id_to_releases.py` (idempotent, backfills dotted rows) — **migration not yet run**. Open: whether the parent's `comp_eta` should size on remaining rather than total hours (today the parent still schedules on the full pool), and what completing every splice means for the parent
- 2026-09-15 · open · src daniel-2026-09-15 — **conflicts with the 9/14 package's "never a separate release" rule** (see the banner). Built shape = numbered release child; package shape = non-release assignment child with three outcomes. Needs Bill's call before (b)/(c) are built; `parent_release_id` survives either answer
- 2026-09-16 · transcript · src bill-2026-09-16#L384–L417, L519–L567 — Bill demoed the numbered splice live (`640.1`, drawn from the parent's 51-hr pool) and asked only to extend it; the office (Andrea) found and adopted it unprompted. **Read as settling the banner tension toward numbered splices** — confirm with Bill before (c) punch
- 2026-09-16 · notes · src bill-2026-09-16 — **splice modal spec** (supersedes the audio's "install modal" discussion — it is the same modal): **own tab** at the top of the release hub [#L1581]; **original job-release / name / description read-only**; **new description required** and must differ [#L409]; **stage dropdown**; **optional start install date**; **required installer**; **additional-hours flag** — hours flagged additional come from **outside** the parent's budget pool (relaxes the pool cap for flagged hours only = outcome (b)) with a **required note** explaining why [#L494–L501]; install hours relabel **"Budget Install Hours"**
- 2026-09-16 · transcript · src bill-2026-09-16#L718–L737 — clicking a linked splice opens its modal **mirror-card style**, navigating back and forth; the buried Splices panel moves to the tab
- 2026-09-16 · merged · src pr#380 — the 2026-09-15 `audit/splice-behavior` build confirmed on `main` (merged 2026-09-15 21:53 MT, patch notes v2.0.380). Migration `add_parent_release_id_to_releases.py` **not yet run**
- 2026-09-16 · built · src pr#383 — **splice modal v2 shipped to `main`** (`feature/splice-modal`, patch notes v2.0.383), every item of the 9/16 spec: Splices tab (`SplicesPane.jsx`, count badge) replaces the Details panel; the hub swaps to a clicked group member in place with a header back button (frame stack in `ReleaseHubModal`, single row via `GET /brain/get-all-jobs?release_id=`); `CreateSpliceCommand` requires a description that differs from the parent's (case/whitespace-insensitive) and an installer, takes stage (fab_order tiered as a stage move) and a hard `start_install` (comp_eta computed). **Outcome (b) model:** a splice's `install_hrs` stays its total; new `additional_install_hrs` / `additional_install_note` hold the part outside the pool, and the pool counts `install_hrs − additional_install_hrs`. Additional hours are editable afterward (`PATCH /brain/job-log/release/<id>/splice/additional-hours` — budget fixed, total follows, recorded reason kept; Daniel: *"reason can stay the same"*). Migration `add_splice_additional_install_hrs.py` **not yet run**. 13 splice tests broken by the required fields plus 1 made hollow were **deleted at Daniel's call**, leaving 5; backend 1547 / frontend 369 green
- 2026-09-18 · built · src design-canvas "Splices Tab Facelift" (Option A) — **Splices tab facelift: the hours math on the page.** Bill, from the 555-551 test group: *"it would be great if we saw an hours math or subtotal type thing"*. Two directions drawn on a Design canvas, Option A chosen and built: one continuous bar, Original | Splices (a slice per splice that drew budget hours) | Additional, widths proportional to hours (2 : 10 : 14 of 26), with a legend under it; a statement-style ledger (pool − each splice = left on the original, + additional = group total); and the group as a table (Budget / Additional / Install / Fab columns, subtotal row) replacing the cards — the original's Install cell is what it still installs itself, so the column sums to pool + additional, never the gross. `pool_summary` now carries `additional_install_hrs` and `group_install_hrs` so the tab never adds a split up client-side. Additional hours still edit in place from the table. No migration — no schema change. src —
- 2026-09-22 · built · src handout-2026-09-21 — **zero-hour splice bug fixed** (the training handout's first "Watch for": *"Zero-hour splice bug (0 vs 0.0) can block create — use a small decimal or wait for the fix on true zero-hour / drop-ship cases"*). It was a guard, not a type quirk: `CreateSpliceCommand` refused budget 0 + additional 0, so a drop-ship or material-only splice could not exist without a fake 0.5. Now a zero-hour splice is legal: `install_hrs` stored as 0 (never NULL, which on a parent means "no pool"), nothing drawn from the pool, no pool needed, and the installer is required only when the splice carries hours. The + Splice form says "Zero-hour splice" in place of blocking, and the field-edit guard lets a splice's hours be edited to 0 (blank and negative still refused). Still open from the handout: billing tag on the splice form, Procore drawings not copied to the child, PM-only create (no PM role exists), a many-splices flag. No migration — no schema change. src —
- 2026-09-22 · built · src handout-2026-09-21 — **billing tag on the splice form** (handout step 8: *"apply the billing tag (MHMW vs customer) on the new row if needed — not in the splice form yet"*). + Splice now has a Billing tag select (Contracted / Change Order / MHMW Cost) pre-set to "Same as <original>"; `POST …/splice` takes `release_tag` (labels normalized like the paste path, bad values 400), blank inherits the original's as before. `pool_summary` and the create response carry `release_tag` on the original and every splice. No migration — no schema change. src —
- 2026-09-22 · built · src handout-2026-09-21 — **many-splices flag** (handout rule: *"Lots of splices on one job = problem flag (cleanup / scope creep). Exception: clarifying hold-downs by building"*). At 4+ splices under one original (`MANY_SPLICES_THRESHOLD`, `frontend/src/constants/splices.js`), the Splices tab shows an amber callout with the rule and the hub's Splices tab count turns amber. Display only — nothing is blocked; the threshold is a judgment call to tune with Bill. src —

### T10 · Job-log photos → Trello bridge *(interim)*
*W5 · not-started · class fix · due — · deps — · owner daniel · src bill-2026-08-21#L171 · upd 2026-08-21*

Effort S–M, feasibility check first. Doug's ask, relayed by Bill: push job-log
release photos onto the matching Trello card *"in the meantime"* [#L171] — a
per-photo **"add to Trello"** button is acceptable [#L175]. Not every photo:
fit-up photos are noise; **paint-complete and ship photos** are the valuable
ones, so the field guys see what they're looking for. The real motive is
adoption: today's Trello card only carries job-site photos, and Bill is
weaning the **shipping guy** onto the Brain — this bridges his gap until T1/T4
retire the boards. Daniel owes Bill the feasibility answer (Trello attachment
API via the existing outbox path looks plausible; unverified). **Deliberately
throwaway** — dies with T4; do not gold-plate.

**Trail**
- 2026-08-21 · transcript · src bill-2026-08-21#L171 — Doug's ask; "in the meantime" framing; Daniel to check feasibility and get back
- 2026-08-21 · transcript · src bill-2026-08-21#L175 — per-photo button acceptable; paint-complete/ship photos are the ones that matter; shipping-guy adoption is the motive
- 2026-09-14 · note · src thisweek-2026-09-14#§5.4 — the photos this bridge was for (paint-complete and ship) become **gated, captured evidence** under T13. If T10 is ever built, it should push T13's evidence sets, not arbitrary job-log photos — and the case for building it at all weakens once the shipping guy's photos live on the Timeline card

### T11 · Release Issue & Error Register
*W5 · in-progress · class build · due — · deps — · owner daniel · src thisweek-2026-09-14#§3 · upd 2026-09-16*

Effort L. **Package P0**, `queue.now`. An **Issues tab on the release hub** so
errors, field problems, quality failures, missing items, damage and rework are
recorded while still actionable — *"a usable record of errors before they become
hidden cost, rework, or blame without ownership"* [§2]. **Core rule: each issue
is its own linked record** — never one bulk note, one attachment pile, or one
cost total with no traceable cause [§3.1].

**Pulled forward out of T6.** T6 carried "field issues" (ten categories, routing
per type) behind T5; this is that idea, release-anchored (already decided
2026-08-21, [bill-2026-08-21#L45]), with cost and department ownership added, and
**no dependency on T5's assignment records**. Safety Hold and punch stay in T6.

**Record** [§3.3]: system ID tied to the 3-digit project + 6-digit release ·
title · **responsible department** (required; one primary + involved others;
drives notification and reporting) · accountable person (optional at create,
**required before In Progress**) · description (required) · **estimated cost**
(currency, with *Unknown/TBD* allowed, value history retained) · category
(Quality/Rework, Fabrication, Paint, Shipping/Delivery, Missing Product/Hardware,
Installation/Field, Drawing/Engineering, Material/Vendor, Customer/GC,
Subcontractor, Damage, Other) · priority Low/Normal/High/Critical · status
Open → Under Review → In Progress → Waiting on Others → Resolved → Closed
(Closed = final verified closure) · photos + PDFs **attached to the issue, not the
release** · created-by/at.

**Lifecycle** [§3.4]: timestamped comments with attachments and **@mentions** (the
board/PDF/DWL mention stack already feeds one bell — reuse it, BUG-17's PR #369
note); edits log who/when/prior value for cost, department, owner, priority,
status; original description retained; department routing lands in a
department/person work queue; design must leave room for a later **actual-cost**
field without a duplicate record.

**Visibility** [§3.2]: open-issue count + total known estimated cost on the hub
and on the **Timeline card**; a leadership/PM filter for releases with open issues
and total impact. Field/sub users may create issues only on releases they can see,
cost visibility follows the permission model — **that model is T2/T3's and is not
built**, so ship internal-only first and gate the sub path on T3.

**Guardrails** [§3.5]: does **not** block production or invoicing in v1; a PM /
Super / designated leader can decide an issue moves a release to Blocked / Safety
Hold. Carmen may summarize (by project, release, department, category, aging,
impact) and draft follow-ups, but never assigns blame, closes an issue, edits cost,
or declares a release safe.

**Three things to settle at build time:**
1. **"Department" is not a concept in the codebase.** `User` has role flags, not a
   department; there is no accountability chart in the DB. A fixed department list
   is the minimal answer — confirm the list with Bill.
2. **Safety escalation points at a workflow that does not exist.** The acceptance
   test wants the form to *direct the user to create the immediate Safety Hold* —
   Safety Hold is T6, not started. v1 can only direct to a phone call / named
   person; say so rather than fake a button.
3. **Storage.** Issue attachments are per-issue files — they want the same object
   storage decision as photos (K3), not a new local-disk root (see
   `project_backup_infrastructure`: two ephemeral roots already bit once).

**Acceptance** [§3.6]: two issues on one release stay fully separate; cannot save
without title + department + description, and saving notifies the department;
attachments on Issue A appear only on A; a cost edit keeps prior amount/user/time;
comments + tag + Open → In Progress → Resolved keep a full timeline; hub and
Timeline card show the right open count and the PM filter returns total open
impact; an unsafe condition routes to Safety Hold without losing the issue.

**Trail**
- 2026-09-14 · spec · src thisweek-2026-09-14#§3 — package P0: per-release issue register with department routing, estimated cost + history, per-issue evidence, comments/mentions, open-count on hub and Timeline card; no auto-blocking in v1; Carmen read/summarize only
- 2026-09-14 · decision · src — — filed as its own item rather than as T6 scope: the package ranks it P0 and it needs none of T5's assignment records. T6 keeps punch + Safety Hold
- 2026-09-14 · note · src — — found: no department model and no Safety Hold exist; sub-side create depends on the unbuilt T3 walls — ship internal-first
- 2026-09-15 · decision · src — — build-time answers (Daniel): **departments = fixed list Drafting / Paint / Fab / Ship/Install**, a required label only — no routing, no department notifications, no assignment yet (`accountable_user_id` column carried, unused); **Safety Hold escalation deferred** pending more workflow information; **attachments on the persistent disk** beside photos (`RELEASE_ISSUE_STORAGE_ROOT`, derived sibling `release_issues/`), moving with K3; **admin-only**; mentions are the only notification path
- 2026-09-15 · build · src — — first slice built on `feature/issues-registry`: `ReleaseIssue` / `ReleaseIssueComment` / `ReleaseIssueChange` / `ReleaseIssueAttachment` + two `notifications` columns; admin routes in `app/brain/release_issues/`; Issues tab on the release hub (list with open count + open est. cost, create form, detail with editable fields, per-issue evidence, merged comment + change timeline, @mentions → bell → hub deep link). Change history covers title, description, department, category, priority, status, cost; original description kept. **Not in this slice:** Timeline card count + PM filter, Safety Hold, assignment/department routing, Carmen, sub access. No tests written (by instruction). Migration `migrations/add_release_issues.py` written, **not yet run**
- 2026-09-15 · build · src — — issue actions now land on the release's event stream (`create_issue`, `update_issue`, `add_issue_attachment` ReleaseEvents rows) so Change Log and the Activity rail show them; comments stay on the issue timeline. Timezone checked: Change Log + Activity were already Mountain (server pre-formats `/brain/events`; verified the string parses as MT in Safari's JavaScriptCore); the new Issues pane was showing naive UTC and now renders America/Denver. Side fix: the Activity rail's sentence fallback (photos, drawings) was appending " cleared"
- 2026-09-15 · tests · src — — coverage written on request: `tests/release_issues/` (60 — service validation/numbering/history/mentions/summary/release events; routes admin gate, 400/404s, attachment isolation, file types, soft delete; storage-root derivation) + 4 vitest files (18 — issue event sentences, rail sentence kind, Mountain-time parsing, issue notification routing). Existing hub/rail/feed/notification suites re-run green. The hub's two test files had `utils/auth` mocks missing the new `readCachedRoleFlags` import; first pass worked around it by dropping the cached-role first paint, Daniel reversed that — the optimistic paint (AppShell's pattern) is restored, the mocks completed, and five admin-gate tests added (cached admin paints immediately, uncached waits for checkAuth, non-admin never sees it, no releaseId drops it, pane mounts + tab count)
- 2026-09-16 · transcript · src bill-2026-09-16#L129–L271 — first live walkthrough with Bill + Louie: *"This is sick"*. Asks: **auto-notify the release's PM** on create [#L154]; an **explicit owner** distinct from @mention — owner makes it theirs, mentions stay for updates [#L155, #L1594–L1597]; **"resolved at no cost"** marker [#L190]; issues feed the to-do / open-items surface (N19) [#L168]; **dictation** (mic → text) in data-entry fields [#L236–L244]
- 2026-09-16 · transcript · src bill-2026-09-16#L418–L464 — **estimated cost = hours + materials + total**, not one dollar field — Louie estimates in hours; materials later from an estimate-template dropdown
- 2026-09-16 · notes · src bill-2026-09-16 — owner may be **any user, subs eventually** (T3); the weekly **FC-error report** off issues [#L185] is **deferred**; BUG-29 (mention missing from to-dos) and BUG-28 (PDF modal load) filed off this walkthrough

### T12 · Release flow on the Timeline — Paint Complete queue, Drop Ship Only, load order
*W5 · in-progress · class build · due — · deps — · owner daniel · src thisweek-2026-09-14#§5.1 · upd 2026-09-17*

**① and ② BUILT 2026-09-17; ③ load order not started.**

Effort M–L. **Package P1**, head of `queue.next`. Three asks that stop releases
sitting in the wrong queue and let shipping plan a day in order. All three build on
T1's shipped surface (`GanttChart.jsx`, the Unassigned tray, `shipLaneDrop`).

**① Paint Complete queue** [§5.1] — a left-side vertical column *"similar to the
existing Unassigned tray"* holding releases at **`Paint Complete`** eligible for
shipping planning; drag into Shipping Planning **updates the stage** (logged); a
live view of the same record, never a copy; ASAP cards prioritized inside it.
**Overlap to resolve first:** the Unassigned tray's membership already includes
`Paint Complete` (`READY_TO_SHIP_STAGES`, `utils/unassignedLane.js:33` — the
2026-08-29 rule), so a Paint Complete release with no installer would show in
**both** columns. Either the Unassigned tray drops `Paint Complete` from its intake
(narrowing Bill's own 2026-08-29 rule) or the two are one tray with sections.
Also check the drop against N5's intercept: **`Paint Complete` + a hard date
already auto-rolls to `Ship Planning`** (`stage/command.py`), so hard-dated
releases may never sit in this queue at all. **See Open question 7.**

**② Drop Ship Only** [§5.2] — an assignment choice for releases fabricated and
shipped with **no MHMW install**: its own Timeline lane/destination, consumes no
installer capacity, leaves the Unassigned queue, stays fully linked (drawings,
photos, shipping, billing), and progresses through shipping and closeout **without
being falsely marked installed/complete**. Change-logged. **Net-new field** — there
is no install-type or product-type attribute on `Releases` today
(`project_tee_time_scheduling`), so this is a column + migration. The closeout path
is the hard part: `COLOR_DUMP_STAGES`, `job_comp` cascades and the archive rule
(`stage='Complete' AND job_comp='X' AND invoiced='X'`, PR #344) all assume an
install happened — decide what "complete" means for a release that never installs
before touching those rules.

**③ Shipping load order** [§5.3] — vertical reorder of Shipping Planning cards
within a day, persisted as an explicit **load number for that date**, displayed as
**Load 1 / Load 2 / Load 3**, carried into any dispatch view or export; reordering
never changes ship date, install date, stage or capacity. Net-new column (e.g. a
per-date sequence on `Releases`) + migration; today's in-cell order is computed
(`GanttChart.jsx:213`, ASAP first then job/release #). A date change must decide
what happens to the load number (clear, or append to the new day).

**Acceptance** [§8]: a Paint Complete release appears in the left queue and drags
into Shipping Planning without a duplicate; a no-install release moves Unassigned →
Drop Ship Only, consumes no crew capacity, still ships and closes out; five
same-day shipping cards keep a manual Load 1–5 order after refresh with no date
change.

**Trail**
- 2026-09-14 · spec · src thisweek-2026-09-14#§5.1–5.3 — package P1: Paint Complete queue, Drop Ship Only assignment + lane, persisted shipping load order
- 2026-09-14 · note · src — — found: Unassigned tray already takes `Paint Complete` (double membership); N5's hard-date intercept moves Paint Complete rows to Ship Planning automatically; no install-type field exists; in-cell order is computed, not stored — two migrations expected (drop-ship flag, load sequence)
- 2026-09-16 · transcript · src bill-2026-09-16#L31–L72 — **`Paint Complete` is renamed `Paint QC`** and sorts **above Store** on the Ready to Ship filter (*"hot top, cold bottom"*). Shipping Planning keeps its name and top-of-list place. Rename touches `STAGE_TO_GROUP`, `FIXED_TIER_STAGES`, the Trello list mapper, N5's intercept, the stage-photo-gate constants and the Unassigned intake
- 2026-09-16 · transcript · src bill-2026-09-16#L1113–L1358 — ① reshaped as a **Ready-to-Ship column** pulling **Paint QC + Store**; droppable **only onto Shipping Planning or Ship Complete**; a drop on Shipping Planning sets the stage **and `start_install` = next business day** (Ship Complete = same day as install) [#L1336–L1358]. Paint QC → Shipping Planning has **no fixed gap** (a day to three months) [#L1280–L1297]. **ASAPs at any stage** show at the bottom of the column [#L1343]. Bill on the 1-day rule: an unassigned drop lands in Unassigned and dragging onto an installer fixes the date, so one day is right [#L1188–L1222]
- 2026-09-16 · transcript · src bill-2026-09-16#L1360–L1417 — **symmetry rule:** setting a hard date on a Ready-to-Ship-stage release from the table auto-moves it to Shipping Planning — same result as the drag. N5 already does this for `Paint Complete`; extend to `Store at MHMW`. Partly answers **Open question 7**
- 2026-09-16 · transcript · src bill-2026-09-16#L1598–L1617 — ② Drop Ship: Bill's read is a **normal installer-style lane at the bottom** of the Timeline (Doug's ask)
- 2026-09-17 · build · src — — **① Ready-to-Ship column and ② Drop Ship lane built** on `claude/loving-cori-gy8xr1`. ③ load order untouched.
  **Open question 7 answered by narrowing the tray's DATE test, not its stage set** — the third
  option neither side of the question offered. `isUnassigned` now also requires a hard Start install
  (Ship Planning rows excepted, since N5 can legitimately leave one undated), so the tray keeps
  `Paint Complete` in its 2026-08-29 intake and the two columns are disjoint anyway. The pipeline
  reads left to right: Ready to Ship (no day yet) → dropped on Shipping Planning, which gives it one
  → Unassigned (no crew) → dropped on a crew lane. No duplicate, and Bill's own rule survives intact.
  **The hard-date intercept worry was the right question with the answer inverted:** N5's intercept
  fires on a STAGE change, so it never pre-empted this queue — a `Paint Complete` release that is
  dated while already at `Paint Complete` just sat there. The symmetry rule (#L1360–L1417) is now a
  real cascade, `features/start_install/ship_planning_roll.py`, firing off the DATE for both
  `Paint Complete` and `Store at MHMW`, on the FIRST hard date only, never on an undo. It emits the
  stage change as a CHILD event of the date event, so one Undo reverses the whole gesture — which
  needed `parent_event_id` adding to `UpdateStageCommand` (it already existed on
  `AssignInstallerCommand`). Every writer of a hard date routes through `UpdateStartInstallCommand`,
  so the Job Log table, the release hub and the Timeline drag all get it from that one place.
  **"start_install = next business day" resolved as the lane's own arithmetic, not a fixed offset:**
  a Shipping Planning card is drawn on its SHIP date (install − 1 business day), so the column the
  user drops on is a ship day and the install is the business day after it. Writing the column date
  straight into `start_install` would have rendered the card one column LEFT of where it was let go.
  **Out-of-department ASAPs included** (#L1343) and tagged with an "in Fab" / "in Paint" chip, sorted
  below the in-shop holds exactly as the Job Log's `propagatedAsapJobs` block is; `PAINT_STAGES` now
  has one definition, shared by both surfaces. **Not built, deliberately, as out of today's ask:**
  the drop restriction (*droppable only onto Shipping Planning or Ship Complete* — a Ready-to-Ship
  card can still be dropped on a crew lane, which dates and assigns it in one go), the Ship Complete
  drop writing `start_install` = same day, and the `Paint Complete` → `Paint QC` rename with its
  sort flip above Store.
  **② Drop Ship needed no migration** — the 2026-09-16 ruling (a normal lane) supersedes the
  net-new-field reading, so it is a roster entry: `Config.NON_TRELLO_INSTALLERS` appended last to
  `INSTALLER_TEAMS` and always present, so an env var that forgets it cannot make it unassignable.
  It gets its Timeline lane, its install-schedule column and the installer picker for free.
  `AssignInstallerCommand` skips the mirror-card outbox item for it entirely — delivery resolves the
  target list BY NAME, so queueing one would guarantee five failed retries and an ERROR per
  assignment. Hidden from Subs → Invoice Paid beside Oscar (no company, nobody to invoice).
  **Consequence to be aware of:** the mirror card is left wherever it was, so reassigning a release
  from a real crew to Drop Ship leaves a stale card in that crew's Trello list until T4. That is the
  literal reading of "will not communicate to Trello"; the alternative (treat it as Unassigned and
  move the card there) is one line if the stale card turns out to matter.
  **Closeout path untouched** — `COLOR_DUMP_STAGES`, the `job_comp` cascade and the archive rule
  still assume an install happened. A Drop Ship release is not yet exempt from any of them.
  | `frontend/src/utils/readyToShipColumn.js` (new), `utils/unassignedLane.js`, `utils/shipLaneDrop.js`, `components/GanttChart.jsx`, `hooks/useJobsFilters.js`; `app/brain/job_log/features/start_install/ship_planning_roll.py` (new), `.../start_install/command.py`, `.../start_install/assign_installer.py`, `.../stage/command.py`, `app/config.py`, `app/brain/subs/service.py`
- 2026-09-17 · note · src — — **existing tests encode the old tray rule and now fail**: `frontend/src/utils/unassignedLane.test.js` and `components/GanttChart.staging.test.jsx` both place undated `Paint Complete` / `Store at MHMW` rows in the Unassigned tray. They are asserting the duplicate-membership behaviour ① exists to remove, so they need rewriting to the new split, not reverting. Not done in the build session (tests explicitly out of scope there)

### T13 · Two-stage Photo Evidence Gate + partial shipments
*W5 · not-started · class build · due — · deps — · owner daniel · src thisweek-2026-09-14#§5.4 · upd 2026-09-16*

Effort L. **Package P1.** A **controlled status gate**, not a reminder: moving a
release to **`Paint Complete`** or to **`Ship Complete` / Shipped** cannot finish
until there is a photo set **or** a documented Photo Exception [§5.4.1]. **Shipping
Planning is deliberately ungated** — it stays a flexible planning stage.

- **Paint Complete Evidence modal** — ≥1 photo of the finished painted product,
  current shop/staging **location**, attestation that the pictured product is this
  release.
- **Shipment Completion Evidence modal** — ≥1 photo of loaded/dropped/delivered
  product, actual location, **Full Release or Partial Shipment** (+ short
  description when partial), attestation the photos cover what left MHMW.
- **Photo Exception** — written reason + current location; visible on the
  card/release, logged with user + time + stage, lands in a **photo-exceptions
  queue**. A status change must *never* silently bypass the gate.
- **Evidence fields** [§5.4.2]: multi-photo (mobile/tablet/desktop); location type
  (Shop/Staging, Truck/Trailer, Job Site, Vendor/Pickup, Other) + free text (bay,
  trailer, building, level, unit, gridline, laydown); auto date/time/user, manual
  edits need an auditable reason; everything linked to project + release.
- **Partial shipments** [§5.4.3] — each movement is its own **Shipment Event**
  (*Shipment 1 of 3*, *2 of 3*, *Final Shipment*), never overwriting the first set;
  the release reads **Partially Shipped** (or stays in shipping planning) until the
  final event moves it to Ship Complete; events tie to the ship date and T12's load
  sequence; the card shows a shipment-history count + link.
- **Visibility** [§5.4.4]: hub + shipping card show photo-evidence count, current
  location, shipment scope/status, latest Paint Complete evidence, active
  exception; installers/subs opening the work package see location + shipment
  photos. Carmen surfaces open exceptions, missing evidence, and releases Partially
  Shipped past a configurable period — never invents a location or clears an
  exception.

**Absorbs J1** (photos at paint complete as an invoicing gate) — this *is* that
gate, built as a stage gate. **Delivers N9's deferred "stage-change gate"** — the
2026-08-21 answer to the photo-before-stage race was "ship it, then see; a gate is
the future fix" [bill-2026-08-21#L81], and the gate is now the ask. N9 (the stamp)
stays its own item but must render off these evidence photos: build the capture
path once. Photo storage already exists (`ReleasePhoto`, `app/models.py:1193`;
PR #349 client-side compression, which strips EXIF — N9's note applies here too).

**A v0 of this gate already exists, switched off.** `adb0937` (2026-06-07) added a
stage photo gate on **`Welded QC` and `Paint Complete`** — server-side in
`UpdateStageCommand` (`STAGE_PHOTO_GATES`, raises `StagePhotoRequiredError` →
`422 photo_required`, checks a `ReleasePhoto` tagged with that stage, skipped on
undo, evaluated *before* the N5 intercept so a rerouted Paint Complete still needs
its photo) with a matching frontend upload-modal flow in `JobsTableRow.jsx:35–40,
481, 539`. **`d63146d` disabled it the same day** behind
`STAGE_PHOTO_GATE_ENABLED = False` on both sides, *"keep all photo infra"*. So T13
is an **extension of a parked mechanism, not a greenfield gate**: flip the flag,
swap `Welded QC` for `Ship Complete` (the package gates only Paint Complete and
Ship Complete — confirm Welded QC is really dropped), add location + attestation
+ the exception path, and add the shipment-event model. **Find out why it was
turned off on 2026-06-07 before turning it back on** — the commit message gives
no reason, and whatever made it unworkable then (probably the same crew friction
the exception path is now designed to absorb) is the first risk now.

**The hard part is the writers, not the modal.** A gate that lives in one command
is a gate the other writers skip — the BUG-22 lesson, three for three. Today's
stage writers: `UpdateStageCommand`, the **inbound Trello list move**
(`sync.py`), and the Install Prog branches. **Trello can move a card to "Shipping
completed" with no modal and no photos**, and inbound lands `Ship Complete`
(`list_mapper.py`). While Trello lives, the gate is unenforceable on the path the
shop actually uses — so decide: refuse and bounce the Trello move, accept it and
auto-raise a Photo Exception ("moved in Trello, no evidence"), or accept that T13
only fully closes at T4. **See Open question 6.** Same check for N5's
`Paint Complete` hard-date auto-roll to Ship Planning, and for undo of a gated
transition. **"Partially Shipped" is a new state** — decide whether it is a stage
value (touches the Trello list mapper, stage order and `COLOR_DUMP_STAGES`
integrity test) or a derived flag over `Ship Planning`; the flag is cheaper and
keeps every existing stage rule intact. Two new tables expected (evidence
set/shipment event, photo exception) + migration.

**Acceptance** [§5.4.5]: Paint Complete cannot finish without photos + location or
an exception; same for Ship Complete; an exception shows reason/location/user/
time/stage and sits in the exceptions queue; a partial shipment creates Event 1,
keeps the release Partially Shipped, allows Event 2 without overwriting; the final
event moves to Ship Complete keeping all prior events; an installer/sub sees
location + shipment photos in the work package.

**Trail**
- 2026-09-14 · spec · src thisweek-2026-09-14#§5.4 — package P1: gates at Paint Complete and Ship Complete (photos + location, or a logged exception), Shipping Planning ungated, per-movement shipment events, exceptions queue, Carmen follow-up
- 2026-09-14 · decision · src — — J1 dissolves into this item; N9's deferred stage-change gate is delivered here; N9's stamp renders off these photos rather than a second capture path
- 2026-09-14 · note · src adb0937 — found: a stage photo gate on Welded QC + Paint Complete was built 2026-06-07 and disabled the same day (`d63146d`, `STAGE_PHOTO_GATE_ENABLED = False` FE+BE), infra kept. T13 extends it; the reason it was switched off is unrecorded and is the first thing to recover
- 2026-09-14 · note · src — — found: the inbound Trello list move writes `Ship Complete` with no Brain UI, so the gate cannot be enforced there while Trello lives (Open question 6); "Partially Shipped" has no home in the stage model yet
- 2026-09-16 · transcript · src bill-2026-09-16#L1–L112 — Bill opened the session on it: *"a QC at every stage change going forward… red stars… you can't ever click the button to say submit it or change stage"* [#L2–L9]; *"as soon as I click welded QC, that's going to pop up and say prove it"* [#L80]. Shape: **photo required, note optional** [#L92]; **"no photos available" forces a comment** — the Photo Exception [#L111]; a short **per-department checklist** (~4 facts: complete package, all parts photographed, misc/hardware accounted for) [#L15–L30]; gate data lands in the normal description/photos, not a side store [#L81]; **markup on photos** with the PDF tool [#L95–L104]
- 2026-09-16 · transcript · src bill-2026-09-16#L30, L80 — gates named: **Welded QC** and **Paint QC** — answers the 9/14 *"confirm Welded QC is really dropped"*: **it is not**; the parked v0 (`adb0937`, Welded QC + Paint Complete) was the right pair
- 2026-09-16 · notes · src bill-2026-09-16 — behavior confirmed; it is a **cross-department** check fired on a **stage-group boundary** crossing (`STAGE_TO_GROUP`: FABRICATION → READY_TO_SHIP lands on Welded QC; READY_TO_SHIP → COMPLETE lands on Ship Complete). **Paint QC sits inside READY_TO_SHIP**, so a pure group rule misses the second gate Bill named — **Open question 8**. Per-department checklist items owed by Bill/Louie

### T14 · iPad / PC parity
*W5 · not-started · class build · due — · deps — · owner daniel · src thisweek-2026-09-14#§7 · upd 2026-09-14*

Effort M. **Package P3.** *"The iPad must be a dependable field operating view, not
a stripped-down version of the PC screen"* [§7]. Five asks: the **same blue
collapsible left-side menu** as PC; the **same top filters, primary buttons and
actions** on Job Log and Timeline; usable in **landscape and portrait** without
hiding critical filters; **rotation/responsive changes never close an active
modal, discard unsaved work, or lose scroll/filter context**; a user can finish
normal Job Log, release-hub, photo, date and Timeline tasks without going back to
a PC.

**What's in the way, from the record:** the left icon rail only mounts at
**≥1440 px** (Job Log redesign, `project_job_log_redesign`) — every iPad is below
that in both orientations, so the "blue collapsible menu" is absent by design and
the fix is a collapsible rail at tablet widths, not a style tweak. The rotation
half is **BUG-14, whose re-check trigger has now fired** (dropped 2026-09-04 *"unless
we hear otherwise"* — this is hearing otherwise): the build is on `main`, the
physical-iPad verification is what's owed, and it extends to unsaved form state,
not just the open hub and scroll. PR #376 (2026-09-14, *"much improved mobile view
for timeline"*) just moved this surface — start from it. The ~10 native-HTML5-drag
components in `docs/tablet-tuning.md` are the parity backlog behind "Timeline
tasks from the iPad". **Needs the physical iPad on the desk** — same device gate as
T1's drag proof and BUG-14.

**Acceptance** [§8]: blue collapsible menu, top filters and main Job Log/Timeline
actions usable on a current iPad in landscape and portrait.

**Trail**
- 2026-09-14 · spec · src thisweek-2026-09-14#§7 — package P3: menu, filters and actions at parity; orientation-proof state; full task completion on iPad
- 2026-09-14 · note · src — — BUG-14's re-check trigger fired (rotation must not close a modal or lose context); rail is ≥1440 px only today, so tablet widths need a collapsible rail; physical-iPad gate shared with T1/BUG-14

---

## Workstream 0 — Preconditions

### K4 · Backups — Postgres + binary disk
*W0 · in-progress · due — · deps — · owner daniel · src — · upd 2026-08-09*

Effort S–M. The Postgres portion is **done and verified 2026-08-09**: cron live,
first prod backup run, and the **recovery drill passed** — restored
off-platform, schema-verified, app booted, so the backup is proven rather than
believed. The original Tier 0 premise was wrong: Postgres PITR (3-day window)
had been on since before 7/22 — the database was never unrecoverable. The binary
disk genuinely had nothing and now has an offsite tiered backup to R2
(`mhmw-data`), verified end-to-end against sandbox, runbook merged and
corrected. **Blobs are deferred**: Procore still carries the PDFs/photos, so
binary coverage folds into the K3 / data-lake work — that remainder is why this
stays in-progress.

**Trail**
- 2026-08-06 · note · src — — entered the roadmap as a Workstream 0 precondition on the premise that nothing was recoverable
- 2026-08-09 · note · src — — offsite tiered backup to R2 (`mhmw-data`) built, verified end-to-end against sandbox; runbook merged and corrected; work surfaced and fixed a live data-loss bug (two storage roots writing to ephemeral paths); found Postgres PITR had been enabled since before 7/22 — Tier 0 premise wrong
- 2026-08-09 · note · src — — Postgres portion verified: cron live, first prod backup run, recovery drill passed (restored off-platform, schema-verified, app booted)
- 2026-08-09 · decision · src — — blobs deferred: Procore still carries PDFs/photos; binary backup folds into the K3 / data-lake work

### K3 · Object storage migration + cost numbers
*W0 · not-started · due — · deps — · owner daniel · src bill-2026-08-06#L662 · upd 2026-08-09*

Effort L — size generously. Every binary sits on one Render disk; Procore's
document history does not fit that shape. Bill asked for cost numbers on the
record. **Blocks P7, C3, and P11** — every submittal binary lands wherever this
decides, so K3 · P11 · C3-narrow · archival policy move as one cluster.
Archival policy is agreed: closed projects keep metadata + a text record,
drawing files get dropped; retention posture is *"handle as much as possible
and slide irrelevant data out as those things become more clear"* — prune
later rather than filter on the way in. R2 was provisioned 2026-08-09 for K4,
so storage cost is now a known sub-$1/mo figure; the open part is the blob
migration decision, not the vendor. This is `queue.now`.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#L662 — Bill asked for the storage cost numbers on the record
- 2026-08-06 · transcript · src bill-2026-08-06#L666 — archival policy agreed: closed projects keep metadata + text record, drawing files dropped; retain generously, prune as clarity comes
- 2026-08-09 · note · src — — R2 provisioned (`mhmw-data`) via the K4 work; storage cost now a known sub-$1/mo figure; the open part is the blob migration, not the vendor

### N4 · Two-calendar business-day fix + 26-call-site audit
*W0 · built · due — · deps — · owner daniel · src notes-2026-08-04#notes · upd 2026-08-09*

**Built 2026-08-09** (in the v2.0.338 wave). `app/trello/utils.py:37` now
carries `CALENDAR_FIELD` (Mon–Fri) and `CALENDAR_SHOP` (Mon–Thu);
`is_business_day`, `add_business_days`, and `calculate_business_days_before`
all take `calendar=`. The audit — which was the actual job — ran: fab and
paint math moved to the shop calendar in `schedule_builder.py` (lines
210–295) and `job_log/scheduling/calculator.py` (166, 190), while install and
ship math stayed on the field calendar (`calculator.py:245`,
`schedule_builder.py:262`). Tests: `tests/test_business_day_calendars.py`;
`scripts/compare_fab_calendars.py` diffs old vs new projections.
**Caveat worth carrying:** the drafting-deadline sites
(`drafting_work_load/service.py:200,299`) and the ASAP +1wk anchor
(`job_log/routes.py:1788`) still take the default field calendar implicitly —
correct by default, but they were never explicitly decided. **This unblocks
E1–E3** (tee-time), which were parked behind it.

*The pre-build statement, retained for the record (2026-08-06):* MHMW runs two working calendars — shop (fabrication, paint) is
Mon–Thu 4×10s, permanent; field (ship, install) is Mon–Fri; drafting/admin
Mon–Fri unless corrected — and the code knows about neither. The single
business-day helper (`add_business_days` and friends,
`app/trello/utils.py:257`) is hardcoded Mon–Fri and has **26 call sites**;
everything downstream (`comp_eta`, drafting deadline, ship-date auto-fill,
`schedule_builder.py`, tee-time projection) computes on the wrong week. Work:
add a calendar parameter, then audit all 26 call sites and decide which
calendar each wants — **the audit is the job, not the helper**. The measured
~400 hrs/wk fab throughput is already 4-day-aware and does not need
re-deriving. Gates E1–E3 (parked): calibrating on the wrong week means
calibrating twice.

**Trail**
- 2026-08-04 · note · src notes-2026-08-04#notes — surfaced as "lookahead schedule dates are wrong"; it is not a lookahead bug
- 2026-08-06 · decision · src — — made a precondition of E1/E2/E3 (collapse ④): the projection math runs on a Mon–Fri week for a Mon–Thu shop
- 2026-08-09 · build · src pr#337-wave — two-calendar model landed (`CALENDAR_FIELD`/`CALENDAR_SHOP`, `calendar=` on all three helpers); fab/paint audited onto the shop calendar, install/ship left on field; tests + `compare_fab_calendars.py` shipped; E1–E3 unblocked
- 2026-08-09 · note · src — — drafting-deadline and ASAP-anchor call sites still ride the default field calendar by omission, not by decision

### MIG · Outstanding migration backlog per environment
*W0 · in-progress · due — · deps — · owner both · src — · upd 2026-08-10*

Effort S–M, standing item — in-progress by nature, not by debt. **The named
backlog is currently clear:** three migrations confirmed run 2026-08-10 —
`releases_unique_job_release_name.py` (BUG-3), `add_release_tag.py` (N1),
`add_installer_invoice_progress_and_numbers.py` (I4). One older claim is *not*
covered by that confirmation and stays open: the 2026-08-06 note that A1 alone
shipped five unrun migrations — unverified per environment, worth an
inventory pass rather than an assumption. Workstream 1 adds more. Scripts are
handed over per the usual split (Daniel writes, client runs).

**Trail**
- 2026-08-06 · note · src — — standing backlog established; A1 alone shipped five unrun migrations
- 2026-08-06 · build · src pr#327 — bug wave added `releases_unique_job_release_name.py` (BUG-3 fix); run state to be verified per environment
- 2026-08-10 · note · src — — three migrations confirmed run by Daniel: `releases_unique_job_release_name.py`, `add_release_tag.py`, `add_installer_invoice_progress_and_numbers.py`; the A1-era five remain unverified

---

## Workstream 1 — Procore exit ~~(October)~~ · **DEFERRED 2026-08-15**

> **Every item in this section carries `class deferred` as of 2026-08-15.**
> Procore was renewed; the absolute dead date is **October 2027**. The whole
> ecosystem comes off the active path as one block — P0, P1, P2, P4, P7, P10,
> P11, plus C3-narrow and D1-minimal below. Item bodies are retained unedited
> for when the lane reopens; their `upd` dates are deliberately left at
> 2026-08-06 because nothing about the *work* changed, only its timing.
>
> **Re-check trigger:** W5 substantially complete, or Q1 2027 — whichever comes
> first. **P11 is the exception that cannot wait for either** (see its entry).
>
> The 2026-08-06 framing, retained: Bill drew the boundary himself — *"brain
> projects, brain submittal handling, and ball-in-court workflow is the absolute
> core need to have before October"* [bill-2026-08-06#L802] — and invited-user
> access to customers' Procore survives the lapse [#L811], which keeps
> plan-document hosting off the critical path. Full data model in
> `docs/procore-decommission-plan.md`.
>
> **One open thread the deferral does not stop:** submittals and releases are
> converging in practice. P1 (extend `Submittals` into the native record) was
> this roadmap's vehicle for that unification, and it is now inside the deferred
> block — but the convergence continues as a direction anyway, which is why AUD2
> is scoped to survive the merge rather than hard-code today's two-model split.

### P1 · Extend Submittals — contract_scope_id, parent_id, phase, state, source
*W1 · not-started · due — · deps — · owner daniel · src bill-2026-08-06#notes · upd 2026-08-06*

Effort M. **No new table** — `Submittals` *is* the native record (resolved
2026-08-06). The existing model gains `contract_scope_id`, `parent_id`,
`phase`, `state`, and a `source` discriminator (Procore vs Brain). The
consequence is large: the 3,892 legacy rows need no migration at all — they
become rows with a null `parent_id` and a `phase` derived from the existing
`type`, and everything downstream (DWL filtering, Rel assignment,
`start_install`, `linked_release_id`) keeps working untouched. Opens
Workstream 1; queued after the P11 delta inventory.

**Trail**
- 2026-08-06 · decision · src bill-2026-08-06#notes — extend, don't replace: no new BrainSubmittal table; existing model gains contract_scope_id, parent_id, phase, state, source
- 2026-08-06 · decision · src bill-2026-08-06#notes — cut-over gate is the project, not the submittal: new projects originate in the Brain, running projects stay; 660 Fox Hill fits exactly as the pilot (645 backup)

### P0 · Project origination — Contract Scopes + context doc + must-check notes
*W1 · not-started · due — · deps P1 · owner daniel · src bill-2026-08-06#L1036 · upd 2026-08-06*

Effort M. Project creation sets up Contract Scopes and takes a **context
document** — the context doc and the must-check notes are **one document**,
uploaded at creation (Claude-Projects style). It carries project context and
the must-haves-to-verify Bill asked for right after the intumescent-paint
story. This is the cheap version of Mission Brief (pushed to phase three
because it needs estimate parsing, drawing clips, historical retrieval) and
gives the estimate-derived version somewhere to land later. Absorbs catalog A5
and note N3 (collapse ①). "Contract Scope" is the final term — singular
*Contract*, never Spec Section / Scope Breakdown / CSI language.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#L1036 — must-check notes asked for immediately after the intumescent-paint story [#L1021]
- 2026-08-06 · transcript · src bill-2026-08-06#L1019 — Mission Brief pushed to phase three; manual context upload is the cheap version
- 2026-08-06 · decision · src bill-2026-08-06#L990 — "Contract Scope" is the final term; singular Contract; never CSI language
- 2026-08-06 · decision · src — — collapse ①: absorbs A5 + N3; context doc and must-check notes are one document

### P2 · Intelligent workflow building — templates, instances, 5 responses
*W1 · blocked · due — · deps P1 · owner daniel · src bill-2026-08-06#L289 · upd 2026-08-06 · blocked-on bill/workflow-template-export since 2026-08-06*

Effort L. The ball-in-court engine — Bill's phrase, coined live. **The
reviewer's response mutates the workflow.** Five responses, not six: Approved ·
Approved as Noted (drafter addresses notes → Carmen verifies they landed) ·
Revise & Resubmit (auto re-add every approver, loops indefinitely) · Review
Skipped (one reviewer clears another; records who clicked on whose behalf) ·
Void. *Rejected* dropped. Plus canned responses + freeform; anyone insertable
at any point; Carmen suggests insertions; templates key on project × phase;
drafter runs Carmen first as baseline; upstream reviews referenced, not
re-run. All Procore material/order statuses are dead. **Surface:** the DWL
"Procore Status" dropdown becomes the workflow actions dropdown, and reviewers
respond there too — D1-minimal's submittal tab is the secondary surface. Turn
notifications ride the shipped G1 system (one emit call; known
foreground-only limit). **Tests are named scope:** the response matrix (5
responses × loop/skip/manual-insert) gets service-level tests before any UI.
**Blocked start on Bill's Procore workflow template export** (the 8-step,
per-PM list) — we are replicating those templates.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#L30 — ball-in-court confirmed priority one
- 2026-08-06 · transcript · src bill-2026-08-06#L289 — "intelligent workflow building" coined; the response mutates the workflow
- 2026-08-06 · transcript · src bill-2026-08-06#L246 — today Bill hand-appends himself as a ninth step to see a revision
- 2026-08-06 · decision · src bill-2026-08-06#L390 — five responses, not six: Rejected dropped (it and Void do the same thing), Review Skipped stays
- 2026-08-06 · transcript · src bill-2026-08-06#L1141 — DWL "Procore Status" dropdown becomes the actions dropdown; reviewers respond in the DWL too
- 2026-08-06 · transcript · src bill-2026-08-06#L206 — all Procore material/order statuses dead; job log + email orders cover it
- 2026-08-06 · question · src — — start blocked on Bill's template export/screenshots (Owed)

### P4 · Tree of Life — sub-GC → N DRRs, PM-created, pre-filled
*W1 · not-started · due — · deps P1,P2 · owner daniel · src bill-2026-08-06#L1398 · upd 2026-08-06*

Effort M. The sub-GC submittal is the root — one record, many revisions; the
PM creates N DRRs pre-filled from the parent. **DRR→FC is 1:1, enforced** —
Bill rejected one DRR feeding several FCs outright. FC is terminal for review
and **immutable**: post-FC changes are as-builts, already handled by the job
log PDF markup — As-Built is a version series on the released FC, not a new
record type.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#L1398 — DRR→FC 1:1 enforced; 1:N rejected outright
- 2026-08-06 · transcript · src bill-2026-08-06#L403 — "once it's FC, we don't review it anymore" — FC terminal for review, immutable
- 2026-08-06 · transcript · src bill-2026-08-06#L48 — As-Built is a version series on the released FC, not a new record type

### P7 · Returned submittal ingestion via Carmen mailbox
*W1 · not-started · due — · deps P2 · owner daniel · src bill-2026-08-06#notes · upd 2026-08-06*

Effort M. Returned submittals land via the Carmen mailbox — the mail path
already exists. Returned binaries land wherever K3 decides, so K3 blocks the
storage side of this even though the build dependency is P2.

**Trail**
- 2026-08-06 · note · src bill-2026-08-06#notes — a way for returns to land is part of the minimum system; mail path already exists

### P10 · Backfill phase + source on 3,892 legacy rows
*W1 · not-started · due — · deps P1 · owner daniel · src bill-2026-08-06#notes · upd 2026-08-06*

Effort S — **shrank from "unscopeable."** Two 2026-08-06 decisions (extend
`Submittals`; project-level cut-over gate) collapsed what was the plan's
largest unscoped risk. What remains: a backfill script setting `phase` and
`source` on existing rows, and a decision about what the Brain shows for
Procore-originated submittals after October. Reconstructing legacy trees is
explicitly deferred — *"cross that bridge when we get there"*; legacy
DRR/GC/FC stay as three unlinked records (`submittal-id-coherence-audit.md`).
Opened Open question 1 (in-flight Procore projects at the lapse).

**Trail**
- 2026-08-06 · decision · src bill-2026-08-06#notes — extend-not-replace + project-gate cut-over collapse the migration; the 3,892 rows never move
- 2026-08-06 · decision · src bill-2026-08-06#notes — legacy tree reconstruction deferred; native model prevents the problem forward, does not fix it backward
- 2026-08-06 · question · src — — opened Open question 1: in-flight Procore projects when the subscription lapses

### P11 · Procore document export
*W1 · not-started · due 2026-10-31 · deps K3 · owner daniel · src bill-2026-08-06#L811 · upd 2026-08-06*

Effort S + unknown until inventory. PDFs, drawing sets, returned markups,
correspondence — `Submittals` holds metadata only; the files live on Procore's
servers and **vanish at lapse**. The only item with a cliff rather than a
deadline, and no second attempt. **Read-only delta inventory (~1d) in week 1**
sizes the pull; the pull is paced by rate limits, runs in the background, and
must be **verified complete before the lapse**. First in `queue.next`.
(Invited-user access to *customers'* Procore survives, which is what keeps
current drawing sets reachable through the GC's environment — our own document
history is what this rescues.)

> ⚠️ **Deferred 2026-08-15 with the rest of W1 — but this is the one item whose
> deferral is irreversible.** Every other Procore item can start late and still
> finish; this one has a cliff. Our hosted PDFs, drawing sets, returned markups
> and correspondence are deleted at the lapse and there is no second attempt,
> the pull is paced by rate limits, and the acceptance bar is *verified complete
> before the date*. **Resurface with real lead time — not in September 2027.**
> The cheap insurance remains what it always was: the read-only delta inventory
> (~1d) that sizes the pull. Deciding to skip the export is a legitimate call;
> discovering in month twelve that nobody decided is not.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#L811 — invited-user access to customers' Procore survives the lapse; our own hosted documents do not
- 2026-08-06 · decision · src — — week-1 read-only delta inventory sizes the pull; effort unknowable until it runs; verified-complete-before-lapse is the acceptance bar

### C3 · Universal PDF tool — absorbs the revision stack (P9)
*W1 · not-started · due — · deps — · owner daniel · src bill-2026-07-22#notes · upd 2026-09-03*

Effort L. **Promoted from Tier 2 onto the critical path** (collapse ②): the
as-built path already lives in the job log markup stack, so the submittal
revision stack (former P9 — revision stack + obsolete watermark + overlay
compare) must be the same tool, not a second one. **October scope is
C3-narrow** — the revision viewer only. Scoping resolved 2026-08-08:
**generalize the DWL viewer** — the client-validated PDF source of truth
(left sidebar + page toggle, client "incredibly pleased") — nothing new gets
invented, which cuts the risk; the catalog's "needs a brainstorm before build"
flag is retired. The full universal tool moves after October. K3 decides where
its binaries live.

**Trail**
- 2026-07-22 · transcript · src bill-2026-07-22#notes — "this needs to now become our profile markup system"
- 2026-08-06 · decision · src — — collapse ②: P9 folds in; building the submittal viewer separately ships two markup stacks and merges them later at full cost; C3 promoted into the October path
- 2026-08-08 · decision · src — — all future PDF modal/viewing/review work generalizes the DWL viewer; "needs a brainstorm" retired — the brainstorm happened in production, by the client using it
- 2026-08-09 · build · src pr#337 — a read-only in-modal PDF viewer (`PdfReadViewer.jsx`) shipped inside the release hub's Attachments tab, with Carmen's drawing review beside it. Not scoped as C3 and not the revision stack — but it is a second viewer in the codebase, which is the exact outcome collapse ② exists to prevent. C3-narrow should start by deciding whether it generalizes the DWL viewer or this one
- 2026-08-21 · note · src bill-2026-08-21#L69 — demand accumulating while deferred: the field guys asked to **mark up on top of photos**, and Bill wants drawings markable on the Brain from the job log [#L87]. Photo markup is this tool's ground (one markup stack) — do not build it ad hoc inside N9
- 2026-09-02 · notes · src bill-2026-09-02 — **improved photos / attachments handling** is the umbrella name for this thread. Three concrete deletes in scope: **delete a photo**, **delete a single markup while it is in progress**, and **delete a whole attachment** for the wrong-file-uploaded case. The transcript covered only photo and markup deletion [bill-2026-09-02#L52]; whole-attachment delete is new
- 2026-09-02 · transcript · src bill-2026-09-02#L1158–L1198 — **PDF viewer has no scroll** — page-at-a-time via a next button; Bill wants *"the drafting workflow side behavior"*. The edit surface opening its own window is **clunky and must stay in-modal**: the crews run the Brain as an **installed app, not a browser tab**, so a new window opens in Chrome somewhere else entirely. Pinch-to-zoom in-modal is acceptable on iPad; Bill does like the edit surface being bigger
- 2026-09-02 · notes · src bill-2026-09-02 — **named design references**: the markup layer and the agentic panel are both to be modelled on **Procore's PDF markup modal** and the **Gemini sidebar**. New — the transcript discussed Gemini's behaviour but never set it as the UI target
- 2026-09-02 · transcript · src bill-2026-09-02#L1239–L1291 — Carmen PDF review keeps its findings-to-page behaviour (*"the way that Carmen flags the pages and you click on the pages from the review is fucking great… so valuable"*) and **adds** a side-push chat that sees the full document **and** the findings, can update its own memory, and can be asked questions. Blocker Bill named: **our markups live in Procore and never reach the Brain** [#L1249], so there is nothing to train the reviewer on. He also wants the **Mile High 101 documentation** fed to the model [#L1234]. Reusable test prompt: given a cover sheet, verify every hole has hardware that fits and that counts match [#L1251]
- 2026-09-07 · decision · src — — the drawing-chat half of that ask is now its own entry, **N18** (the *global* side-push surface is **N17**), scoped as review-is-a-tool + chat-is-the-fast-path; the markup-training blocker is half-closed by N14's Final PDF Pack puller landing approver markups in the Brain as PDF annotations
- 2026-09-16 · transcript · src bill-2026-09-16#L738–L831 — asks: a **full-screen** mode for markup [#L748]; navigating markup must **not drop the Carmen review** [#L801–L809]; a new version behaves like a **clear layer over the previous one**, keeping earlier markup visible across versions [#L807–L831]; markup on photos (T13) [#L95]
- 2026-09-16 · notes · src bill-2026-09-16 — Bill: Carmen Review *"needs a full overhaul"* — does much well but little that's useful, not pointed the right way [#L786–L790]; he'll draft a prompt. **Overhaul deferred** (Daniel)

### D1 · Projects page
*W1 · in-progress · due — · deps K2 · owner daniel · src bill-2026-08-06#L802 · upd 2026-08-06*

Effort L. The container for P8 and the submittal section. **In progress on
`feature/updated-projects`.** October scope is **D1-minimal** — the submittal
tab only: Bill named "brain projects," but a container is enough. The full
page moves after October.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#L802 — "brain projects" named inside Bill's must-have boundary
- 2026-08-06 · note · src — — in progress on `feature/updated-projects`; October cut is the minimal submittal tab

---

## Workstream 2 — Money

One thread across both meetings, sequenced (collapse ⑤).

**Re-tiered 2026-08-15: an ongoing cost lane, sitting behind W5.** It was
described as "the release valve — allowed to slip" while W1 owned a deadline;
with W1 deferred, that framing is void. W2 is not a thing that finishes, and it
is not the thing being cut. It runs behind Trello in the short term.

**The strongest evidence in the file that it is under-tiered rather than over:**
I4 shipped 2026-08-10 out of order — skipping I3 and N2b — and within five days
caught **~$15k of premature-or-duplicate sub payment** [bill-2026-08-15#L33],
cash-flow harm rather than accounting noise. *"Lexi was just loving it"* [#L41].
Logged as signal; explicitly **not** treated as a re-tiering trigger (Daniel,
2026-08-15).

### N1 · Release tags — Contracted / Change Order / MHMW Cost
*W2 · built · due — · deps — · owner daniel · src bill-2026-08-06#notes · upd 2026-08-09*

**Built 2026-08-09**, migration run 2026-08-10. `Releases.release_tag`
(`app/models.py:530`, nullable) ships with the tag **required at creation** on
both the pasted and verbal paths, editable afterwards in the release hub's
Billing section (`JobDetailsBody.jsx`, `ReleasesLayout.jsx`,
`constants/releaseTags.js`). Existing rows are untagged, exactly as planned —
the sequencing holds: nullable now → N10 bulk-edit backfill → required.
**It shipped ahead of its own definition, and that turned out to be safe.**
Open question 2 (what *MHMW Cost* means) was half-answered 2026-08-29: it means
a release MHMW eats the cost on, and **for now it is a flag with no downstream
behavior** — no invoicing exclusion, no cost rollup. So the rows accumulating
under it are descriptive, not load-bearing, and the "expensive if it accumulates
under the wrong reading" risk is off the table. The reason split (rework /
warranty / no-charge) only has to be settled when the tag first drives
something — which is N2b/invoicing, not N10.

*The pre-build statement, retained for the record (2026-08-06):* the classifier that makes the invoicing tab work: the 8/6
conversation described *how much* is invoiceable per stage; the tag says
*whether, and against what* — Contracted bills against the SOV, Change Order
against the CO, MHMW Cost against nobody. **Ships nullable first**, N10
backfills it, only then does the field become required. Ship without waiting
on A2 — the Change Order tag is useful before COs exist as records (*"we will
grow into COs"*). The exact meaning of MHMW Cost is with the client (Open
question 2).

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#notes — tag drives invoicing filters: SOV / CO / nobody
- 2026-08-06 · decision · src — — sequencing: nullable → N10 bulk-edit backfill → required; backfill is not a migration default
- 2026-08-06 · question · src — — opened Open question 2: what MHMW Cost means
- 2026-08-09 · build · src pr#338-wave — `release_tag` shipped: required at creation (pasted + verbal), editable in the hub Billing section, existing rows untagged
- 2026-08-10 · note · src — — migration `add_release_tag.py` run; Open question 2 still open, so MHMW Cost is collecting rows before its meaning is fixed
- 2026-08-29 · decision · src — — Open question 2 half-answered (Daniel): MHMW Cost = a release MHMW eats the cost on, **flag only, no behavior attached**. De-escalates the "collecting rows before its meaning is fixed" risk — the rows are descriptive. The reason split waits until invoicing actually reads the tag
- 2026-09-05 · measurement · src — — **coverage counted for the first time** (sandbox, read-only): **12 tagged rows system-wide**, and **91 of 99** releases with a `released` date on or after the 2026-08-09 ship date are untagged. The nullable → backfill → required sequencing is holding exactly as designed, but it means **N10 is now on the critical path for anything that reads the tag** — first instance is **N16**, which has to render an explicit `untagged` bucket because that bucket is currently the whole answer

### N10 · Bulk edit on the job log
*W2 · not-started · due — · deps N1 · owner daniel · src bill-2026-08-06#notes · upd 2026-08-06*

Effort M. Multi-select rows, set a field across them. Born as N1's backfill
mechanism (decided 2026-08-06 over a migration default) but worth more than
that one use — there is currently no way to change a field across many
releases at once.

**Trail**
- 2026-08-06 · decision · src bill-2026-08-06#notes — N1 backfill happens through bulk edit on the job log, not a migration default; promoted to its own item

### N2 · Billing spine v1 — Excel ingest at FC conversion
*W2 · not-started · due — · deps P5 · owner daniel · src bill-2026-08-06#L637 · upd 2026-08-06*

Effort M. **Entry point: the FC conversion modal** — the same moment the
drafter drops the final PDF pack; not the project page. **Display: the
invoicing tab now**, the admin project tab later, spliced per department.
**Store the file and extract the data**; back-end only — nothing renders on
the submittal. Billing-stage gates: material ordered → 100% material · fab
complete → 100% fab · paint complete → 100% paint, **photos required** (J1) ·
install % → equipment and install labor at that percentage. Budget vs actual
per department reconciles to the original quote value. **Bill owes the sample
release Excel** (Owed). Excel is v1; quote/estimate integration — SOV
generation, native department budgets, the decrement-against-contract-value
check that catches double-selling a stair — is v2.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#L637 — "DRR to FC, drop in the final PDF pack, work with the Excel in the short term… on the invoicing tab is where we see this breakdown"
- 2026-08-06 · transcript · src bill-2026-08-06#L648 — store the file too; Bill started at "just this data, not the sheet" [#L502] and softened at 340 KB
- 2026-08-06 · transcript · src bill-2026-08-06#L607 — billing stage gates; photos required at paint complete [#L613]
- 2026-08-06 · transcript · src bill-2026-08-06#L550 — budget vs actual reconciles to the original quote value
- 2026-08-06 · transcript · src bill-2026-08-06#L478 — v2 is the decrement-against-contract-value check that catches double-selling a stair
- 2026-09-02 · business rule · src bill-2026-09-02#L1131–L1145 — **line-item contract value splits roughly in thirds: material / fab+paint / install.** Bill first offered *"a general 30%"* for install, then landed on *"effectively one third of the value for each of the different stages."* Captured 2026-09-05 — it was in the 9/2 findings and had reached no item. Directly useful to N2b's stage gates, to health scoring, to T&M→CO, and to any earned-value work; Daniel is already using it to backfill an audit

### N2b · Billing stages → invoicing tab
*W2 · not-started · due — · deps N1,N2 · owner daniel · src bill-2026-08-06#L607 · upd 2026-08-06*

Effort M. Renders the billing-stage breakdown (see N2) on the invoicing tab,
filtered by N1's tags. Later the same data moves to the admin project tab,
spliced per department.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#L607 — the stage-gate table this tab renders

### A2 · Change orders — auto-ingest from email
*W2 · blocked · due — · deps — · owner daniel · src bill-2026-07-22#notes · upd 2026-07-22 · blocked-on bill/co-log-excel-and-sample-email since 2026-07-22*

Effort M. Auto-ingest change orders from email. **Blocked on Bill since
2026-07-22** — needs the change order log Excel and a sample CO email (Owed).
A2 is a dependency of full CO records, not a gate on N1 (collapse ⑤): N1
ships the Change Order tag ahead of CO records. In `queue.awaiting`.

**Trail**
- 2026-07-22 · transcript · src bill-2026-07-22#notes — item opened; Bill to supply the CO log Excel + a sample CO email
- 2026-08-06 · decision · src — — collapse ⑤: A2 is a dependency, not a gate — N1 ships the CO tag first

### J1 · Photos at paint complete as an invoicing gate
*W2 · dissolved into T13 (2026-09-14) · due — · deps N9 · owner daniel · src bill-2026-07-22#notes · upd 2026-09-14*

Effort S. **Un-dropped 2026-08-06.** Cut on 7/22 as "irrelevant basically" —
but paint invoicing requires photographs, which makes this a gate, not a
nice-to-have. N9 is what makes those photos usable: Katie's 7/22 problem was
*"I don't know what it is most of the time, what it's supposed to look like,
where it's at"* — a stamped photo is self-describing.

**Trail**
- 2026-07-22 · transcript · src bill-2026-07-22#notes — dropped as "irrelevant basically"
- 2026-08-06 · decision · src bill-2026-08-06#L613 — supersedes the 7/22 drop: paint invoicing requires photographs; J1 is the gate, N9 makes it work
- 2026-09-14 · dissolved · src thisweek-2026-09-14#§5.4 — **into T13**: the Paint Complete Evidence gate is this item, built as a stage gate and paired with a Ship Complete gate. The invoicing read of that evidence (Katie's side) rides T13's visibility section and N2b

### I4 · Installer invoicing — Subs → Invoice Paid
*W2 · built · due — · deps — · owner daniel · src bill-2026-07-22#notes · upd 2026-09-16*

Effort S–M. **Un-parked and shipped 2026-08-10** (PR #339), migration run the
same day. The admin Subs page gained a fillable
`installer_invoice_progress` (0–100) and free-text `installer_invoice_numbers`
on `Releases`, plus a reworked invoice table; Oscar was dropped from the
invoicing tab. Deliberately distinct from `invoiced` (MHMW customer billing)
and `installer_invoice_paid` (the yes/no complete toggle) — three separate
money facts on one row, which is worth remembering when N2b renders the
invoicing tab. Real users: Katie and Lexi.

**It skipped its own gates.** The catalog had I4 deferred behind I3 + N2b and
this roadmap had it parked; it shipped because the office needed it, not
because the dependencies cleared. That is a legitimate call — but N2b now
renders against a sub-invoicing surface that already exists and was designed
without it, so N2b's scope should be re-read before it starts rather than
assumed.

**Trail**
- 2026-07-22 · decision · src bill-2026-07-22#notes — deferred behind I3; confirmed deferred even with I3 elevated
- 2026-08-10 · build · src pr#339 — shipped from `fix/sub-invoicing`: progress % + invoice numbers on `Releases`, reworked Subs invoice table, Oscar removed from the invoicing tab; `add_installer_invoice_progress_and_numbers.py` run
- 2026-08-10 · note · src — — shipped without I3/N2b clearing; N2b inherits a surface it did not design
- 2026-09-16 · built · src pr#382 — Invoice Paid tab: Paid / Company / Project / Crew dropdown filters + search + clear-all, and **CSV / PDF export of exactly the filtered rows** with Company + Crew columns. Company is derived from the crew name via `SUB_COMPANY_CREWS` in `app/brain/subs/service.py` (a hardcoded map — a new sub crew needs a line there or it exports with a blank company). Patch notes v2.0.383

---

## Workstream 3 — Daily use

The bug pile, DP, N6, N5, and the N7 core all cleared 2026-08-06/08 (PRs
#323–#334; in-app patch notes at v2.0.334) — see the Resolved log. **N7's
remainder cleared 2026-08-09** (PRs #336–#338, v2.0.338).

**Re-stocked 2026-08-15.** With W1 deferred, this tier is where the *quality* of
the daily tool gets paid down: three fixes (see the Fix queue at the top) and
two audits. The audits share one shape, set by Daniel on 2026-08-15 —
**document current behavior → agree the target with the client → then change**.
Neither is a code-first task.

### AUD1 · End-of-lifecycle audit — staging semantics + date handling
*W3 · not-started · class audit · due — · deps — · owner daniel · src bill-2026-08-15#L115 · upd 2026-08-15*

Effort M–L. **One item, not two.** Install Complete / Complete / `job_comp` /
`invoiced` all describe *how a release ends*, and the date-color cascades fire
off exactly those transitions — auditing them separately produces two rulesets
that disagree again, which is how we got here.

**The defect that opened it:** assigning an installer [#L115] *and* changing
stage [#L119] both silently convert a soft date into a **hard date**, including
on past-due rows [#L123]. Reported by Katie and Bill independently the same
morning. A hard date is a commitment; this manufactures commitments nobody made,
on exactly the rows PMs are being told to clean up. **Rule set 2026-08-15:
assigning an installer natively assigns nothing.** Bill's ask follows —
*"we should have to toggle hard date on or off"* [#L127].

**Why it is an audit and not a fix:** N5's install-start/install-complete
coloring rules are recent, the comp / ship-comp rules are older, and nothing ever
reconciled them — so the trickle-down is inconsistent and inference fills the
gaps. **Governing principle: lean on user control, do not automate out user
agency in the short term.**

**Also in scope — Katie's staging question** [#L211]: why doesn't `invoiced = X`
move a row off Install Complete to Complete? Daniel's live read, still to be
verified: no such cascade exists — `neutralize_install_date_cascade` fires in
that zone but only strips date color, it does not advance stage. Likely a
cascade never built rather than one that broke. Bill's own model, hedged twice
[#L207]: Install Complete means *we physically installed on site*; **drop-shipped
work should be marked Complete, never Install Complete** — a distinction nothing
currently enforces. Katie's written feedback is an **input** to this audit, not a
separate ticket, and had not arrived as of 2026-08-15.

**Deliverable is two things:** corrected behavior, **and a legible statement of
the date rules for distribution back to the client.**

**Banked as working:** ~~the N5 shipping-stage rule (ship planning / ship complete
→ dump the color, keep the hard date) is confirmed correct in production
[#L127]; Bill hedged only about *"some old outliers"* [#L131].~~ **Un-banked
2026-08-21** — Bill reversed himself (*"I might have given you bad
information"* [bill-2026-08-21#L109]): the color dump moves to the **`Install
Start`** stage, yellow never silently disappears [#L113–L115]. Carried as BUG-11,
**which shipped 2026-08-29** — the dump now fires on a stage transition into
`Install Start` or later, so the behavior this audit has to describe is settled.
Still one more reason the deliverable is a written ruleset Bill signs: the
reversal came eight days after the rule was banked as *confirmed correct in
production*.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L115 — installer assignment and stage change both silently create hard dates; two independent reports the same morning
- 2026-08-15 · transcript · src bill-2026-08-15#L207 — Install Complete = physically installed; drop-ship should read Complete; "Complete = invoice marked off" was discussed and never built
- 2026-08-15 · decision · src — — merged the date-handling and staging questions into one audit; assigning an installer assigns no date; user agency over automation; client-facing ruleset is a deliverable
- 2026-08-20 · spec · src fieldops-2026-08-20#§5.4 — an input to the ruleset, in writing: **projected dates carry no color** (not yellow); **yellow = a hard green date now past due**; hard dates rank above projected on the same day. Verify the timeline and job-log renderers against this before the ruleset is distributed
- 2026-09-03 · decision · src daniel-2026-09-03 — third input, and the one that simplifies the ruleset most: **ASAP is a colour, not a date** (BUG-20). Every date in the install column is now one a person typed — there is no synthetic date in the system for the ruleset to have to explain, and the fieldops §5.4 line ("projected carry no colour, yellow = a hard green date now past due") extends cleanly with "red = a hard date flagged ASAP"
- 2026-08-21 · decision · src bill-2026-08-21#L109 — second input, and a reversal of a banked rule: hard-date color survives the ship stages and dumps at Start Install; yellow stays until then (EOS-scored, never silently dropped [#L113]); trigger ambiguity (Install Start stage vs `start_install` date) is this audit's to resolve; do NOT touch hard-date semantics until the trigger move is tried [#L115]. Bill also flagged the projected-vs-hard *font* distinction as too subtle once color is gone [#L109] — legibility belongs in the same ruleset

### AUD2 · Release-number uniqueness ruleset
*W3 · not-started · class audit · due — · deps — · owner daniel · src bill-2026-08-15#L177 · upd 2026-09-05 · **queue.now 2026-09-05***

Effort M. Same shape: confirm current behavior, confirm the updated behavior
**with the client**, then change. **Early read: the job-log enforcement (the
BUG-3 rule) is correct and the gap is DWL-side**, so the fix may be entirely
one-sided — BUG-8 in the Fix queue carries that half.

Bill independently restated the rule and matched what shipped: *"it needs to have
a must-stop if the job number and release number match… **we just can't have the
full match ever**"* [#L167], while job-number rollover across years is fine.

**Open for the client conversation:** on collision, auto-advance to the next free
number or keep block-and-suggest? Bill wants advance — *"is it not just 'give me
a new number and move it to the next one' in the sequence at that point?"*
[#L173]. Today it blocks and suggests.

**Rejected, with a reason that must be given back to him:** Bill proposed
carrying the start year as project metadata (`340-26`) to disambiguate the
archive [#L185]. **Not needed — the record already carries date handling that
accomplishes the same comparison**, so the year would be a display-number
encoding of data we already hold. He proposed it himself, so the confirm step
has to *explain* the rejection, not silently drop it. **Replaces it:**
best-practice research on long-term uniqueness handling.

**Scope constraint:** submittals and releases are converging (see the W1 banner).
Write the ruleset to survive that merge; do not hard-code today's two-model split.

**Targeted 2026-09-05 (Daniel) — and the deferral above no longer holds.** The
written cursor option was shelved on 2026-09-02 as *"not a needle mover"*, with
one stated prerequisite: **measure the burn rate**. That measurement was taken
this session and it moves the item, for a reason the deferral did not anticipate.

**The allocator is in rollover mode right now — it is not an edge case waiting to
happen, it is the current steady state.** `998` is held by an **active** release,
so `current_max == REL_MAX` on every call and `next_rel_number` takes its
gap-filling branch every time, scattering into the **580 free numbers below the
max**. That is Bill's 202 → 203 → 205 → 105 symptom, and it is not a transient:
the 2026-09-02 note already described the top of the range as an attractor, and
the data now shows the sequence sitting on it. Nothing about the current behavior
recovers on its own.

**Burn rate — the recorded prerequisite, now answered.** By `released` date:
**282** releases in 2025 and **491** in the first eight months of 2026, a run rate
near **735/year** and rising. Against 898 usable numbers that is a **full wrap
roughly every 15 months, trending toward annual.** Read two ways, and both point
the same direction: the range is not roomy enough for "we'll deal with it later",
and the cursor design's cost — *one predictable wrap per cycle* — is a **yearly**
event, which is a straight trade against the permanent scatter running today.

**Third finding, and it belongs in the ruleset rather than the fix:** live rows sit
**outside `[101, 998]` on both ends** — an active release numbered **999**, and
pending DRRs holding **100** and **101**. `assign_rel_manual` validates the range,
so nothing in the current code issued them; they are legacy or import residue. The
ruleset has to say what an out-of-range number already in the data *means* — is it
taken, is it reissuable, does it get migrated — because `next_rel_number` silently
filters them out of `in_range` today and would happily hand `999` to someone else
if the constraint ever moved.

**All three figures were read from the SANDBOX database** (`SANDBOX_DATABASE_URL`,
read-only `SELECT`s, 2026-09-05) because no production URL is configured in this
checkout. Sandbox looked current — releases through 2026-09-01 — but **re-run the
three queries against production before the ruleset is written**, since the wrap
math and the "998 is occupied" claim both turn on exact live values.

**What targeting it means, in order:** ① re-measure on prod; ② take the
confirmation conversation Bill is already owed (auto-advance vs. block-and-suggest,
and *why* `340-26` is not needed) — it is in **Owed** and it gates the change step,
not the measurement; ③ then build. The **per-job uniqueness** structural fix stays
where it was put — riding the Procore exit, because `ReleaseDate.rel` is
`unique=True` as the DRR join key — so what is buildable now is the **cursor**, not
the constraint.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L159 — DWL issued a number already in use; worst case was the same job *and* the same release number
- 2026-08-15 · transcript · src bill-2026-08-15#L177 — Bill diagnosed it himself: the DWL side never checks the archive, the job log catches it later; "it should have caught that when it got to 108"
- 2026-08-15 · transcript · src bill-2026-08-15#L173 — instances 410-108 (archived twin Columbine Square) and 500-140 (Novel Flatirons); asks for auto-advance over blocking
- 2026-08-15 · decision · src — — full audit with client confirmation; year-as-metadata rejected (dates already in the record) with the reason owed back to Bill; uniqueness research replaces it
- 2026-09-02 · notes · src bill-2026-09-02 — **live symptom reported.** A job's releases ran **202 → 203 → 205 → 105** because 105 cleared after the others. Daniel's ask: enforce sequential *as far as possible*, and *"ideally we just want to grab the next available larger number"*
- 2026-09-02 · decision · src — — **root cause found, and it is not a typo.** `next_rel_number()` re-derives its position from `max(taken)` on every call. Rollover fires when `current_max == REL_MAX (998)`; when 998 frees, `current_max` becomes 997, the next suggestion is 998, and rollover **immediately re-arms** — the top of the range is an attractor, so once the range fills once the allocator never durably leaves gap-filling mode. The observed *"105 released before 998"* fits: `_globally_taken_rel_numbers` counts **pending DRRs holding a rel**, so 998 only had to be *reserved on an uncleared DRR* to trip rollover — it never reached the job log. **The allocator has no memory** is the single defect behind both symptoms (archiving the highest release also drags the sequence backward on its own)
- 2026-09-02 · decision · src — — **rejected:** widening `REL_MIN`/`REL_MAX` (*"we are not widening"* — would push release numbers to 4 digits on drawings and paperwork). Also rejected: making the rollover branch pick the next free number above the *job's* max — it gives a per-job sequential feel but breaks the **global chronological** reading Daniel wants, and would hand a brand-new job a low scattered number
- 2026-09-02 · decision · src — — **written option, DEFERRED** (*"not a needle mover"*): replace the derived position with a **persistent monotonic cursor + circular allocation** — store `last_issued` in a small state table (model it on `LakeIngestState`), allocate the first free number strictly above the cursor, wrap to `REL_MIN` past `REL_MAX` and keep climbing. The cursor never moves backward except at the wrap. Delivers what was asked: a new job draws *the next few highest numbers consecutively*, numbers read chronologically across all projects, and archiving the top release stops yanking the sequence. Costs a tiny table + migration, and one predictable wrap per cycle instead of constant scatter. Seed the cursor at the current global max so nothing shifts on day one. **Prerequisite for revisiting: the burn rate** — releases per year against 898 numbers decides how often the wrap actually lands. Optional refinement: on wrap, prefer numbers freed longest ago
- 2026-09-02 · decision · src — — **the 898-number ceiling is self-imposed.** `Releases` already constrains per-job — `UniqueConstraint("job", "release", "job_name")` — and the DB would accept 105 on two different jobs. Uniqueness is global only because `ReleaseDate.rel` is `unique=True` as the Procore DRR→release join key (`models.py:230`). **Per-job uniqueness is the structural fix and rides along with the Procore exit (W1), not ahead of it**
- 2026-09-05 · decision · src daniel-2026-09-05 — **targeted; moved to `queue.now`** alongside N16, on Daniel's "build now"
- 2026-09-05 · measurement · src — — **rollover is armed today, not hypothetically.** `998` is held by an active release, so `current_max == REL_MAX` on every `next_rel_number` call and the gap-filling branch runs every time, with **580 free numbers below the max** to scatter into. The 2026-09-02 attractor analysis is confirmed by the data, and the "105 released before 998" reading was right
- 2026-09-05 · measurement · src — — **burn rate answered, and it un-defers the cursor.** 282 releases released in 2025, 491 in Jan–Aug 2026 (~735/yr and rising) against 898 numbers = a **wrap every ~15 months, trending annual**. The deferral's own prerequisite is met and the answer argues *for* the cursor: one predictable yearly wrap replaces permanent scatter
- 2026-09-05 · finding · src — — **live data sits outside `[101, 998]` on both ends**: an active release numbered `999`, pending DRRs holding `100` and `101`. `assign_rel_manual` validates the range so no current code path issued them. The ruleset must state what an out-of-range number means (taken / reissuable / migrated) — `next_rel_number` currently just filters them out of `in_range`
- 2026-09-05 · caveat · src — — all three figures read **read-only from the sandbox DB**; no production URL is configured in this checkout. Sandbox is current to 2026-09-01, but **re-run against prod before writing the ruleset** — both the wrap math and the "998 is occupied" claim turn on exact live values

### N15 · Carmen tiers — CarMini / CarMid / CarMax
*W4 · not-started · class build · due — · deps T2 · owner daniel · src bill-2026-09-02#L107 · upd 2026-09-03*

Effort M. **Bill's idea, raised unprompted after he noticed AI spend on the admin page is
*"pretty damn low"*** [#L66]. Three Carmen tiers keyed to **both permission and model
strength**, so the tier decides what data is reachable *and* how much compute a question is
worth:

- **CarMini** — the default-user tier. *"Everybody can have car mini."*
- **CarMid** — the middle tier. Named by Daniel after the meeting; the transcript says
  "Carmen" [#L110].
- **CarMax** — **admin only**, strongest model, **full read-only access to all data**, and
  explicitly worth real money per question: *"you can spend $10 performing data analysis on
  the data we've collected"* [#L116].

Wires into the user-roles work — *"just as we're working on the user roles, maybe default
user just gets car mini, but the admin gets car max"* [#L122]. Hence `deps T2`.

**The need is unanticipated ad-hoc queries, not a prompt library.** Bill's worked case: at
project close, tax work needs total fabrication labour hours for a job; in the old job log he
sorted and tallied it himself and now cannot [#L74]. He wants *"hey Carmen, how many fab hours
did I have in total on job number 500"* across **archive and active** [#L79]. He accepts a
prompt library (N13) as *part* of it but named its limit himself: *"there's going to be obscure
ones that are going to come up that I'm like, I didn't think about this because it hasn't
happened for two years. When it does, it's painstaking to figure it out"* [#L90].

**Adjacent, and likely its own item once real — conversational write-back.** Separate work
from tiering, recorded here so it is not lost. Sparked by an oil-and-gas field app Bill saw
where a tech says *"I'm at well site X"* in a chat and the job record updates [#L216]. MHMW
shape: *"I'm at Columbine Square building one, balcony rails are done with the exception of
this, add a note about this"*. Hard requirements he stated:
- **Confirm before writing** — *"you mean this job, this release, this description… check"*
  then commit [#L226]. Daniel's notes ask for a **written spec of that confirmation modal**,
  with a worked example to build against: *"move 150-389 to Install Start and leave a note
  '…'"* spoken through general voice mode.
- **Extends to subs** — *"I'm at this project on this building"* → *"do you mean this
  release?"* → yes → photos attached [#L230].
- **Gating is part of the appeal** — *"this has a gate, we can't make it QC complete until you
  have your photos, please"* [#L239].
- Bill on urgency: *"I don't know that that's mission critical to get in there right away"*
  [#L234].

**Trail**
- 2026-09-02 · transcript · src bill-2026-09-02#L107–L127 — three tiers proposed by Bill, keyed to permission *and* model strength; CarMax admin-only with full read-only data access and a real per-query budget
- 2026-09-02 · notes · src bill-2026-09-02 — middle tier named **CarMid** by Daniel after the meeting, superseding the transcript's "Carmen"
- 2026-09-02 · transcript · src bill-2026-09-02#L74–L95 — the driving need is the query nobody anticipated; a prompt library (N13) is complementary, not sufficient
- 2026-09-02 · decision · src — — conversational write-back recorded here as adjacent scope; it is genuinely different work and should take its own ID once it is real

### N12 · Release Modal — distribute the one-stop surface
*W3 · in-progress · class build · due — · deps — · owner daniel · src bill-2026-08-15#L49 · upd 2026-09-16*

Effort M, incremental. **Reframed 2026-08-15 from "invoicing detail modal" to
what it actually is:** the **Release Modal** is the one-stop surface for all data
on a release, and it gets **distributed wherever a release is referenced**.
Invoicing is the first redistribution target, not a separate build. N7's
`ReleaseHubModal` is already that object — this makes *distribute and refine in
place* the standing pattern instead of per-page modal variants.

First round of tweaks is already filed: Lexi's notes in the bug tracker [#L47] —
*"additional information in this column… and then having the overall modal pop up
to give us more of the details"* [#L49], plus unspecified job-log modal tweaks
[#L53]. Signal from Bill: the data storage is right, the surface needs tweaks and
wider distribution.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L49 — Lexi wants column enrichment + a detail modal on the invoicing surface; notes filed in the bug tracker
- 2026-08-15 · decision · src — — reframed as the Release Modal: one canonical surface, distributed to other pages, refined in place; invoicing is the first target
- 2026-08-21 · transcript · src bill-2026-08-21#L143 — sizing note: the modal could be bigger on desktop ("there's more space for it") but **do not disturb the iPad layout** — that's where most usage lives and it "looks really good" there. Photos should render in the modal's preview area rather than a new window [#L69] (also on N9)
- 2026-09-02 · transcript · src bill-2026-09-02#L291–L321 — the Job Log modal's own rework, from Bill: **photos move to the front page** and Attachments becomes the drawings/PDF-review surface — motive is the shipping guy's click path, *"he's clicking here and then he's clicking attachments"* [#L294]; a **photo-present indicator icon** [#L291]; **condense the data box** — Bill is *"a medium fan"* of how it reads and Daniel owes him options, target near job-log density [#L305]; and **write access to everything** — *"any functionality you have on the main page should be inside"* [#L311]. Stage progress is explicitly free to move [#L295]
- 2026-09-04 · build · src pr#367 — **the photo indicator shipped** (a slice of the 9/2 photos thread, ahead of the modal rework): a camera glyph leads the Description in both the table row and the card when a release has photos, count in the tooltip, no icon and no extra request when it has none. It reuses `photo_count` / `cover_photo_id`, already batched server-side for the Timeline's cover thumbnails — the answer was on screen already, just not shown. Icon **leads** the text because the Description cell clamps to two lines and a trailing icon would be the first thing truncated. Does not touch the modal-front-page ask below, which is still open
- 2026-09-02 · notes · src bill-2026-09-02 — placement pinned by Daniel: the **camera icon lives in the description field**, and the **Banana Code goes upper-right on the JL modal** (it currently sits at the bottom of `JobDetailsBody`, so that's a move, not a build)
- 2026-09-02 · decision · src — — **the combined modal is N12's next redistribution target, not a reopened N7.** Today four components render a release across ~1,940 lines: `ReleaseHubModal` (325) + `JobDetailsBody` (497) on the Job Log, and `ReleaseDetailModal` (471) / `ReleaseCockpitModal` (647) from a timeline card — the latter two **read-only by `GanttChart`'s stated invariant**. Daniel's ask is one modal everywhere, which retires ~1,100 lines of duplicate. N7 stays `built`: it shipped the `ReleaseHubModal` unification 2026-08-06/09 and never had the timeline modals in scope
- 2026-09-02 · decision · src — — **two open questions block a clean start.** (1) `ReleaseCockpitModal` is 647 lines of admin crew/date what-if that deliberately never writes — does it survive as a *mode* inside the combined modal, or go away? It is the largest branch in the consolidation. (2) `GanttChart`'s "clicking a card opens a read-only detail modal" invariant is retired once the combined modal carries write — correct now that drag sets `start_install` (T1), but it must be retired deliberately, not by accident
- 2026-09-02 · decision · src — — **sequencing note:** `JobDetailsBody`'s header states *"no new write paths except mark-received on orders and release_tag PATCH"*. Write access is therefore the bulk of this work and must land **before** the T3 permission layer — you cannot gate fields that do not yet write. Suggested order: settle the cockpit question → consolidate → layout → write access → permissions
- 2026-09-02 · decision · src — — **watch the direction conflict.** Bill wants the Job Log data box *condensed* [bill-2026-09-02#L305]; Daniel's DWL instruction was Details *expanded, no collapse control*. Scoped to the DWL modal only on Daniel's confirmation (2026-09-02), but the two surfaces are about to become one component — confirm the Job Log side genuinely goes the other way before building
- 2026-09-16 · transcript · src bill-2026-09-16#L712–L717 — an **Open items** block (active to-dos + active issues) takes the materials-order slot; materials moves down. "The hub" in patch notes confused Bill [#L118–L128] — say **release modal** in user-facing copy

### N19 · Home page — your open items *(un-parks D2)*
*W3 · not-started · class build · due — · deps — · owner daniel · src bill-2026-09-16#L593 · upd 2026-09-16*

Effort M–L. **Elevated 2026-09-16 by Daniel.** Every to-do, issue and notification
ask in the 9/16 session converged on one surface: a per-user **home page** listing
*your* to-dos, issues assigned to you or your department, ball-in-court items, and
submittals waiting on client review — Procore's "my open items" and Ninety's to-dos
as the named models [#L168–L173, #L598–L610, #L1566–L1577]. Today's to-dos are
*"select them all and mark done"* [#L670]; the ask is real to-do behavior — notes on
an open item, linked items, comment → notify the assignee — the in-app notification
model Ninety uses [#L664–L686]. Bill: the notification bell *"doesn't really have to
be that great"* once this exists [#L610].

**Un-parks D2** (personal page, parked in the reasoning catalog). **Builds on
BUG-17's shipped half** (PR #369 two-column to-dos/mentions page) and its parked
scope at `~/Desktop/Reference/eos-todos-reference/SCOPE-for-MHMW.md` — whose headline
still holds: there is no to-do table, only extractor-made `ChecklistItem` rows, so
real to-dos need a write model first. Overlaps **T5's My Work** queue; build this
as the internal-user version and let T5 extend it to the field. Consumes **T11**
owner/mentions and **N12**'s open-items block.

**Trail**
- 2026-09-16 · transcript · src bill-2026-09-16#L593–L686 — home page + Ninety-style to-dos asked for; to-dos tied to cards praised [#L668]
- 2026-09-16 · notes · src bill-2026-09-16 — **elevated** (Daniel): *"elevating home page behavior, improved visibility into to-dos, issues, etc"*; queued in `queue.next` behind T12/T13/T9

### N14 · FC pack on the Job Log modal
*W3 · not-started · class fix · due — · deps — · owner daniel · src bill-2026-08-21#L87 · upd 2026-09-03*

Effort S–M. The DWL attachments can pull the drawing down from Procore; Bill
wants the same on the job log modal — *"or if it just automatically did it —
whatever was uploaded as the FC just runs it"* [#L87]. Purpose is adoption:
*"get the guys used to staying on the Brain and seeing the drawings there"*,
with markup-on-the-Brain as the follow-on (C3's ground). The Attachments tab +
`PdfReadViewer` already exist in the `ReleaseHubModal` (N7/PR #337), so this is
plumbing the FC pack into a surface that's already built — auto-attach
preferred over a manual pull.

**Trail**
- 2026-08-21 · transcript · src bill-2026-08-21#L87 — ask: replicate the DWL Procore pull on the job log, ideally auto-attaching the FC pack; markup to follow
- 2026-09-02 · transcript · src bill-2026-09-02#L1114–L1157 — restated by Bill and widened: he wants the final PDF packs on **every** release with no extra click — *"the opportunity for those to be in every one of these cards without someone doing an extra click"*. Daniel's read: a **collection script** lands ~80%, improving over time. Bill **accepts a manual attach step as part of the release process in the interim** [#L1118]
- 2026-09-02 · notes · src bill-2026-09-02 — **deferred by Daniel, with a follow-up owed.** Not dropped: *"Procore Final PDF Pack collection for all job log releases (deferred, but will follow up)"*. Re-check trigger: Daniel raises it

### BUG-8 · DWL release-number generator skips the archive
*W3 · built · class fix · due — · deps — · owner daniel · src bill-2026-08-15#L177 · upd 2026-08-15*

Effort S. See the Fix queue and AUD2. Shipped **ahead of** its audit deliberately:
it closes a gap against a rule already enforced and already confirmed correct.

**Built 2026-08-15.** `_globally_taken_rel_numbers` drew its release half from
`active_releases_filter()`, so archiving a release silently handed its number
back to the generator — and the job log, whose constraint is
`(job, release, job_name)` *including archived rows*, rejected it later, after
someone had done the work. `_archived_rel_numbers_for_job` now adds every Rel
that job has ever used to the taken set, and both entry points pass the job:
`next_rel_number(job_number=…)` (resolved in the `/rel/next` route from the
submittal's `project_number`) and `assign_rel_manual`, which reports the archive
collision in its own words rather than claiming an active release holds it.

**Scoped to the job on purpose.** Reserving archived numbers *globally* would
burn the 101–998 range down over a few years — that exhaustion is exactly why
the archive was excluded originally. Scoping to the job number closes the gap the
job log actually enforces and costs nothing (a job holds a handful of releases).
Another job's archived 108 is still fair game. Tests:
`tests/procore/test_rel_assignment.py` (BUG-8 block) + two route tests in
`tests/dwl/test_dwl_routes.py`.

**A second caller was found on verification and fixed the same day:**
`/job-log/release/next-number` — the **Verbal Release form's** prefill, open to
any logged-in user — shares `next_rel_number` with the DWL popup and was calling
it unscoped. The paste path already knows the job number, so it now passes it;
opening the empty modal still can't, and stays unscoped with the submit-time
guard as the backstop. Worth noting because the entry point named in the fix
queue ("DWL number request path") was accurate but not exhaustive.

**The two sides do not enforce the same rule, and should not.** Verified and
pinned in `tests/procore/test_rel_vs_joblog_agreement.py`:

| | rule |
|---|---|
| Job log | (job, release, normalized job_name), archived included |
| DWL | the Rel **value alone** across all active releases (job-agnostic) + pending DRRs + every number **this job** has used, archived included |

The property that matters is containment, not equality: **anything the job log
would reject, the DWL already refuses.** Two deliberate disagreements survive —
the DWL is stricter across jobs on active work (pre-existing design), and it
skips a number an archived row on the same job used even when a *different*
project name would make the job log accept it. That second one is a conscious
trade: `Submittals.project_name` and `Releases.job_name` come from different
sources, so name-matching at suggestion time would miss collisions exactly where
the data is fuzzy. Being stricter costs a skipped number; being looser costs a
rejected release after the work is done.

**Unchanged, and still AUD2's:** collision still **blocks and suggests** rather
than auto-advancing — Bill wants advance [#L173] and that is a client decision,
not a bug fix. Long-term identity likewise.

**Trail**
- 2026-08-15 · build · src — — archive-aware generator, scoped to the job number; block-vs-auto-advance deliberately left to AUD2
- 2026-08-15 · build · src — — verification pass found the Verbal Release prefill (`/job-log/release/next-number`) calling the same generator unscoped; job now passed on the paste path. DWL/job-log containment pinned by cross-check tests, including the two places they deliberately disagree

### BUG-9 · Fab order clunk at paint → complete
*W3 · built · class fix · due — · deps — · owner daniel · src bill-2026-08-15#L201 · upd 2026-08-15*

Effort S (**came in larger than S — it was structural, not a tweak**). *"When
we're getting to the paint department and then complete, it's not flipping the
two and the one… the fab order is being cleared and not cleared — there's just
some clunkiness to the back end"* [#L201].

**Bill twice called it a non-issue; Daniel overrode to high priority — "I want
this clean." Do not wait on Bill to confirm.** The override was right: the
suspicion (tier drift dragging renumber and the shop's ordering with it) was
correct, and the cause was worse than a tier bug.

**Built 2026-08-15. Root cause: the tier rules were implemented once and skipped
three times.** They lived inline inside `UpdateStageCommand`, so they only ran
when a stage change came through that one command. Three other paths write a
stage, and each answered differently:

1. **The inbound Trello sync** (`TrelloListMapper.apply_trello_list_to_db`) —
   *how the shop actually moves work* — set stage and `stage_group` and touched
   `fab_order` not at all. A card dragged out of the paint list kept its tier-2
   value forever. **That is Bill's "not flipping the two and the one" exactly**,
   and it explains why it looked intermittent: the same move made in the Brain
   worked, the same move made in Trello did not.
2. **`update_job_comp` with a percentage** → `Install Start` (a tier-0 stage) via
   `update_job_stage_fields`, leaving whatever the paint deck left behind — so a
   dynamic-band value like 10 sat on a fixed-tier stage and sorted itself in
   among live fab work.
3. **`update_job_comp` with `X`** → `Install Complete`, and it *cleared*
   `fab_order` to NULL — while `UpdateStageCommand` gives that same stage tier 0.
   **One stage, two answers, chosen by which control the office pressed. That is
   the "cleared and not cleared."**

`app/brain/job_log/features/fab_order/tier.py` is now the single rule set
(`plan_fab_order_for_stage` / `apply_fab_order_for_stage`) and all four paths
call it. The rules themselves were never in dispute — they are stated identically
in `FIXED_TIER_STAGES` and in `migrate_unified.py`'s invariants; this makes the
code say them once. Two behavior changes worth naming:

- **Backward moves are repaired.** A release landing on a dynamic stage while
  holding a reserved value (< 3) or NULL — came back down from shipping, or was
  reopened after Complete — used to keep it and sort in front of the entire shop.
  It now goes to the back of that stage's deck (`Released` → the 80.555
  placeholder, matching `fix_null_fab_orders`).
- **The DB field is written even when the audit event deduplicates.** The old
  inline code wrote `fab_order` only inside `if event:`, so a dropped event left
  the release on a stale tier — a second, quieter source of the same symptom.

**Verified through the real webhook path, not just the helper**
(`tests/test_trello_stage_sync.py::TestInboundListMoveRetiersFabOrder` drives
`sync_from_trello` itself). Re-run against the pre-fix `sync.py`, a paint →
shipping card move leaves `fab_order` at **2.0** and writes no `update_fab_order`
event; with the fix it flips to 1 and records the event. The rank gate still
holds — a backward drag changes neither stage nor fab_order, so the sync never
half-applies an inbound it rejected.

**One prior decision was overruled, deliberately:** the comment on the job_comp
percentage path said fab_order was left alone on purpose, and a test asserted it
(`test_job_comp_percent_does_not_clear`). It contradicted the invariant written
down in three places, so the invariant won and the test was rewritten to the
unified rule. Worth a line to Bill only if Install Start ordering looks odd —
it should look *more* correct, not less. Tests:
`tests/brain/test_fab_order_tier.py` (rules, then each write path).

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L201 — reported and self-deprioritized as "really kind of a non-issue"
- 2026-08-15 · decision · src — — elevated to high priority by Daniel over Bill's framing
- 2026-08-15 · build · src — — root cause was scatter, not the tier values: rules extracted to `features/fab_order/tier.py` and applied by the Trello inbound sync and both job_comp paths, which had never applied them; backward tier drift repaired; field write decoupled from event dedup; job_comp-percentage exception overruled in favour of the documented invariant

### BUG-10 · Sub invite email ships a localhost link
*W3 · built · class fix · due — · deps — · owner daniel · src bill-2026-08-15#L81 · upd 2026-08-15*

Effort S — **config, not code.** Bill: *"I did try to do one and I sent it to my
Gmail, and **the link that it sends is like a broken link. It did not work.**"*
[#L81]

**Root cause confirmed in the code:** the invite link is built as
`f"{cfg.APP_BASE_URL}/sub/accept-invite/{raw_token}"`
(`app/brain/tm/subcontractors/command.py:52`), and `APP_BASE_URL` falls back to
`http://localhost:5173` when unset (`app/config.py:60`) — so Bill's Gmail
received a localhost link. Everything else on the path is fine: the frontend
route exists (`App.jsx:91`), the token is hashed with a TTL. **The same variable
builds the T&M ticket-assignment link (`/sub/tickets/<id>`) — broken identically,
just not hit yet.** Fix is setting `APP_BASE_URL` to the real domain in Render;
the prod value is unverified from here. **Rider worth taking: make the fallback
loud** — refuse to send, or log ERROR, when a link would be built against
localhost outside the local environment, so it cannot fail silently twice.

**Blocks A1** (Bill cannot test T&M without a sub in the system) and gates sub
enrollment generally.

**Both halves done 2026-08-15.** The config change landed:
`APP_BASE_URL=https://mile-high-metal-works-trello-onedrive.onrender.com` is set
in Render, so invites now build
`…onrender.com/sub/accept-invite/<token>` — verified against the link builder,
and the Flask catch-all serves that React route (`App.jsx:91`,
`app/__init__.py:697`), so the deep link resolves on a cold open.

The rider is what keeps it fixed. The fallback is no longer silent:
every outbound link now goes through `_external_link` in
`app/brain/tm/subcontractors/command.py`, which **refuses to send** and logs an
ERROR when it would build a link against the localhost default outside a local
environment (`is_local_environment()` in `app/config.py`; anything unrecognised
counts as deployed, so an odd `ENVIRONMENT` value cannot buy a pass). The invite
and resend paths check *before* they write, so a misconfigured environment costs
neither a dead `Subcontractor` row nor a rotated-away token, and the routes
return a 500 that names the actual problem instead of a 502 blaming the mail
server. The ticket-assignment link is covered by the same guard; there the send
is best-effort, so it logs the ERROR and the assignment still stands. Tests:
`tests/tm/test_outbound_link_config.py`.

**Acceptance test not yet run:** nobody has watched a real invite land and open.
Send Bill one — that closes both this and A1's confirmation step. **Two riders
worth carrying:** the guard only fires when `ENVIRONMENT` (or `FLASK_ENV`) is set
to something non-local on the deployed service, so if that variable is ever unset
in a new environment the localhost default goes quiet again; and the current value
is the `onrender.com` host — **when a custom domain arrives, this variable moves
with it**, since the link lands on a subcontractor's phone and outlives the
sending session.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L81 — invite link broken on a real send to an external mailbox
- 2026-08-15 · note · src — — root cause found in code: unset `APP_BASE_URL` → localhost fallback; same var breaks the ticket-assignment link
- 2026-08-15 · build · src — — rider shipped: outbound links refuse to build against the localhost default outside local, checked before any write
- 2026-08-15 · build · src — — `APP_BASE_URL` set in Render to the service's public onrender.com URL; A1 unblocked; first real invite send is still the acceptance test, and the variable moves with any future custom domain

**The items W3 already carried, unchanged by the 8/15 pass:**

### N5 · Shipping-stage date discipline
*W3 · built · due — · deps — · owner daniel · src bill-2026-08-06#L1322 · upd 2026-09-03*

> ✅ **The hard-date color half of this rule was reversed by Bill 2026-08-21 and
> the reversal shipped 2026-08-29** as BUG-11 (see the Fix queue for the build
> notes). *"I might have given you bad information on where we wanted to change
> that"* [bill-2026-08-21#L109]. Hard-date color now **survives the ship stages**
> and dumps on a stage transition into **`Install Start` or any later stage** —
> destination ∈ {`Install Start`, `Install Complete`, `Complete`}, never the
> `start_install` date arriving. Yellow overdue color never silently disappears
> (*"sweeping an issue under the rug"* [#L113] — it's a scored EOS metric).
> The formula-date blanking and the Paint-Complete intercept are untouched, per
> Bill; the hard-date branch left in `shipping_stage_date_discipline.py` is now a
> no-op that **must not be deleted** — it guards hard dates from the blanking
> path below it.

Effort M (grew from S). Formula dates blank at ship stages; hard dates wash
white; Paint Complete + hard date auto-rolls to Ship Planning (generalizes the
ASAP intercept, `stage/command.py:142`). The fork is hard vs formula date
(`start_install_formula` discriminates): formula dates at Ship
Planning/Complete blank `start_install` and `ship_date` with no re-estimation
— an estimate that survived to the truck is stale by definition; a hard date
wins the fork, keeps the date, washes the color. Auto-fill is suppressed in
the no-hard-date flow — ships with modal Break-default (N6 semantics).
Implementation: `shipping_stage_date_discipline.py` called from
`UpdateStageCommand`; tests `tests/brain/test_shipping_stage_date_discipline.py`.

**Trail**
- 2026-08-04 · note · src notes-2026-08-04#notes — "drop ASAP + red after ship complete" — daily notes, no transcript
- 2026-08-06 · transcript · src bill-2026-08-06#L1322 — confirmed in session: scope is all dates at ship stages, not just ASAP red
- 2026-08-08 · decision · src — — fork is hard vs formula date; hard wins, color washes white, auto-fill suppressed, Break on by default; Paint Complete intercept widens from ASAP-only to any hard date
- 2026-08-08 · build · src pr#334 — `shipping_stage_date_discipline.py` + stage intercept + modal Break-default; tests green
- 2026-08-21 · decision · src bill-2026-08-21#L109 — color-wash trigger reversed by Bill: moves from the ship stages to Start Install; yellow stays visible until then; supersedes the 8/15 "confirmed correct in production" banking → BUG-11
- 2026-08-29 · decision · src — — "install starts" means a **stage transition into `Install Start` or any later stage** (destination ∈ {`Install Start`, `Install Complete`, `Complete`} per the order in `app/api/helpers.py:123`), **not** the `start_install` date arriving. A human action, so the color drops when someone says work began; a date-driven dump would fire on schedule through a slip and hide the overdue signal. "Or later" matters: a release can jump Ship Planning → `Complete` and skip `Install Start` entirely. If the crew never moves the stage the color outlives the real start — accepted, and the stage-change photo gate (N9) is the eventual nudge
- 2026-08-29 · note · src — — **naming hazard, called out by Daniel:** `start_install` (date field) vs `Install Start` (stage value) read almost identically and the roadmap's own "start-install trigger" phrasing had already blurred them. Prose here now names the stage in backticks and the date as `start_install`; do not reintroduce the bare phrase
- 2026-08-29 · note · src — — **the mechanism already exists for two of the three stages.** `neutralize_install_date_cascade` (`CascadeReason`) already fires on `stage_set_to_install_complete` and `stage_set_to_complete` (`stage/command.py:289`), so `Install Complete` and `Complete` are done. BUG-11 reduces to: **add** an `install_start` reason and its trigger, and **remove** the two N5 ship-stage reasons (`stage_set_to_ship_planning` / `stage_set_to_ship_complete`) whose hard-date wash lives at `shipping_stage_date_discipline.py:67-73`. The formula-date blanking further down that module (~`:95-120`) is untouched, per Bill
- 2026-09-03 · decision · src daniel-2026-09-03 — **ASAP stops setting a date.** Daniel: *"remove the ASAP text and have the user set an actual hard date. Color dropping rule is unaffected. ASAP mode still gets read and the user clicks ASAP mode, which colors the cell red, but user must set a hard date. Break/link behavior for ship/start install dates is unchanged."* ASAP becomes a pure rush flag over a hand-set hard date — the cell shows that date in red instead of the literal word "ASAP". Carried as BUG-20
- 2026-08-29 · build · src — — **BUG-11 shipped.** `COLOR_DUMP_STAGES` {`Install Start`, `Install Complete`, `Complete`} in `neutralize_install_date_cascade.py` is now the single boundary; `stage/command.py`, `start_install/command.py` and `shipping_stage_date_discipline.py` all read it. The reduction above undercounted by one: `start_install/command.py:114` was a third encoding of the boundary (`no_color = stage in SHIPPING_STAGES` on a hand-typed date). The ship-stage hard-date branch survives as a no-op guard — it is what keeps hard dates out of the formula blanking below it. An integrity test ties the set to the tail of the canonical stage order so "or later" cannot rot
- 2026-09-02 · transcript · src bill-2026-09-02#L283 — **Bill confirmed the shipped rule is correct**: colour dumps at Start Install, and if no hard date exists at Start Install one is set to the start date. Validates the BUG-11 ship of 2026-08-29. Colour semantics restated for the record: **yellow = one day past due, day-of stays green** [#L257]
- 2026-09-02 · transcript · src bill-2026-09-02#L243–L290 — **open question, Bill owns it.** The rule is right but he is not satisfied, because one of his **EOS measurables is how many hard dates are in play** and he does not want to lose hard-date visibility when the colour goes. Options he floated: a gold/yellow **band** around the cell keeping the base colour inside; faded/opaque variants; **bolding hard dates in addition to colouring**. Alternative he raised himself: change his own metric to *"yellow dates that are not shipped"*. **Decision deferred deliberately — Bill is thinking about it and will come back.** He was candid about the churn: *"I made you change this thing so many times I got confused on what was actually happening"* [#L288]
- 2026-09-02 · notes · src bill-2026-09-02 — related but separate, and decided: **ASAP drops its text.** Filed as BUG-20

### N7 · Job log modal merge + redesign
*W3 · built · due — · deps — · owner daniel · src — · upd 2026-08-09*

Effort M. **Core shipped 2026-08-06** (PRs #326/#330/#333): unified
`ReleaseHubModal`, the token/lattice design system across Job Log · Events ·
DWL · Archive, opt-in Left Sidebar Mode. **Both remaining items shipped
2026-08-09 in PR #337:** the change-log feed became a Change Log tab rendering
plain-language field diffs grouped by day with undo on the entry (the Events
page keeps the raw table), the notes rail became a full activity feed merging
notes with stage/fab/date updates, and the bottom progress bar was replaced by
the banana-code icon flow exactly as predicted — one `StageIconRow` import
(`JobDetailsBody.jsx:478`). Functionality stayed frozen; this was UI only.

**PR #337 also shipped something not on this roadmap:** an Attachments tab
with an in-modal read-only PDF viewer (`PdfReadViewer.jsx` — fit/width/zoom,
page nav, no new window), with Carmen's drawing review inside it and opened to
drafters as well as admins. That is C3 ground arriving early and by a side
door — see C3's trail.

**Trail**
- 2026-08-06 · note · src — — was in flight, uncommitted, on the `feature/unified-release-modal` worktree
- 2026-08-06 · build · src pr#326 — unified `ReleaseHubModal` core merged
- 2026-08-06 · build · src pr#330 — lattice/token design system across Job Log · Events · DWL · Archive
- 2026-08-06 · build · src pr#333 — opt-in Left Sidebar Mode
- 2026-08-08 · note · src — — client requirements added: main-card change-log feed (dates + stage changes off `ReleaseEvents`) and banana icon flow replacing the progress bar; functionality frozen, UI only
- 2026-08-09 · build · src pr#337 — both remaining items shipped: Change Log tab (plain-language field diffs by day, undo on the entry) + activity feed; banana icon flow replaced the progress bar via one `StageIconRow` import
- 2026-08-09 · build · src pr#337 — unplanned: Attachments tab + in-modal read-only PDF viewer (`PdfReadViewer.jsx`), Carmen drawing review inside it, opened to drafters; overlaps C3-narrow

### N9 · Photo stamp + GPS
*W3 · not-started · class build · due — · deps — · owner daniel · src bill-2026-08-06#notes · upd 2026-09-16*

**Elevated 2026-08-21 — Bill wants it "in the short timeline"** [bill-2026-08-21#L67],
now second in `queue.next`. The 8/21 session pinned the spec down:

- **It's a stamp, not a watermark** — a text string across or on the bottom;
  placement is free, **consistency is mandatory** [#L73].
- Content: **job number, release number, stage, who took the photo** [#L73] —
  and the stage is the **stage at the time of the photo**, not the current one
  [#L77], precisely so a "paint complete" claim can be checked against an
  unpainted photo. The 8/6 list also carried **date + GPS**, and Bill pointed
  back at it rather than replacing it (*"the notes on exactly what we wanted"*
  [#L67]). **Resolved 2026-08-21 (Daniel): build to the union** — job, release,
  stage-at-photo-time, who, date, GPS. Six fields is a long string, so the
  render has to stay legible: that is a layout problem to solve, not a reason
  to drop a field.
- Purpose has sharpened: **invoicing evidence — Katie sends stamped photos
  straight to customers** [#L77], which makes this J1's enabler explicitly.
- The stage-vs-upload ordering race (photo uploaded before the stage flips):
  **ship it, then see** — worst case the crews are told "change the stage
  before you add the photos"; a stage-change **gate** ("did you add the
  photos?") is the possible future fix [#L81].
- Rider asks from the same session: photos should render in the modal's
  existing **preview area** (bigger, contained in-system) with an
  open-in-new-window escape hatch, and the field guys want to **mark up on top
  of photos** [#L69] — the markup half is C3 ground (one markup stack, not
  two), noted on C3's trail.

**Open question 3 (shared-tablet attribution) is RESOLVED 2026-08-29 (Daniel):
individual Brain logins on the shared tablets.** The stamp renders `who` from the
logged-in user with no new capture UI — no picker, no device-name fallback, no
blank-on-tablet case. Attribution then matches the rest of the audit trail, which
matters because these photos are invoicing evidence going to customers.

**It buys correctness with friction and with a rollout, and both are real.**
Everyone who photographs anything needs their own account and has to be logged in
as themselves on a shared device — that is an operational prerequisite, not a code
one, and it lands on **T2** (member management: add people, assign permissions,
invite). N9 does not *block* on T2 — the stamp reads `get_current_user()` either
way — but a stamp shipped before the accounts exist prints one generic name on
every photo, which is the exact failure the question was asked about. **Ship the
accounts alongside the stamp, not after it.** Worth re-checking with Bill once the
crews feel the login friction; the picker stays the fallback if it doesn't hold.

Effort M — the metadata is free, the rendering is not. Stamp uploaded job-log
photos with date, who took it, current stage, plus GPS. Three of the four
fields already exist on `ReleasePhoto` (`app/models.py:1053`); only GPS is a
new column. But there is **no image library in this codebase** — watermarking
adds an image pipeline (Pillow) plus **`pillow-heif`** (iPhones/iPads shoot
HEIC; `save_photo` stores it undecoded). Keep the original clean, generate a
stamped derivative. **Capture standard settled:** browser geolocation at
upload is the primary source (EXIF GPS tested absent on a real field photo —
transit re-encode drops the GPS IFD; capture `DateTime` survives and is
preferred over `uploaded_at`); EXIF GPS opportunistic only; record which
source each coordinate came from; the geofence
(`drafting_work_load/service.py:682`, PostGIS point-in-polygon) marks
"verified on site"; three provenance states with "no location" visible, never
silently degraded; a location denial never blocks the upload; personal phones
get gesture-only prompts, never background location; cellular tablets are a
**standing purchase spec** (Wi-Fi-only iPads have no GNSS). Pitch as site
verification (5–20 m), not position tracking. **Open question 3 (shared-tablet
attribution) is resolved — individual logins**, so what gets rendered is settled
and the build can start. This is what makes J1 work.

**The capture standard changed under this item on 2026-08-24 and the plan above
is now partly obsolete.** PR #349 added a client-side compressor
(`frontend/src/utils/imageCompress.js`) and wired it into the job-log release
photo upload (`PdfVersionHistoryModal.jsx:271`). It decodes the file and
re-encodes through `canvas.toBlob(..., 'image/jpeg')`, which emits a **fresh JPEG
carrying no EXIF at all** — for every file over its 600 KB skip threshold, i.e.
every phone shot (3–12 MB). Consequences for N9:

- **EXIF is not "opportunistic" any more, it is gone.** The GPS IFD was already
  absent in transit; now the whole block is stripped client-side before the
  server sees the bytes. Browser geolocation at upload is the *only* location
  source, not the primary one.
- **Capture date needs a new source.** The trail below prefers EXIF `DateTime`
  over `uploaded_at`; that field no longer arrives. The compressor *does*
  preserve `file.lastModified` onto the new `File`, which is the usable
  stand-in — otherwise read EXIF in the browser **before** `compressImage` runs
  and post it alongside the file.
- Either fix lands in the upload path, so decide it with Open question 3 rather
  than after the watermark is built.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#notes — client ask: stamp date, who took it, current stage, GPS coordinates
- 2026-08-06 · note · src — — EXIF test on a real field photo (Pixel 6a): Make/Model/DateTime survived, GPS IFD absent — re-encoded in transit; do not build on EXIF GPS
- 2026-08-06 · decision · src — — browser geolocation primary, EXIF opportunistic; capture date from EXIF falling back to uploaded_at; provenance recorded per coordinate; denial never blocks upload; cellular-tablet standing purchase spec (company iPads confirmed cellular)
- 2026-08-06 · question · src — — opened Open question 3: shared-tablet attribution; decide before the watermark is built
- 2026-08-21 · decision · src bill-2026-08-21#L67 — elevated to the short timeline; stamp-not-watermark, content pinned (job/release/stage-at-photo-time/who), Katie-to-customer invoicing purpose, ship-then-tweak on the ordering race, stage-change photo gate as the future option; in-modal preview + photo-markup rider asks logged
- 2026-08-21 · decision · src — — stamp field list is the **union** of the 8/6 and 8/21 lists (job, release, stage-at-photo-time, who, date, GPS); Daniel's call — Bill referenced the 8/6 notes rather than superseding them. Legibility of a six-field string is a layout problem, not grounds to cut a field
- 2026-08-29 · decision · src — — Open question 3 answered: **individual Brain logins on shared tablets**, not a capture-time picker. Stamp reads the logged-in user; correctness over friction, because the photos are customer-facing invoicing evidence. Carries an account-rollout prerequisite onto T2 — ship the accounts with the stamp, or every tablet photo prints the same generic name
- 2026-08-29 · note · src pr#349 — client-side JPEG re-encode now strips EXIF from every job-log photo over 600 KB; browser geolocation becomes the sole location source and capture date must come from `file.lastModified` or a pre-compression EXIF read. Supersedes the "EXIF opportunistic / capture DateTime preferred" half of the 2026-08-06 capture standard
- 2026-09-02 · transcript · src bill-2026-09-02#L60 — **Bill re-elevated it unprompted**: the photo watermark/text stamp is *"something I need to push into the higher priority"*. Consistent with its existing position at #2 in `queue.next`; no reorder needed
- 2026-09-14 · decision · src thisweek-2026-09-14#§5.4 — the stage-change photo gate this item deferred ("ship it, then see" [bill-2026-08-21#L81]) is now asked for as **T13**, which also adds a location field. N9 sits behind T13 in `queue.next` on purpose: the gate is the capture path, the stamp renders onto what it captures — one upload path, not two. Not a demotion of Bill's 9/2 re-elevation; the package does not mention the stamp at all
- 2026-09-16 · transcript · src bill-2026-09-16#L1441–L1459 — **stamp is live and working**: new photos carry who / date / stage (*"photo added in ship planning by Keith Powell"*); older photos don't
- 2026-09-16 · notes · src bill-2026-09-16 — a **per-project photo directory** filterable by stage and shop-vs-field [#L502–L516] is a **long-term goal**, not scheduled

### H1 · Polish sweep
*W3 · not-started · due — · deps N7 · owner daniel · src — · upd 2026-08-06*

Effort M. Rolling calendar, full-screen modals, metrics load times, and the
"left sidebar mode" toggle in the theme settings (alongside dark mode /
old-man mode, `ThemeContext.jsx`). Collapse ⑥ split this: bugs are not
polish, and N7 is too big for a sweep.

**Trail**
- 2026-08-06 · decision · src — — collapse ⑥: H1 splits — the bug pile and N7 leave the sweep

---

## Workstream 4 — Carmen

### N8 · Carmen admin reporting — EOS metrics
*W4 · built · due — · deps — · owner both · src bill-2026-07-22#notes · upd 2026-08-09*

**Built 2026-08-09** (PR #338). The metrics list was walked and the derivable
ones built: hours released to production, fabrication hours, QC completed, fab
backlog, yellow dates, T&M hours, target dates met — each computed Monday–Sunday
to match the scorecard columns. It shipped as the tool it was scoped as, not a
page: `get_eos_metric` / `get_eos_metrics_for_owner` in
`app/brain/carmen_chat/tools.py` over `carmen_chat/eos_metrics.py`, owner-aware
across David / Bill / Luis / Doug, so *"David's numbers"* or *"my metrics"*
resolves. `scripts/eyeball_eos_metrics.py` is the check harness. **Phase two
(C10 — Carmen running Brain actions) stays parked**; the read-only half is what
shipped, which is the leash-loosening order Bill described. Which metrics
proved *non*-derivable was not recorded as findings — that was part of the
method and is worth capturing before the gap is forgotten.

*The pre-build framing, retained for the record (2026-08-06):* started as
"David's fab hours report." It is not a report page — it is a **Carmen tool**: *"Hey Carmen, pull my EOS data for last week."* Method:
take the EOS metrics the client actually tracks, walk them one by one,
identify which are derivable from current data, build against those; the gaps
become their own findings. **Absorbs C10** (collapse ③) — the same capability
read-only first (pull, summarize, report), which is the progressive
leash-loosening path Bill described on 7/22 and gives C10 the trigger it never
had. Ships on `app/brain/carmen_chat/tools.py`, which already does
tool-calling. **Bill has the metrics list in hand; it needs walking** (Owed).

**Trail**
- 2026-07-22 · transcript · src bill-2026-07-22#notes — "then progressively letting the leash off as tasks prove repeatable"
- 2026-08-06 · decision · src — — collapse ③: N8 absorbs C10 — read-only first; C10 becomes N8's second phase
- 2026-08-06 · note · src — — Bill has the EOS metrics list; walking session pending
- 2026-08-09 · build · src pr#338 — seven Mon–Sun metrics shipped as Carmen tools (`get_eos_metric`, `get_eos_metrics_for_owner`), owner-aware across David/Bill/Luis/Doug; C10 phase two still parked
- 2026-08-09 · note · src — — the non-derivable metrics were never written down as findings; the gap the method was supposed to produce is currently unrecorded

### N11 · Carmen prompts the PM on a yellow date
*W4 · not-started · class build · due — · deps — · owner daniel · src bill-2026-08-15#L137 · upd 2026-08-15 · awaiting bill/distribution-channel*

Effort S–M — **most of the infrastructure already exists.** Bill's ask [#L137]:
*"when a yellow date comes up, that **Carmen sends an email to the project
manager** with a summary of: here's the project, here's the stage changes, and
this is the current install date. **What are we going to do here?**"*

Note the shape — **a prompt, not an alert.** It states the situation and asks the
PM to decide, which matches the Carmen-asks-questions direction from July and the
AUD1 agency principle: it prompts a human rather than adjusting the date itself.

Why it is cheap: **N8 already computes the yellow-dates EOS metric** (the
detection half), G1 ships the notification stack, and Carmen's mailer is live. Why
it matters: PMs are in the field, so **G1's in-app notification is foreground-only
and never reaches them** — and *"one of our metrics for our **L10s** is yellow
dates on the job log"* [#L139], so this drives a number Bill is already scored on.

**Open before build — confirm with Bill: the distribution channel** (email,
in-app, or both). Carried into that conversation: **trigger discipline** —
on-transition-to-yellow versus a daily digest of everything currently yellow,
which is really a channel question in disguise.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L137 — Carmen emails the PM a project/stage/install-date summary and asks what to do
- 2026-08-15 · transcript · src bill-2026-08-15#L139 — yellow dates are a scored L10/EOS metric; PMs are in the field where in-app notification does not reach
- 2026-08-15 · decision · src — — deferred pending Bill's channel confirmation; trigger discipline rides along
- 2026-08-21 · note · src bill-2026-08-21#L113 — the metric's meaning reaffirmed while reversing the color rule: yellow dates must stay visible ("sweeping an issue under the rug" to hide them) — this item's detection input is unaffected by BUG-11's trigger move

### N13 · Carmen prompt library — exposed in-app
*W4 · not-started · class build · due — · deps — · owner daniel · src bill-2026-08-21#L119 · upd 2026-08-21*

Effort S. Bill independently asked for *"canned prompts for Carmen… a prompt
library to some extent"* [#L119] — which already exists server-side: Carmen
routes queries against Daniel's prompt library, each prompt bound to a specific
tool set (deliberately, for the audit trail once Carmen graduates from reading
to writing). Agreed in session: **a button inside Carmen chat opening the
library** (goal + prompt text), visible to anyone with Carmen access — the
flag-gated handful. Daniel also sends Bill the current library directly.

**Add-a-prompt stays restricted, by Bill's own caution:** a prompt without a
data path behind it is worthless (*"you can't really add a prompt if we don't
have the ability to find the information"* [#L125]) — he's hit "I'm not
programmed to do that yet" already. New-data requests route through Daniel for
now; self-serve prompt authoring waits until the tool surface is broader.

**Trail**
- 2026-08-21 · transcript · src bill-2026-08-21#L119 — prompt library asked for; already built server-side; expose read-only in chat
- 2026-08-21 · decision · src bill-2026-08-21#L125 — add-permission restricted; new-data asks go through Daniel; Daniel to send Bill the current library

### N16 · Carmen: hours released to the job log, by billing tag
*W4 · built · class fix · due — · deps N1 (tag data) · owner daniel · src daniel-2026-09-05 · upd 2026-09-05*

Effort S. **Daniel's ask, 2026-09-05 — and the reason W4 comes to the front.** An
**all-admin prompt**: the user names a **time frame**, Carmen returns the **hours
released to the job log** in that window **broken down by billing tag** —
Contracted / Change Order / MHMW Cost. Not owner-scoped, not a new scorecard
column: any admin can run it.

**Most of it is already built.** The metric exists as
`hours_released_to_production` (`app/brain/carmen_chat/eos_metrics.py`) and is
exposed twice — through `get_eos_metric(metric=…)` and through the dedicated
`TOOL_HOURS_RELEASED` alias in `carmen_chat/tools.py`. It already sums `fab_hrs`
over `Releases.released` inside a window, excludes archived rows, and counts a
zero-`fab_hrs` release rather than skipping it. `Releases.release_tag` shipped
with **N1** on 2026-08-09 (migration run 8/10) and is required at creation on both
the pasted and verbal paths. So the build is two changes:

1. **Unlock the window.** The tool advertises `_WEEK_PROPS` only — `weeks_back`
   and `week_of` — and `resolve_week` snaps any anchor to its **Monday–Sunday**
   bounds. "User requests time frame" means an arbitrary `start`/`end`. Add the
   range to the metric and to **both** tool schemas, keeping Mon–Sun as the
   default so **N8**'s scorecard semantics are untouched.
2. **Group by `release_tag`.** One `group by` over rows the query already loads.

**The data is the real work, and it needs Bill.** Measured read-only on sandbox
2026-09-05: of the **99** releases with a `released` date on or after 2026-08-09 —
the day the tag became required — **91 are untagged**. System-wide only **12 rows
carry a tag at all**, effectively a pilot on job 640. The forward path is sound:
new releases arrive tagged, so the corpus grows from here. But it is roughly two
weeks deep, and **N10's bulk-edit backfill — the mechanism N1 explicitly deferred
the backfill to — has not run.**

**Consequence, and the decision to take to Bill before this ships:** the answer
must carry an explicit **`untagged`** bucket, and for any window reaching back
before mid-August that bucket *is* the answer. Ship it visible rather than
silently dropping untagged hours — a total that quietly omits 92% of the work is
worse than one that says so out loud. The question for Bill is whether the number
is useful enough to hand over before **N10** backfills, or whether N10 comes
first; that is a call about what he'll do with the figure, not a build question.

**Built 2026-09-05** on `feature/carmen-hours-by-tag`. The window and the breakdown
landed together on the existing metric rather than as a new one, so there is a
single definition of "hours released" and no second number to keep in sync:

- **`resolve_window` replaces the week-only path.** No `start`/`end` → the
  Mon–Sun week, byte-for-byte what the scorecard meant before. Either bound →
  the exact span, with `start` omitted meaning **no lower bound** (that is the
  shape behind an all-time total) and `end` omitted meaning today. Reversed
  bounds are swapped rather than returning an empty window, because a model that
  inverted them is asking for the same span either way.
- **`week` is omitted in range mode, not filled with range bounds.** The payload
  always carries `window` (with an explicit `mode`); the historical `week` key
  survives only where it is true. Nothing downstream can read an arbitrary span
  as a Mon–Sun week.
- **`by_tag` always renders in canonical order with `Untagged` last**, and an
  unknown tag value falls into the untagged bucket rather than inventing a
  category. `tag_coverage` states `tagged_releases` / `untagged_releases` /
  `untagged_fab_hrs` / `tagged_pct`, and a test asserts the per-tag figures sum
  back to the headline so nothing can be silently dropped.
- **The range is offered only where it means something.** `RANGE_CAPABLE_METRICS`
  is `{hours_released_to_production}`; asking for a range on a weekly-by-definition
  metric returns an **error**, not a quietly-substituted week, and the weekly tools
  do not advertise `start`/`end` in their schemas at all.
- **Admin-wide, as asked.** The tool was never owner-gated — access is the route's
  `carmen_chat_required`, which admins always pass — but the payload's David
  framing made it *read* like his scorecard line. The tool description and the
  system prompt now say plainly that it is not owner-restricted and that the
  number is the company's. Any admin (Daniel, David, Bill, Katie, …) can ask it.
- **The prompt does the honest-reporting work.** Carmen is instructed to always
  state the untagged share when it is non-zero and never to present a tagged
  subtotal as the whole — the guardrail that keeps the thin tag corpus from
  producing a confidently wrong number.
- **The NaN landmine was closed while in there** — `finite_hours` reads non-finite
  `fab_hrs` as zero at the point of the read rather than relying on the archive
  filter that happens to be hiding those nine rows today.
- `scripts/eyeball_eos_metrics.py` gained `--start` / `--end` and prints the tag
  split, so the check harness covers the new shape.

**Verified against sandbox 2026-09-05** (read-only, via the eyeball script):
Aug 1 – Sep 5 returned **34 releases · 639.58 fab hrs**, split Contracted 75.2 /
Change Order 34.5 / MHMW Cost 12.0 / **Untagged 517.9 across 25 releases** — i.e.
**81% of the hours in that window are untagged**, which is exactly the shape the
Owed decision is about. The number is correct and the caveat is doing its job.

**Relationship to the other Carmen items.** This is the first *concrete instance*
of the ad-hoc query need **N15** was filed against — Bill's own worked case there
was the same shape (total fab hours on job 500, at project close, across archive
and active). Build it as a **prompt in the library (N13)**, not as a one-off tool,
so the pattern is reusable; it is deliberately **not** blocked on N15's CarMini /
CarMid / CarMax tiering, which carries `deps T2` and is a much larger piece.

**Landmine, not a defect.** Nine rows hold a literal **`NaN`** in `fab_hrs` (and
`install_hrs`) — all archived, all legacy `V###` release numbers. The metric's
non-archived filter shields it today; a single NaN would poison the sum and emit
invalid JSON. **Any variant that drops the archive filter inherits it** — including
N15's *"across archive and active"* — so coerce non-finite values to zero at that
point rather than discovering it in an answer.

**Trail**
- 2026-09-05 · decision · src daniel-2026-09-05 — filed and queued to `queue.now`: an admin prompt taking a user-specified time frame, returning hours released to the job log with the billing-tag breakdown
- 2026-09-05 · note · src — — code read: the metric and both tool entry points already exist; the only structural gap is that the window is locked to Mon–Sun by `_WEEK_PROPS` / `resolve_week`
- 2026-09-05 · measurement · src — — tag coverage on sandbox: **91 of 99** releases with a `released` date ≥ 2026-08-09 are untagged; 12 tagged rows system-wide. An explicit `untagged` bucket is mandatory, and N10's backfill is what makes the breakdown mean anything historically
- 2026-09-05 · finding · src — — nine archived legacy rows carry `NaN` in `fab_hrs`/`install_hrs`; harmless behind the current archive filter, poisonous to any archive-inclusive variant
- 2026-09-05 · decision · src — — ships as an **admin-wide prompt**, not an owner metric: `hours_released_to_production` is registered to **David** in the `OWNERS` registry, so "my metrics" as Bill would never reach it
- 2026-09-05 · decision · src daniel-2026-09-05 — **all admins use this tool** (Daniel, David, Bill, Katie, …). No new gate was needed — `carmen_chat_required` already admits every admin — so the change is to the *framing*: tool description and system prompt now state it is not owner-restricted
- 2026-09-05 · build · src — — **built** on `feature/carmen-hours-by-tag`: `resolve_window` (week ⟷ arbitrary range, unbounded-below supported), `by_tag` + `tag_coverage` with an explicit untagged bucket, `RANGE_CAPABLE_METRICS` so a range on a weekly metric errors instead of silently returning a week, `finite_hours` closing the NaN landmine, prompt guidance requiring the untagged share to be reported, and `--start`/`--end` on the eyeball harness. 12 new tests in `tests/carmen_chat/test_tools.py`
- 2026-09-05 · verification · src — — read-only sandbox run, Aug 1 – Sep 5: 34 releases, 639.58 fab hrs, **81% of hours untagged** (517.9 of 639.58 across 25 releases). Confirms both the query and the reason the untagged bucket had to be visible

### N17 · Carmen chat surface — side-push panel, poppable out
*W4 · not-started · class fix · due — · deps — · owner daniel · src bill-2026-09-02#L1305 · upd 2026-09-05*

Effort S. **Filed 2026-09-05 from the 2026-09-02 session, where it was decided and
then never carried onto this map.** Bill wants Carmen's chat as a **full side-push
panel that can be popped out** — explicitly *not* the small popup [#L1305–L1318].
The named design reference is the **Gemini-in-Chrome sidebar**, which is also what
seeded **N15** and the write-back thread; the mechanic he liked was that *it only
knows what it has seen*.

**What it changes.** `BBChatWidget.jsx` today is a 420px panel that drops from the
CM bubble beside the notification bell and grows down and left, with three stated
invariants in its header — *"No floating bottom bubble"*, *"Panel drops from the CM
bubble… it does not cover the last Job Log row"*. A side-push panel **retires those
invariants** and changes the page's layout contract rather than overlaying it, so
`AppShell` is in scope, not just the widget. Pop-out is a second surface (its own
window rendering the same chat) — worth confirming whether Bill means a real
window or a maximised in-page mode before building.

**Rides with it — one question at a time** [#L1263–L1270]. Bill called the pattern
a *"game changer"* and named the failure it fixes: six questions at once, most of
which don't make sense, where answering the first would have answered two others.
That is a **prompt-side** change, not a UI one, and it applies to every Carmen
surface — chat, PDF review, meeting extraction. Cheap, and it belongs in whichever
of these ships first.

**Not queued** — recorded so the decision survives. Sequence it behind **N16**,
which needs none of it.

**Trail**
- 2026-09-02 · transcript · src bill-2026-09-02#L1305–L1318 — chat is a full side-push panel, poppable out; not the small popup
- 2026-09-02 · transcript · src bill-2026-09-02#L1263–L1270 — **ask one question at a time**: *"game changer"*; the alternative is six questions where the first answers two others
- 2026-09-02 · note · src bill-2026-09-02#L66–L73 — the Gemini-in-Chrome sidebar is the named reference for both this and N15
- 2026-09-05 · note · src — — filed on the roadmap-staleness pass; the 2026-09-02 roll-up carried both decisions in the findings file but neither reached an item. Retiring `BBChatWidget`'s three placement invariants is the actual scope, and it reaches `AppShell`

### N18 · Carmen drawing chat — PDF in context, beside the review
*W4 · not-started · class build · due — · deps — · owner daniel · src bill-2026-09-02#L1239–L1291 · upd 2026-09-07*

Effort M. **Not N17.** That is the *global* chat surface — side-push, poppable,
retiring `BBChatWidget`'s placement invariants. This is a chat **scoped to one
drawing version**, living in the release hub's Review tab beside the findings, and
it needs none of N17's layout work. N17's prompt-side rule — **one question at a
time** [#L1263–L1270] — does apply here, as it does to every Carmen surface.

Splits Carmen's drawing work in two, which is how Bill described it
and how the surfaces differ in cost. **Full review stays the heavy tool**: a
minutes-long Opus pass on a background thread whose findings are **saved per
drawing version** (`CarmenDrawingReview`, keyed release + version + attachment)
and keep the findings-to-page click-through Bill called *"fucking great"*.
**Chat is the fast path**: the open version's PDF is already the context, so a
drafter can ask one-offs — *"summarize the v3 markups"*, *"does every hole have
hardware that fits"* [#L1251] — **before or after** a review exists, and get an
answer in seconds rather than minutes.

Two thirds of it is already in the repo. `carmen_chat/agent.py` does
`cache_control: ephemeral` prompt caching and `carmen_chat/pricing.py` already
accounts `cache_read` / `cache_write` tokens into per-turn cost;
`pdf_review/service.py` already ships a version's full PDF as a base64 document
block. New: `pdf_review/chat.py` (PDF block + context header — version meta,
markup summary, the saved review's findings when one exists, comments — plus the
turns), one `POST /brain/releases/<id>/drawing/versions/<vid>/carmen-chat` route
at drafter-or-admin, and the chat panel under the pinned findings in the release
hub's Review tab, per the 3a design.

**Two decisions taken at scoping.** ① **Prompt-cache the PDF block.** Turn one
pays to upload the drawing set; follow-ups read it from cache. Without this each
question re-ships 1–2 MB and the feature is too expensive to use casually, which
defeats its purpose. ② **Chat runs Sonnet, review stays Opus** — the alias split
already in `pdf_review/service.py`. Chat wants seconds; review can take minutes.

Chat turns are **session-only in v1** — no table. Persisting a thread per
drawing version is one small table if it turns out reviewers want to re-read
what Carmen said last week; reviews are already durable, so the durable half of
Bill's ask is covered.

**The training blocker Bill named is now half-solved.** He said *"our markups
live in Procore and never reach the Brain"* [#L1249]. The Final PDF Pack puller
(N14) pulls the approver's returned set — markups burned in by Procore's markup
renderer — into a release drawing version, so approver markups now land in the
Brain as PDF annotations. **Mile High 101 into the model** [#L1234] is still
open and is the other half.

**Trail**
- 2026-09-02 · transcript · src bill-2026-09-02#L1239–L1291 — side-push chat that sees the full document *and* the findings, can be asked questions, updates its own memory; review keeps findings-to-page
- 2026-09-07 · decision · src — — split confirmed in session: review = heavy tool saved per markup version; chat = fast path with the PDF as context, usable pre/post review. Prompt caching and the Sonnet/Opus split settled at the same time; v1 chat is session-only
- 2026-09-07 · note · src — — scoped while building the hybrid viewer on `fix/improved-pdf-modal`; **deliberately not built there** — that branch already carries the viewer rebuild, the FC pack puller, the 4c markup chrome and the hub header changes. Chat lands on its own branch off it so the AI feature is reviewable on its own

### N20 · Carmen: Dencol drawing vs. order-confirmation cross-check
*W4 · not-started · class build · due — · deps — · owner daniel · src bill-2026-09-16#L370 · upd 2026-09-16*

Effort S to test, M to build. **Opportunity, not critical** (Daniel). The shop
verifies plate cuts against the drawing PDF by eye; the Brain already lands Dencol
order emails (`project_supplier_order_tracking`). Ask: ingest the **drawing PDF we
send Dencol** (DXF not needed [#L350]) with **Dencol's order confirmation** and have
Carmen confirm every part is on the order [#L370–L381]. Likely Dencol only [#L379].
**First step is a test**: one real pair, confirm the two actually reconcile before
building anything. Aside: Gary BCCs Carmen on a large volume of email nothing
processes yet [#L329–L338].

**Trail**
- 2026-09-16 · transcript · src bill-2026-09-16#L272–L383 — Louie's team checks prints, not the order checklist; Bill asks for the PDF-vs-order cross-check
- 2026-09-16 · notes · src bill-2026-09-16 — test drawing PDF vs order first; not critical

---

## Parked — real work, off the path

**Read "October" in this section as the old W1 window.** These blocks were parked
against a deadline that no longer exists (2026-08-15), so their re-check triggers
are still valid as *dependency* statements — "after P2 ships" — but their urgency
language is historical. Anything whose trigger is a W1 item is now gated behind
that lane reopening.

Each block states its re-check trigger. Also parked without blocks here
(reasoning retained in `docs/feature-catalog.md`): ~~**D2** personal page~~ *(un-parked 2026-09-16 — now **N19**)* ·
~~**D4** timeline view~~ *(un-parked 2026-08-15 — dissolved into **T1**)* ·
~~**A3** punch list~~ *(un-parked 2026-08-20 — dissolves into **T6**)* ·
**A4** lookahead upload + markup *(the spec's §5.4 look-ahead attachment is T1
Phase-B ground; A4's markup half stays parked)* ·
**F1** meeting extraction bands · **E1–E3** tee-time (**N4 gate cleared
2026-08-09** — now parked on October scope alone, not on a dependency) · **L1**
styling v3 (unambiguous: not before October) · **I1** OCIP remainder (argued
against cutting — it has a compliance failure behind it) · **C5 + K1** accept
into knowledge base + learning substrate (K1 decision due before C5) ·
**C10** Carmen runs Brain actions (N8's second phase — N8's read-only half
shipped 2026-08-09, so C10 now has the predecessor it was waiting on) · **C2**
parts + hardware list (experimental). *(I4 left this list on 2026-08-10 —
shipped; see Workstream 2.)*

### P3 · Carmen review as a workflow step
*W1 · parked · due — · deps P2,C3 · owner daniel · src bill-2026-08-06#notes · upd 2026-08-06*

Effort M. Carmen review as a step in the P2 workflow; entry point is the
reviewer response. Deferred past October because the review can be run
manually today — this is the value-add, not the replacement. **Re-check
trigger:** P2 + C3-narrow shipped; first item in the post-October lane.

**Trail**
- 2026-08-06 · decision · src — — deferred past October in the reduced scope; manual review exists

### P5 · FC Separator / Phaser
*W1 · parked · due — · deps P4 · owner daniel · src bill-2026-08-06#L1430 · upd 2026-08-06*

Effort M–L. The only sanctioned FC → many-releases path: one fab-only release
(all fab hours, zero install, stops at welded QC → paint) + N install releases
(zero fab, hours apportioned — location from the description, quantity drives
the hours). Replaces Colton's copy-paste-delete ritual. **Re-check trigger:
Bill's committed trigger when 500-998 goes to FC** — do not finalize the UX
before that lands; deferred past October (the ritual works today).

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#L1430 — the only sanctioned FC→many path; "there's a thousand hours and a thousand pieces, we have 200 here, there's 200 hours"
- 2026-08-06 · transcript · src bill-2026-08-06#L1451 — replaces the manual copy-paste-delete ritual
- 2026-08-06 · transcript · src bill-2026-08-06#L1488 — design against 500-998; Bill committed to trigger us when it goes to FC

### P6 · Distribution — cover sheet + PDF, sent from Carmen
*W1 · parked · due — · deps P2 · owner daniel · src bill-2026-08-06#notes · upd 2026-08-06*

Effort M. Distribution package — cover sheet + PDF, sent from Carmen
on-behalf-of, with a 2-week follow-up. Deferred past October: the manual
process (download, find the file, email it) exists and works. **Re-check
trigger:** post-October lane, after P2 ships.

**Trail**
- 2026-08-06 · decision · src — — deferred past October in the reduced scope; manual distribution works today

### P8 · Aging / outstanding view
*W1 · parked · due — · deps P2,D1 · owner daniel · src bill-2026-08-06#notes · upd 2026-08-06*

Effort S–M. Aging/outstanding view siloed by our phases — **status + timer,
not a real Carmen queue** (resolved 2026-08-06: defer the real
ball-in-court queue). Deferred past October: nobody has this view now either.
**Re-check trigger:** post-October lane, after P2 + D1.

**Trail**
- 2026-08-06 · decision · src bill-2026-08-06#notes — ship status + timer; the real Carmen queue is deferred
- 2026-08-06 · decision · src — — deferred past October in the reduced scope

### K2 · Grid engine
*W0 · parked · due — · deps — · owner daniel · src — · upd 2026-08-06*

Effort L. The shared grid engine, now serving D1 and the future invoicing
tab. **Re-check trigger:** when D1-full or the invoicing tab (N2b) needs it —
not before October.

**Trail**
- 2026-08-06 · note · src — — parked; consumers are D1 and the invoicing tab

---

## Blocked

| ID | Blocked on | Since | The explicit ask |
|---|---|---|---|
| **A1** | ~~BUG-10~~ **cleared; now deliberately queued behind T1** | 2026-08-15 | BUG-10 landed 2026-08-15 (first real invite send still owed as the acceptance test). Then Bill re-sequenced 2026-08-21: *"still more important to get the scheduling piece for the timeline sorted out first"* [bill-2026-08-21#L169] — a stall by decision, not a blocker. |
| N11 | bill/yellow-date-channel | 2026-08-15 | Which channel the yellow-date prompt uses — email, in-app, or both |
| P2 | bill/workflow-template-export | 2026-08-06 | Export or screenshots of the Procore workflow templates (the 8-step, per-PM list) — we are replicating them. **Dormant with W1 from 2026-08-15** |
| A2 | bill/co-log-excel-and-sample-email | 2026-07-22 | The change order log Excel + one sample CO email |

---

## Owed

External dependencies, all Bill's unless noted.

**Live — these block or shape current work:**

| Owed | Blocks | Since |
|---|---|---|
| **The weekly package's two missing references** — it cites `Field_Operations_Decisions_Log.md` (*"confirmed decisions for capacity, mirror-card punch workflow, field access, and invoicing"*) and `pasted_content_4.txt` (*"Bill's current Timeline, Trello sync, shipping, and iPad notes for Daniel"*) [thisweek-2026-09-14#References]. **Neither has been received.** The decisions log may already answer Open questions 4, 5 and 7; Bill's raw notes are the primary source the P0 schedule-integrity items were distilled from | Open questions 4/5/7 — and the confidence of BUG-24…27 | 2026-09-14 |
| **Per-department QC checklist items** *(Bill / Louie)* — the ~4 facts each gate asks for [bill-2026-09-16#L15–L30] | T13's modal content | 2026-09-16 |
| **Why the stage photo gate was switched off on 2026-06-07** *(Daniel's own history)* — built and disabled the same day (`adb0937` → `d63146d`) with no reason recorded | T13's first risk | 2026-09-14 |
| ~~**Department list for the Issue Register** — no department model exists~~ **answered 2026-09-15 by Daniel: Drafting / Paint / Fab / Ship/Install, label only for now** — confirm with Bill before routing is built | T11's routing | 2026-09-14 |
| **Field-ops spec reconciliation** — two threads remain: ① the cover email promises items the doc doesn't contain (mandatory hardware sign-off, safety plan in the work package, shipping photos, "concurrent vouch approval," system-generated MHMW invoice PDF — partly confirmed by Bill's subs-invoice-inside-the-Brain intent [bill-2026-08-21#L57], "Quick Work Authorizations" by name — §11.1's lightweight authorization is the closest match); ② is phase **"A.1"** (sub financial workflow where E should be) a typo or a deliberate elevation behind Phase A? ~~③ Phase-A-first vs T1-first~~ **resolved 2026-08-21: T1 first** [bill-2026-08-21#L169] | T5/T8 shape — not T1's start | 2026-08-20 |
| **Katie's invoicing-tab feedback** *(from Katie, not Bill)* — she's *"trying to brainstorm what to do with the invoicing tab"* [bill-2026-08-21#§13] | N2b/N12 shape when they start | 2026-08-21 |
| **Daniel's own notes on the 8/21 items** — to follow, layer onto the digest | Nothing — additive | 2026-08-21 |
| **T&M change notes** — *"if I can get you something today"*; originals lost [#L155] | A1's shape (not its start — that's BUG-10) | 2026-08-15 |
| **Katie's staging feedback** *(from Katie, not Bill)* | An input to AUD1, not a gate | 2026-08-15 |
| **Distribution channel for the yellow-date prompt** — email, in-app, or both | N11 | 2026-08-15 |
| **Confirm the updated uniqueness ruleset** — including *why* `340-26` is not needed, and auto-advance vs. block-and-suggest. **Live as of 2026-09-05: AUD2 is `queue.now`, so this now gates work in flight rather than work on the shelf** | AUD2's change step (not its measurement — that is done) | 2026-08-15 |
| **Is the tagged hours number useful before N10 backfills?** Only ~12 releases carry a billing tag today, so any window reaching before mid-August answers almost entirely `untagged`. Either Bill accepts the bucket or N10 goes first | N16's ship decision, not its build | 2026-09-05 |
| **Confirm the corrected date/stage ruleset**, then take the written version | AUD1's change step | 2026-08-15 |
| Stage weight approval · Carmen avatar | E2 · C9 cosmetics | 2026-07-22 |
| Change order log Excel + sample CO email | A2 | 2026-07-22 |
| **Sample release Excel (billing sheet)** | N2 | 2026-08-06 |
| **Carmen "best project engineer" chat doc** | Workstream 4 framing | 2026-08-06 |

**Dormant — attached to deferred W1 items; do not chase until that lane reopens:**
Procore workflow template export (P2) · 500-998 FC trigger (P5) · Mission Brief
scope confirmation (P0) · in-flight Procore projects at the lapse (P10) · Procore
bulk-export request and the customer-Procore question to his rep (P10, B1/B4).

**Dissolved 2026-08-15: the October cut-list decision.** It was the top row from
2026-08-06 — which of P3/P5/P6/P8 gets lost against an eleven-week window. The
window is gone, so the question is void. Nothing was decided; it stopped being a
question.

**Delivered 2026-08-29:** the **To-Do page reference** — the HPB EOS standalone To-Dos page (44 files). It unblocked BUG-17 and was fully scoped the same day; **BUG-17 was then parked by Daniel before any build.** Reference tree and the scope doc both live at `~/Desktop/Reference/eos-todos-reference/`, outside the repo.

**Delivered since 2026-08-06:** the EOS metrics list — walked 2026-08-09, N8
built against it. **The Trello phase-1 spec doc** — the top Owed row since
2026-08-15, delivered 2026-08-20 as the Manus-prepared field-ops build package
carrying the sub visibility scope [#L93] as promised; digested into T3, T5–T8,
Open question 4, and the reconciliation row above.

---

## Open questions

Nine were asked 2026-08-06; eight are resolved (see Resolved log). #5–#7 were
opened 2026-09-14 by the weekly request package; #8 by the 2026-09-16 session. These remain — #2 is half-answered and no longer gates anything. **Numbers are stable
identifiers:** #3 (shared-tablet attribution) was resolved 2026-08-29 and the gap
is deliberate — the Resolved log and several trails cite these by number, so they
are never reused or shifted up.

1. **In-flight Procore projects at the ~~October~~ line** — **DORMANT
   2026-08-15**, deferred with W1. It stops being urgent and starts being a
   normal design question, to be answered when the lane reopens against the Oct
   2027 date. *(source §10.1)*. Gates **P10** (and the cut-over posture
   generally). The gate
   is *new projects originate in the Brain* — but the subscription lapses with
   projects mid-flight. Pulled over then, a read-only subscription tail, or
   forced across early? Likely cheaper than it sounds: `Submittals` already
   holds their rows from months of webhook sync, so this is probably "the
   Brain becomes the UI for records it already has" rather than a migration —
   but it needs deciding, not assuming. **Answers: Bill** (possibly a
   contract-renewal question, not a build one).
2. **What MHMW Cost means, and the tag semantics** — **half-answered
   2026-08-29 (Daniel), and de-escalated.** It means *a release MHMW eats the
   cost on*. **For now it is a flag and nothing more: no invoicing exclusion,
   no internal-cost rollup, no downstream behavior at all.** That closes the
   urgent half — rows tagged today are descriptive, so nothing is accruing
   against a meaning that will later change under it, and the "every day is
   rows to re-read" pressure is off.
   What stays open is the *reason* split — rework vs. warranty vs. no-charge —
   which only has to be settled when the tag first drives something (invoicing
   exclusion or a cost rollup). Take it then, and expect it to want a reason
   field beside the flag rather than more tag values. **Answers: the client
   (Bill / office), when behavior attaches.** *(source §10.2)* No longer gates N1.
4. **Punch items vs. completion, and the invoice holdback** *(source
   fieldops-2026-08-20 §7.2 / §11.2 — opened 2026-08-20)*. Gates **T8's**
   validation rules and T5/T6's completion semantics. The spec's §17 declares
   every open decision resolved, but two of its own passages still point at the
   deleted open-decisions section: whether open punch items **block** a final
   installation-complete mark or allow a documented partial-completion approval
   [§7.2], and how the **punch-work holdback** on a sub invoice is computed and
   released when installation isn't 100% [§11.2]. Both are policy, not build
   calls. **Answers: Bill.** Rides the field-ops reconciliation conversation
   (Owed). **Sharpened 2026-09-14:** the weekly package's punch mirror card says
   the primary install *"can be marked Installed / Invoice-Eligible when
   accepted"* while punch stays open [thisweek-2026-09-14#§6.1] — that reads as
   **punch does not block the primary's completion**, which answers the first half
   for T9 (c). Confirm it rather than infer it; the holdback half is untouched.
5. ~~**Default installer count: 2 or 3?**~~ **REVERSED 2026-09-16 — 2** [bill-2026-09-16#L967–L981]: *"as much as I regret to say this, three is the wrong number. It should be two"* — under-promise and finish early. No backfill (Daniel). PR #381. Prior answer kept for the trail: **ANSWERED 2026-09-15 — 3.** Bill: the client
   document specifies 3 installers and 24 hours of work with those 3, so `DEFAULT_NUM_GUYS`
   is 3 and `HOURS_PER_INSTALLER_DAY` stays 8 (3 x 8 = 24). Shipped the same day; the
   documents were the rule, not a drafting error. Unblocked **BUG-24**. Original text kept
   for the trail: *(opened 2026-09-14)* Gates **BUG-24**.
   The weekly package [thisweek-2026-09-14#§4.1] and the 8/20 spec [§5] both state
   the baseline as **3 installers = 24 labor-hrs/day per crew**; the code default
   is **2** on both sides (`DEFAULT_NUM_GUYS`, `scheduling.js:25`; `num_guys or 2`
   server-side), and `comp_eta = start + ceil(install_hrs / (num_guys × 8))` has
   been unified on it (`project_asap_install_team_flow`). Moving to 3 shortens every
   unset release's install bar by a third, the day it deploys, on the Timeline, the
   install schedule and the mirror cards. Either the documents are the new rule and
   the change is announced, or 2 was the deliberate shop number and the documents
   are wrong. **Answers: Bill.**
6. **Can a Trello card move bypass the photo gate?** *(opened 2026-09-14)* Gates
   **T13**'s Ship Complete half. The package says a status change *"must never
   silently bypass the gate"* [§5.4.1], but the inbound Trello list move writes
   `Ship Complete` with no Brain UI to show a modal in. Options: bounce the Trello
   move back; accept it and auto-raise a Photo Exception ("moved in Trello, no
   evidence") that lands in the exceptions queue; or treat the gate as fully closed
   only at T4. Recommended: **auto-raise the exception** — it is honest, visible,
   needs no Trello-side behavior, and uses the queue the package already asks for.
   **Answers: Daniel, then tell Bill.**
7. **Paint Complete queue vs the Unassigned tray** *(opened 2026-09-14)* Gates
   **T12 ①**. The tray's 2026-08-29 intake already includes `Paint Complete`, so an
   unassigned Paint Complete release would sit in both columns; and N5's intercept
   auto-rolls any hard-dated Paint Complete to `Ship Planning`, so only
   formula-dated releases would ever wait in the new queue. Also: does dragging from
   the queue into Shipping Planning set the stage to `Ship Planning` *and* a ship
   date from the drop column? **Answers: Bill** for the intent, Daniel for the
   mechanics. **Half-answered 2026-09-16** [bill-2026-09-16#L1336–L1417]: the column
   is **Ready to Ship = Paint QC + Store**; the drop sets stage `Ship Planning` **and**
   `start_install` = next business day; a hard date typed in the table does the same.
   Still open: the double membership with the Unassigned tray.
8. **Does the QC gate fire on stage-group crossings only, or on Paint QC too?**
   *(opened 2026-09-16)* Gates **T13**. Daniel's rule: gate any change that crosses a
   `stage_group` boundary — that gates Welded QC and Ship Complete. Bill named
   **Welded QC and Paint QC** [bill-2026-09-16#L30]; Paint QC is inside READY_TO_SHIP.
   Options: add Paint QC as an explicit in-group gate, or treat Paint as its own
   department boundary. **Answers: Daniel, confirm with Bill.**

---

## Resolved

Append-only log — never edited, never pruned.

- 2026-08-06 · **BUG-1** · closed — FC/Procore link graying on the job log (gray = missing `viewer_url`). Fixed in the pr#327 wave (+ #331/#332 audit follow-ups): paginated FC submittal fetch; Final PDF Pack detail refetch + workflow fallback after FC updates; retry worker treats `''` as missing, 30d lookback, `active_releases_filter`. Number-vs-name click difference is intentional. Patch-don't-rebuild — subsystem retires with the Procore teardown. src bill-2026-08-06#L1334
- 2026-08-06 · **BUG-2** · closed — ball-in-court uncheck 1 → 0 did nothing; ORDER # `0` / uncheck now clears to NULL (was rejected FE+BE). Bill self-noted it live. Fixed in the pr#327 wave. src bill-2026-08-06#L1064
- 2026-08-06 · **BUG-3** · closed — release-number duplicate: uniqueness is (job #, release #, project name); same project (incl. archived) cannot re-issue; job-# wrap allows 410-108 Alta after 410-108 Columbine. Migration `releases_unique_job_release_name.py` → MIG backlog. src bill-2026-08-06#L1051
- 2026-08-06 · **BUG-5** · closed — stage-change hours reaching the fab side: verified the pipeline works (remaining fab is computed, not stored); gap fixed — sparse FAB_MODIFIER/SQL ignored mid-fab stages (Weld Complete etc. stayed 100%); FE+BE+hours_summary aligned to `STAGE_HOUR_PERCENTAGES` per the Banana Code matrix. SchedulingConfig keeps its separate legacy map (scheduling only). src bill-2026-08-06#L1322
- 2026-08-06 · **DP** · closed — drafter edit permissions, `job` → `released` columns: drafters get gear "Edit row" (modal + API, not inline); PATCH via `drafter_or_admin`; delete stays admin. Merged in the pr#327 wave. src —
- 2026-08-06 · **N6** · closed — Ship ↔ Install Break button: Break/Link in the install+ship modal (`StartInstallDateModal`); linked = auto 1 business day, broken = independent dates. Merged in the pr#327 wave. src —
- 2026-08-06 · **BUG-4** · dropped — Monday-morning drag-and-drop drop. src bill-2026-08-06#L1376
- 2026-08-06 · **BUG-6** · dropped — row 164, Nov 2025 outlier in the DWL: data, not code. src bill-2026-08-06#L1057
- 2026-08-06 · **P9** · dissolved — into C3 (collapse ②): the revision stack + obsolete watermark + overlay compare build inside the universal PDF tool, not beside it. src bill-2026-07-22#notes
- 2026-08-06 · **B3** · dissolved — soft-link: the native submittal model makes it a foreign key. src —
- 2026-08-06 · question · coexist or replace → **neither — extend**: `Submittals` is the native record (see P1)
- 2026-08-06 · question · cut-over rule → **new-projects gate**, not per-submittal (see P1/P10)
- 2026-08-06 · question · archival vs operational → **defer; retain generously**, prune as clarity comes (see K3)
- 2026-08-06 · question · GPS source for N9 → tested: **no GPS in a real field photo**; browser geolocation primary, EXIF opportunistic; capture date survives and is preferred over upload date (see N9)
- 2026-08-06 · question · Review Skipped / Rejected / Void → **Review Skipped stays, Rejected dropped, Void kept** — five responses (see P2)
- 2026-08-06 · question · Carmen's ball-in-court queue for aging → **defer the real queue; ship status + timer** (see P8)
- 2026-08-06 · question · revision to a partly-released FC → **the case does not exist**: FC is immutable; post-FC changes are as-builts in the job log markup (see P4)
- 2026-08-06 · question · release tag backfill → **bulk edit on the job log (N10)**, not a migration default (see N1)
- 2026-08-06 · question · `feature/unified-release-modal` → **uncommitted work in the worktree; N7 in flight** — core subsequently merged 8/6 (see N7)
- 2026-08-09 · **N4 · N7 · N8** · built — the v2.0.338 wave (PRs #336–#338) closed one W0 precondition (two-calendar math), N7's remaining two items, and N8's read-only half. Sections retained with status `built`; no W1 item moved. src pr#336–#338
- 2026-08-10 · **I4** · closed — un-parked and shipped (PR #339) without I3/N2b clearing; installer invoice progress % + invoice numbers on the admin Subs page. src pr#339
- 2026-08-10 · **MIG** · note — three migrations confirmed run (`releases_unique_job_release_name.py`, `add_release_tag.py`, `add_installer_invoice_progress_and_numbers.py`); named backlog clear, A1-era five still unverified. src —
- 2026-08-10 · **doc** · moved — this file moved from repo root `ROADMAP.md` to the canonical `docs/ROADMAP.md`; the 2026-08-06 prose roadmap renamed `docs/roadmap.md` → `docs/roadmap-2026-08-06.md` to free the name. CLAUDE.md updated to name this file as the source of truth. src —
- 2026-08-15 · **horizon** · replaced — Procore renewed; `2026-10-31 lapse` → **October 2027 absolute dead date**. The forcing function this file was built around no longer exists. src bill-2026-08-15#L31
- 2026-08-15 · **W1** · deferred — the entire Procore ecosystem off the active path as one block (P0/P1/P2/P4/P7/P10/P11 + C3-narrow + D1-minimal), re-check at W5-substantially-complete or Q1 2027. **P11 exempted from "wait and see"** — its deferral is irreversible at the cliff. Daniel's call; Bill confirmed only the renewal, not the sequencing. src bill-2026-08-15#L31
- 2026-08-15 · **October cut-list** · dissolved — the top Owed row since 2026-08-06; void with the window it cut against. src —
- 2026-08-15 · **W5** · opened — Trello exit becomes the front lane: T1 timeline assignment (priority 1), T2 admin member management (in tandem), T3 sub visibility, T4 teardown, A1 T&M. End state is **Trello dead, not read-only**; decommission expedited. src bill-2026-08-15#L69
- 2026-08-15 · **D4** · dissolved — into T1; the parked timeline view is the front-lane item now. src —
- 2026-08-15 · **classes** · added — every item carries fix / audit / build / lane / deferred alongside its effort letter, plus a Fix queue at the top of the file carrying entry points, so small work can be picked up cold (mobile included). src —
- 2026-08-15 · question · is ball-in-court benched or just un-deadlined? → **benched with the rest of W1**. Raised because Daniel said "benching" in session [#L63] and Bill answered only the Trello half — resolved by Daniel's deferral decision, not by Bill. src bill-2026-08-15#L63
- 2026-08-15 · question · Trello read-only or dead? → **dead**, expedited. src bill-2026-08-15#L69
- 2026-08-15 · question · sub visibility scope → **short term** T&M + that job release's data; **mid term** it dissolves into T2's role model. Bill's "fab hours is the only exclusion" is his eventual posture, not the short-term scope. src bill-2026-08-15#L93
- 2026-08-15 · question · project number + year (`340-26`) → **rejected**: the record already carries dates that make the same comparison; replaced by uniqueness research inside AUD2. Reason is owed back to Bill, who proposed it. src bill-2026-08-15#L185
- 2026-08-15 · **N1/N2/N2b/N10/A2/J1/I4** · re-tiered — W2 confirmed as an **ongoing cost lane behind W5**, not the release valve it was when W1 owned a deadline. The I4 subs tab caught ~$15k of early-or-double sub payment within five days of shipping [#L33] — the first hard ROI number in the record, logged as signal, explicitly **not** a re-tiering trigger. src bill-2026-08-15#L33
- 2026-08-15 · **Calibri** · standard — Calibri is the MHMW font standard; belongs in the design docs, not here. Bill's "for other customers too / your future builds" [#L105] is his suggestion, not adopted as a cross-project default. src bill-2026-08-15#L105
- 2026-08-15 · **Carmen invites** · approved — invite mail sends as Carmen [#L89], now covering staff onboarding as well as subs. Wider flag from Daniel: Carmen is the primary email inlet **and** outlet for external data. Thread to reconcile later: `bb@mhmw.com` owns the ingestion inlet today, and the invite design explicitly rejected sending *as* bb@ because replies hit those pollers. src bill-2026-08-15#L89
- 2026-08-15 · **Procore AR / 3D views · Brain 2.0 side hustle** · dropped — raised in session [#L231, #L241], judged not relevant to MHMW work. No item, no trail. src —
- 2026-08-20 · **field-ops spec** · delivered — the Owed Trello phase-1 spec arrived (Manus-prepared, `MHMW_Brain_Trello_Replacement_Subcontractor_Field_Operations_Build_Package.md`). T1–T4/A1 confirmed as scoped; **T5–T8 opened** (field foundation · punch/issues/Safety Hold · compliance profiles · sub authorization + invoicing); T3's walls written; AUD1 gains the date-color rule in writing (projected = no color, yellow = overdue hard date); **A3 dissolves into T6**. Opened Open question 4 (punch-vs-complete + invoice holdback — the spec's "§17 all resolved" claim is wrong for these two) and the reconciliation Owed row (cover-email items absent from the doc; the "A.1" phase label; Phase-A-first vs T1-first). Queue unchanged — T1 stays `now` pending that conversation. src fieldops-2026-08-20
- 2026-08-20 · question · does the spec change W5's order? → **not yet** — its Phase-A-first sequencing and "A.1" elevation are treated as inputs to a Bill conversation, not decisions; T1 spoken priority [bill-2026-08-15#L75] stands until then. src —
- 2026-08-21 · question · Phase-A-first or T1-first? → **T1 first, from Bill directly** — the timeline scheduling piece before everything, T&M (A1) deliberately stalled behind it. Closes thread ③ of the reconciliation row; threads ①/② remain. src bill-2026-08-21#L169
- 2026-08-21 · **standup digest** — pre-Alaska session folded in: **T9 opened** (release splicing — punch/remaining work spawns a fractional field work ticket with residual invoiceable value), **T10 opened** (interim job-log-photos→Trello bridge, Doug's ask, dies with T4), **N13 opened** (Carmen prompt library exposed in-app), **N14 opened** (FC pack on the job log modal); **N9 elevated** to `queue.next` with its spec pinned (stamp text: job/release/stage-at-photo-time/who; Katie-to-customer purpose); **punch/field issues anchor to the release** (T6); **subs invoice inside the Brain** hardened (T8); **N5's color-dump rule reversed** → BUG-11 (dump at Start Install, yellow never silently dropped), plus BUG-12 (Carmen lookahead window), BUG-13 (backspace), BUG-14 (iPad rotation state). Mobile target: iPad first. src bill-2026-08-21
- 2026-08-21 · question · punch and field issues — project or release? → **release**, always; punch on a finished release spawns a spliced work ticket (T9). src bill-2026-08-21#L45
- 2026-08-29 · **BUG-12** · closed — Carmen lookahead stale window. Root cause was the rendered Gantt axis, not the data: `_chart_range` expanded the x-axis backwards to cover any past-dated phase bar, so one stale bar rewound the chart to May. Fixed in PR #348 — the axis now starts at the declared window and only extends forward. The other two halves of Bill's ask were already true and predate the bug (3-week-from-today window, `schedule_builder.py:427`; Drafting/Fabrication/Paint/Shipping/Installation labels, 2026-07-25). src pr#348
- 2026-08-29 · **T1 base** · note — `feature/jay-view` (PR #286) and `feature/mirror-cards` (PRs #300/#301) verified **already merged to `main`** in July. The "base is confirmed" line read as two branches awaiting reconciliation; that work does not exist. T1 starts from a clean worktree off `main`. src —
- 2026-08-29 · **T1** · decision — drag rebuilds on `@dnd-kit`, not restored from the 2026-07-12 removal commit: what was removed was native HTML5 drag, already dead on iPad, and iPad is now the stated target. The unassigned lane is net-new — no lane today holds a release with neither a shipping stage nor an installer. src —
- 2026-08-29 · **N9** · note — capture standard partly superseded by PR #349's client-side JPEG re-encode: EXIF is stripped before upload for every photo over 600 KB, so browser geolocation is the sole location source and capture date must come from `file.lastModified` or a pre-compression read. Folded into N9. src pr#349
- 2026-08-29 · **queue** · note — eight days after the 8/21 standup, nothing on the queue has started. PRs #344, #345, #348, #349 and #347 landed in that window; all are fixes or housekeeping. `queue.now` stays **T1**. src —
- 2026-08-29 · question · shared-tablet photo attribution (Open question 3) → **individual Brain logins on the shared tablets**, not a capture-time picker, not a device name, not blank-on-tablet. Correctness over friction: the stamped photos are invoicing evidence Katie sends to customers, so a generic name on every shop photo defeats the feature. The stamp reads the logged-in user with no new capture UI. Carries an account-rollout prerequisite onto T2 — ship the accounts alongside the stamp, or every tablet photo prints one name. Re-check with Bill once the crews feel the login friction; the picker is the fallback. Unblocks **N9**. src —
- 2026-08-29 · question · MHMW Cost semantics (Open question 2) → **half-answered: a release MHMW eats the cost on, and for now a flag with no behavior** — no invoicing exclusion, no cost rollup. De-escalated: rows tagged today are descriptive, so the "every day is rows to re-read later" pressure is gone and it no longer gates N1. The reason split (rework / warranty / no-charge) waits until invoicing actually reads the tag. src —
- 2026-08-29 · **T1** · decision — unassigned-lane membership = **no installer assigned AND (ready to ship OR stored at Mile High OR past paint complete)**, Bill's stated intake verbatim. "Any release with no installer" rejected: it drags in every drafting and fab row and the column stops being a work surface. src —
- 2026-08-29 · **BUG-11** · decision — the color dump triggers on the **`Install Start` stage flip**, not the `start_install` date arriving. A date-driven dump fires on schedule straight through a slip, hiding exactly the yellow-overdue signal Bill said must never silently disappear [bill-2026-08-21#L113]. Accepted cost: a crew that never moves the stage keeps the color past the real start; the stage-change photo gate (N9) is the eventual nudge. src —
- 2026-08-29 · **archive rules** · confirmed shipped — Daniel asked whether the send-to-archive adjustment landed. It did, 2026-08-20 in PR #344. `_archivable_query()` now requires **stage='Complete' AND job_comp='X' AND invoiced='X'**; the stage predicate is the fix, because setting Install Prog to 'X' cascades the stage to 'Install Complete', so job_comp + invoiced alone swept every installed-but-not-closed-out release into the archive. Verified end to end: `archive_preview` and `archive_confirm` share the one query, `routes.py:3915` is the only path that writes `is_archived = True`, the modal's empty-state copy was updated to match, and `tests/test_archive_eligibility.py` covers it. Nothing outstanding. src pr#344
- 2026-08-29 · **BUG-11** · follow-on — Daniel added two rules and answered the ASAP edge case: **ASAP cannot be set at `Install Start` or later** (409 `asap_after_install_start`; clearing still allowed), and **an ASAP row's placeholder date is rewritten to the stage event's date** when it enters the dump zone, since that anchor was never a plan. Hand-set hard dates are untouched. Implementation note for whoever reads this next: the ASAP test has to be made by the *caller*, because `UpdateStageCommand` clears the flag before the cascade runs. **Also found: the fix was invisible in the UI** — three render paths hardcoded the old ship-stage wash, so the DB was right and the screen was unchanged. Now one shared `utils/installDateColor.js`. **Left open:** `comp_eta` still derives from the replaced ASAP anchor after a date rewrite. 1321 backend + 189 frontend tests green. src —
- 2026-08-29 · **BUG-11** · **built** — dump now fires on a transition into `COLOR_DUMP_STAGES` {`Install Start`, `Install Complete`, `Complete`}, never on the `start_install` date. The triage's reduction (add `install_start`, remove the two ship reasons) **missed a third site**: `start_install/command.py:114` independently keyed a hand-typed hard date's color off `SHIPPING_STAGES`. All three sites now share one constant, with an integrity test pinning it to the tail of the canonical stage order so "or later" can't rot. Daniel's confirmation (*"hard date setting unaffected ... Date not changed, just color"*) turned up **two further sites** beyond the three: the ASAP toggle and the Trello mirror-card date slide both stamped a hard date with `no_color = False` hardcoded, so flagging ASAP or sliding the mirror bar on an installed release repainted it. Five sites now share the one constant; the `set_asap` undo is exempt on purpose (it restores the prior value from its payload). The hard-date branch left in `shipping_stage_date_discipline.py` is an intentional no-op guard — deleting it would drop hard dates into the formula blanking path and erase them. Noted side effect: ASAP red survives Ship Planning now, since the wash had been clearing it as a side effect; `asap_dropped_on_ship_complete` still handles Ship Complete. 1312 backend tests green. src daniel-2026-08-29
- 2026-08-29 · **UI** · reload banner lost the z-fight — the version-update banner and the notification/Carmen pod were both `z-50`, so DOM order decided and the pod (mounted later, in `<main>`) covered the Reload button in rail mode. Banner moved to `z-[65]`: above the pod (50) and Carmen's drop panel (61), still below modal scrims (70) and portaled dropdowns (1000), which should cover a passive banner. src daniel-2026-08-29
- 2026-08-29 · **BUG-16 + BUG-18** · **both built** (branch `claude/bug-16-18-fixes-eqqca9`). BUG-16 landed as one shared helper rather than a per-caller clause, and clears any drafter-scoped status (HOLD/STARTED/NEED VIF) — the ask named the field, and all three are scoped to whoever held the ball. Triage said two call sites; there are **three** (`POST /procore/health-scan/update` in `app/procore/__init__.py` is a second copy of the audit fix loop). `scripts/reconcile_bic.py` left alone on purpose — one-off outage backfill, documented as event-free. Also fixed a shadowed `submittal_id` in the order-compression loop that misattributed events and logs to the wrong submittal after any compression. BUG-18 took the localStorage-hydration candidate; cache is a paint hint only, cleared on logout and on session expiry. 1291 backend tests green; frontend builds clean. src daniel-2026-08-29
- 2026-08-29 · **fix queue** · re-stocked — BUG-16 (DWL HOLD must drop on a BIC change — high, client-asked), BUG-17 (To-Do page cleanup — blocked on Daniel's stub), BUG-18 (icon rail pops in role-gated rows on load — diagnosed, low). Triaged with entry points so BUG-16 and BUG-18 can be handed to an agent cold; BUG-14 explicitly held back as device-dependent. src daniel-2026-08-29
- 2026-08-29 · **BUG-17** · unblocked — the To-Do page reference arrived the same day it was asked for (HPB EOS standalone To-Dos page, 44 files). Scoped in `docs/design/todos-page/README.md`. The triage headline is that **we have no to-do table**: ours are `ChecklistItem` rows the meeting extractor creates, with no create / delete / archive / field-edit path and role-based rather than per-row scoping, so the reference's whole write model has no counterpart — "port the page" is not a coherent instruction and the doc says so. Split into take-now / needs-a-backend-touch / decide-first; Tier 1 is decision-free and is the first slice. The bundle itself is **parked outside git** at `~/Desktop/Reference/eos-todos-reference/` — this repo is public and that is another app's source, so it follows the transcripts convention: only the synthesized doc is committed. Flagged the rocks/milestones column as dormant-but-relevant if D8 (EOS Module) ever lands. src eos-todos-2026-08-29
- 2026-08-29 · **BUG-17** · parked — Daniel pulled it out of the bug pass hours after scoping it: *"drop the reference for the to-dos page and the to-dos from the bug pass, I'll circle back on that."* Class `deferred`, re-check trigger = Daniel raises it. The scope survives intact at `~/Desktop/Reference/eos-todos-reference/SCOPE-for-MHMW.md`, moved out of `docs/design/todos-page/` so the analysis sits with its source material instead of in a public repo — the same reason the reference tree was never committed. Nothing to re-derive when it comes back. src —
- 2026-08-30 · **T2** · first pass — admin-only read-only user directory (`/admin/users`, `GET /brain/directory`): First/Last/email/role, split Employees vs Subcontractors. No invite/permissions/reset/block. Status `in_progress`; the rest of T2 and all of T3 are still open. src —
- 2026-08-30 · **T2** · stage — of Bill's six actions [#L83], **see all users is done**. Add people, assign permissions, send invite, reset password, and block are not started. Directory columns share one `table-fixed` grid; Users sits under Matching on the left rail. Queue unchanged (`now` T1). src —
- 2026-09-02 · **T2** · permissions management — employee role is now assignable from the Users page (Admin / Drafter / Default, mutually exclusive, admin-only `PATCH /brain/directory/employees/<id>/role`). Self-demotion and last-admin demotion are both refused. Subcontractors unaffected. Two of Bill's six [#L83] now done; add people, invite, reset password, and block remain. The multi-role model the 2026-08-20 spec calls for is still open. src —
- 2026-08-30 · **BUG-14** · first pass, no iPad test — rotation dump **tracked down**: cards↔table remount when rotate crosses 1024/1280, not a Safari reload (sessionStorage covers that too). Modal state lifted off the unmounted tree; scroll restored on orientationchange; no rotation lock. Still open until a physical iPad confirm: open a release hub, scroll the list, rotate, still there. src bill-2026-08-21#L145
- 2026-09-03 · **BUG-20** · **built** — **ASAP no longer sets a date.** It stamped a hard `start_install` five business days out and derived `comp_eta` from it; the cell then rendered the word "ASAP" in place of the date, in both date columns and in the PDF. Daniel's rule: the flag paints the cell red, the user types the real hard date, colour-drop and Break/Link are untouched. Five behaviours moved with it. (1) `set_asap` is now **flag + colour only** — no date, no `comp_eta`, no Trello due push, no scheduling recalc; the user's own date save already does all four. (2) **Setting a hard date no longer clears ASAP** (`start_install/command.py`) — it used to, because the date was ASAP's to own, so under the new rule the required date save would have cancelled the flag one keystroke after it was set. (3) The **ASAP date rewrite on entering the dump zone is gone** (`neutralize_install_date_cascade`, and the `install_started_on` plumbing through `stage/command.py`): it existed only because the +1wk anchor was a placeholder, and rewriting a hand-set date would now destroy a real commitment. (4) **Undo of `set_asap` is flag-only**, with the legacy branch kept and tested — events recorded before this change carry `prev_start_install` and must still roll back the placeholder they stamped. (5) The modal **refuses to set ASAP without a date** and leaves the date field live; Save is disabled until a date is entered. Daniel also decided the consequence: an ASAP row's date is a hand-set hard date, so **ASAP counts as a hard date everywhere** — it re-enters both EOS metric denominators (`eos_metrics.py`, client-visible math, was excluded), anchors material-order lead time, and sorts ahead of plain hard in the install schedule. 1324 backend + 205 frontend tests green (the 4 `tests/tm/` failures are the pre-existing local `APP_BASE_URL` guard, untouched). src daniel-2026-09-03
- 2026-09-03 · **BUG-22** · found by audit, Trello half built — a read-only prod audit of the ASAP population (5 live rows, **all 5 already hard dates**, which confirmed BUG-20 needs no migration) turned up two rows at `Ship Complete` still flagged red, both last written via Trello. `asap_dropped_on_ship_complete` lived inside `UpdateStageCommand`; the inbound Trello list move writes the stage itself and never calls that command, so the drop never ran — on the path the shop actually uses. Rule extracted to `features/start_install/asap_drop.py` and called by both writers, the BUG-9/BUG-16 shared-rule shape. The colour dump is deliberately NOT wired into the inbound path — inbound lands on the floor of a list's zone, so no drag can reach `Install Start` or later; an integrity test pins that disjointness so a mapping change can't silently reopen it. **All three writers now call the same rules** — the Install-Prog percentage branch was closed 2026-09-04 with both cascades (and the `X` branch picked up the flag-only drop, which its hard-date-only cascade had been missing on formula-dated rows). Standing lesson, three for three: a cascade written inside one command is a cascade the other writers skip. The inventory of stage writers is now `UpdateStageCommand`, the inbound Trello list move, and the two Install Prog branches — anything new joining that list has the same obligation. src daniel-2026-09-03
- 2026-09-04 · **BUG-23** · opened by audit — a four-angle quality audit of the BUG-20/22 diff (reuse · simplification · efficiency · altitude) found the extraction is the right shape but **applied one call short**: the inbound Trello path still skips N5's shipping-stage date discipline, `update_invoiced` still skips the ASAP drop, and the flag now has four clearers rather than one. Cleanups from the same audit were applied to the diff directly (duplicated cascade blocks merged, an always-true guard and a derivable reason removed, a vestigial accumulator collapsed, a duplicated webhook test harness consolidated, and `is_hard` in the install schedule brought in line with the "ASAP counts as a hard date" decision, which the first pass had left disagreeing with its own header). The audit also caught a real defect the same pass introduced — an undo branch whose body had drifted out from under its guard. src daniel-2026-09-04
- 2026-09-04 · **BUG-21** · **built** — **timeline zoom keeps your place.** The re-anchor read `scrollLeft` in a `useLayoutEffect`, i.e. *after* React had committed the new column width; zooming out narrows the chart, so the browser had already clamped `scrollLeft` to the new smaller maximum and the px→date math ran on a corrupted value — dumping the view at an arbitrary column ("snaps to July 3rd"). No amount of care in that effect can fix it: the number it needs is gone by the time it runs. The left-edge **date is now captured in the zoom handler**, while the old column width is still the one on screen, and the effect restores it (`zoomAnchorRef`). Width changes that are *not* zooms — viewport resize, tray toggle — carry no anchor and keep the old px math, which is sound for them because their `scrollLeft` was never clamped. Scoped to zoom as decided: `viewStart`/`zoomIdx` still do not persist across navigation. The **Monday worry was a false alarm** — `mondayOf` is correct and `chartRange.firstDay` is a Monday; the Friday on screen was simply where the corrupted scroll had landed. Regression test models the browser clamp in jsdom (which has no layout) by clamping `scrollLeft` against the live content width, and was checked to **fail on the old implementation** — 291 frontend tests green. src daniel-2026-09-04
- 2026-09-04 · **BUG-13, BUG-14** · **dropped** — Daniel: drop both *"unless we hear otherwise"*. Neither is a build problem. BUG-13 has two sightings and no repro since 8/21, and instrumenting a phantom keystroke bug nobody can trigger is not worth a queue slot; BUG-14's code is on `main` and what is left is a **verification** pass that cannot happen without the physical iPad. Both are `deferred` with a stated re-check trigger rather than deleted — a fresh sighting re-opens BUG-13, and BUG-14 rides along the next time the iPad is on the desk, which is the same device gate T1's drag is already waiting on. src daniel-2026-09-04
- 2026-09-04 · **BUG-23** · **re-checked, still open** — read as possibly closed by the day's ASAP work; it is not, and by construction cannot be: BUG-23 was filed *by* the audit **of** that work, as the list of what it left undone. All four findings verified against `main` @ 7d42436: (1) `apply_shipping_stage_date_discipline` is still called from `features/stage/command.py` **only** — `app/trello/sync.py` does not call it, so an inbound list move to Shipping planning still keeps stale formula dates; (2) `update_invoiced` (`routes.py:1708`) still calls `neutralize_install_date_cascade` and **not** `drop_asap_on_completion`; (3) `start_install_asap = False` is still written in **three** modules (`asap_drop.py:47`, `neutralize_install_date_cascade.py:115`, `shipping_stage_date_discipline.py:96`); (4) `classify_install_date` still returns `KIND_ASAP` off the flag alone **before** the `formula_tf is False` test (`lookahead/pipeline.py:76`) and `_install_source` still maps it to `SOURCE_HARD` (`schedule_builder.py:220`) — this is the half that was deliberately pulled out of PR #364 in `e10feee`, so it was never going to close with it. Live impact is still zero rows (BUG-20 means every ASAP row carries a hand-set date), which is why it stays **med** and keeps its own branch. src daniel-2026-09-04

- 2026-09-14 · **weekly request package** · ingested — Bill's *"The Brain — This Week: Timeline and Field Workflow Updates"* (Manus-prepared, 19 pp., P0–P3 with acceptance tests) folded in and **given the front of the queue** (Daniel: *"probably these elevate to highest urgency"*). **Filed:** BUG-24 installer count, BUG-25 Trello Due-only, BUG-26 weekends, BUG-27 ASAP red on ship lanes (P0 schedule integrity, `queue.now`); **T11** Release Issue & Error Register (P0, `queue.now`); **T12** Paint Complete queue + Drop Ship Only + load order and **T13** two-stage Photo Evidence Gate + partial shipments (P1); **T9** elevated with its deps cut (P2); **T14** iPad/PC parity (P3). **Moved:** AUD2 `now` → `next`; J1 dissolves into T13; field issues leave T6 for T11; N9's deferred stage gate delivered by T13. **Measured against `main` @ 1c3d09a before filing, and four findings changed the shape of the asks:** the Brain has **no `num_guys` write path** (only Trello description parsing) so "restore" is net-new; the Trello date inversion is on the **mirror-card range push** (`update_card_date_range` writes Start = install), primary cards are already Due-only; ASAP red is **tray-only** by design; and a **stage photo gate on Welded QC + Paint Complete already exists, disabled** since 2026-06-07. Opened Open questions 5 (default crew 2 vs 3), 6 (Trello move vs photo gate), 7 (Paint Complete queue vs Unassigned tray). Owed: the package's two cited references were not delivered. src thisweek-2026-09-14

- 2026-09-15 · **BUG-24, BUG-25, BUG-26, BUG-27** · **built, no tests yet** — the P0 schedule-integrity four, code only; test writing and local-dev verification are a deliberate follow-up, not an omission. Existing suite 1480 green, frontend builds. **BUG-27** (smallest): `ShipCard` now reads the release's ASAP state on every render and overrides the lane colour with the tray's red (`ASAP_BORDER_COLOR`, one constant shared with `TRAY_BORDER.asap`), so the rush survives the pull out of the tray and clears itself when `asap_drop` fires at Ship Complete. Installer lanes deliberately untouched — there the lane colour answers whose work it is. **BUG-26**, all four asks: weekend columns darkened (`bg-gray-400/45`) **and** painted into the lane bodies, which had no weekend shading at all — the only cue was a faint header tint, which is how installs kept getting planned across Sat/Sun unnoticed; a new `next_business_day()` snaps `calculate_install_start_date`'s output onto the FIELD calendar so no AUTO-projection places a start on a weekend; a deliberate drop still writes the day it was dropped on (`timelineDrop` was already correct); and T1's open *"install hours don't compute on a weekend drop"* defect [bill-2026-09-02#L471] closed — the drop's optimistic patch wrote `Start install` but left `comp_eta_effective` stale, so the bar kept its old length until the next poll, which reads worst across a weekend. It now recomputes client-side with the same math the server will, and the bar bridges the weekend as one bar because it always did once the end was right. **One over-reach caught by the suite and reverted:** the same weekend snap was first applied to `calculate_projected_fab_complete_date` too, which broke `test_fab_projection_uses_shop_calendar` — fab completing "today" is a statement about the work and today can legitimately be a Friday the shop is shut. The ask is about *starts*; the snap now only covers starts. **BUG-25**: the mirror push is Due-only behind `MIRROR_DUE_ONLY` in `app/trello/api.py` — due = the install day, `start` explicitly cleared with a JSON null (leaving it out would strand the stale Start, the exact field Bill is misreading). **The literal rule could not ship alone and this is the part to look at**: outbound due=start_install fires a due webhook, and `_handle_mirror_writeback` reads a mirror due as `comp_eta`, so every Brain push would have come straight back in as "comp_eta = start_install" and flattened the bar. §4.2's *"leave inbound alone"* is therefore violated by exactly one guard — a mirror carrying **no** `start` has its due read as `start_install`, legacy range cards unchanged. That guard is the price of the rule; if Bill exempts the mirror, flip the constant and delete the guard. `mountain_due_datetime`'s 6pm/6am contradiction resolved in favour of the **code** (6 AM, same calendar day everywhere in the US); moving it to 18:00 would rewrite the due time on every card ever pushed for no stated need, so the docstring was what changed. *"No silent mismatch"* got its backend half: `GET /brain/sync-failures` (admin) names the failed outbound pushes — job, release, action, error — rather than only counting them like `/sync-health`; the UI is T11's. **BUG-24** is net-new as filed, and **shipped on two calls that are not mine to make** — both are live and both are one line to change. (1) **`DEFAULT_NUM_GUYS` stays 2.** Open question 5 is unanswered and moving it to 3 shortens every unset release's bar by a third the day it deploys; the new control lets a scheduler set 3 per release today without that blast radius. (2) **A crew edit recomputes `comp_eta`, overwriting a hand-compressed one** — the package's own wording for BUG-24, and the only rule under which the typed number means anything, but it does lose a Timeline edge-compress. That is BUG-11's open 2026-09-02 question answered by fiat to unblock the build; the recompute site carries the note. Shape as specified otherwise: `UpdateNumGuysCommand` (`features/num_guys/`) writes `num_guys`, recomputes `comp_eta`, emits an undoable `update_num_guys` event and pushes the count into **both** card descriptions via the existing `sync_num_guys_on_card`; `PATCH /brain/update-num-guys/<job>/<release>` is `@admin_required` — the Timeline's own scheduler gate, so subs never see it [§4.1]; the hub's read-only "crew of N" footnote is now the control, rendered only for admins. Outbound is synchronous best-effort with ERROR-on-failure, matching `UpdateStartInstallCommand`'s due push rather than the outbox — an outbox action for it is the obvious follow-up. src —

- 2026-09-15 · **Open question 5** · **answered — 3, and shipped** — Bill: the client document specifies **3 installers and 24 hours of work with those 3**, so the documents were the rule and the code was wrong. `SchedulingConfig.DEFAULT_NUM_GUYS` 2 → 3 with `HOURS_PER_INSTALLER_DAY` unchanged at 8 (3 × 8 = 24 labor-hrs/day per crew, matching fieldops-2026-08-20#§5 and thisweek-2026-09-14#§4.1); the legacy `INSTALL_HOURS_PER_DAY` reference value moves 16 → 24 to stay equal to the product it documents. **The blast radius is the stated one and it is live:** every release with no recorded `num_guys` just had its projected install window shorten by a third, on the Timeline, the install schedule and the mirror cards — that is the change, not a side effect, and it wants announcing to the crews rather than discovering. **The number now lives in exactly one place.** It had been hardcoded as a literal `2` in six sites that could silently disagree — `calculate_installation_duration`'s signature default, the inline seed in the card-description builder, `update_num_guys_in_description`'s `default_num_guys`, the `num_guys or 2` in the outbox mirror push, the `CardSpec` dataclass default, and the frontend constant. All five backend sites now read `SchedulingConfig.DEFAULT_NUM_GUYS` (a leaf module importing only `typing`, so no cycles); the frontend keeps its own mirror by necessity, marked as such on both sides. This retires the first of **BUG-24's two shipped-under-protest calls**; the second (a crew edit recomputing over a hand-compressed `comp_eta`, which answers BUG-11's open 2026-09-02 question by fiat) is still open and still wants a ruling. Backend 1480 green, frontend 341 green. **One stale frontend expectation fixed, and it was mine from earlier the same day:** `GanttChart.drag.test.jsx` pinned the drop-rollback object exactly, and BUG-26's optimistic `comp_eta_effective` patch had added a key to it — caught only because the frontend suite had not been run alongside the backend one. src —
- 2026-09-15 · **BUG-24, BUG-25, BUG-27 + Timeline/hub follow-ups** · **BUG-27 complete; BUG-24 and BUG-25 awaiting rulings** — Daniel's pass on `fix/bug-fix-audit-bill-notes`, code only (tests deliberately deferred to the end). **BUG-27 closed on a rule change:** ASAP is **kept through Ship Complete** — `asap_drop.py` now fires at `Install Start` or later (UpdateStageCommand + Install Prog %/X); the inbound Trello drop call was removed (no list can reach `Install Start`), and the N5 formula-date blanking at Ship Planning/Complete no longer clears the flag. Three existing tests still encode the old Ship Complete drop and fail until the test pass. **BUG-25 awaiting date confirmation from Bill, expected 2026-09-16** (mirror Due-only vs exempt range bar). **BUG-24 awaiting the hand-shortened bars ruling** (crew edit recomputing over an edge-compressed `comp_eta`); its crew control moved to its own "Crew (num guys)" row in the hub — it had only rendered inside the install-hours footnote, so a release with no hours had no control. The last literal `2` seed (`trello/sync.py`, missing "Number of Guys" line → parsed back into the row; also `trello_cleanup.py`) now reads `DEFAULT_NUM_GUYS`. **No backfill (Daniel):** 276 active sandbox releases still store `num_guys = 2` from the old default and stay that way; only edits and new cards get 3. **Also fixed:** Timeline drag card drifted ~one column from the drop highlight (overlay anchored to the grab offset; now pinned to the pointer, lane chosen by `pointerWithin`); ticking ASAP in the hub wiped the Start Install date (`JobDetailsBody` dropped the date arg → dateless save cleared it) and the ASAP checkbox now toggles off as well as on; hub edits on Timeline/Archive refetch silently instead of redrawing the page; Install Prog is editable in the hub with the Job Log cell's stage rules. src —

- 2026-09-16 · **9/16 shop session** · ingested — Bill + Louie, 1:33 (bill-2026-09-16), walked against Daniel's notes. **Rulings:** BUG-24 hand-adjusted bars (start fixed, `comp_eta` moves, no recompute, listable + hatched); BUG-25 mirror card exempt from Due-only; **Open question 5 reversed to 2** (PR #381, no backfill). **Re-specified:** T13 QC gate (Welded QC + Paint QC, photo req / note opt / no-photo comment), T12 Ready-to-Ship column + `Paint Complete` → `Paint QC`, T9 splice modal. **Filed:** BUG-28–31, N19 home page (un-parks D2, `queue.next`), N20 Dencol cross-check, Open question 8. **Deferred:** FC-error report, Carmen Review overhaul, project photo directory. src bill-2026-09-16
- 2026-09-18 · **BUG-32** · **filed and built** — Bill, from experimenting with splicing: the hours *"are not updating in all locations"* — the Splices tab nets them, the Job Log and the sub assignments do not. Filed as a display/billing bug on shipped T9, not a splice-rule change: the pool stays whole on the parent (every guard measures against it) and the netting moved into the read paths, behind one `install_hours_view` so the Job Log, the release modal, Subs → Invoice Paid (and its export), the install schedule's crew capacity and the `Install HRS` KPI total cannot drift from each other again. Found and fixed en route: a splice never touches its parent's row, so the Job Log's cursor poll would have kept serving the stale original until someone cleared localStorage. **Left open, and it wants a ruling:** the parent's `comp_eta` is still computed from the gross pool, so a spliced release's projected install window is longer than the hours it still carries. No migration — no schema change. src —

- 2026-09-16 · **merged to `main`** · PRs #381–#383, patch notes v2.0.383 — **#381** default crew back to 2 + BUG-25 mirror keeps start + due; **#382** Invoice Paid export + filters (I4); **#383** T9 splice modal v2 (Splices tab, required scope + installer, additional hours outside the pool). **Migrations owed before the splice UI works:** `add_parent_release_id_to_releases.py` → `add_splice_additional_install_hrs.py`. src pr#381, pr#382, pr#383

---

## Sources

| Slug | Path | Role |
|---|---|---|
| bill-2026-09-16 | `~/Desktop/Transcripts/MHMW/Bill-9-16-2026.txt` | Wednesday shop working session (Bill; Louie for the first half) — QC photo gate, Issues walkthrough, splice modal, hand-adjusted bars, Ready-to-Ship column, crew default reversed to 2, sub view. `#LNNN` anchors are line numbers in the **raw** transcript (continuous prose, mlx_whisper large-v3-turbo; silence-fill loop at L200–L220). Findings: `processed/Bill-9-16-2026.md`, which folds in **Daniel's notes** marked *(notes)* |
| thisweek-2026-09-14 | `~/Downloads/MHMW_Brain_This_Week_Timeline_and_Field_Updates_September_2026.pdf` | Bill's weekly developer request package, *"The Brain — This Week: Timeline and Field Workflow Updates"* (Manus-prepared, September 2026, 19 pp.) — P0 Issue & Error Register + schedule integrity, P1 release flow + Photo Evidence Gate, P2 splicing, P3 iPad parity, each with acceptance criteria. `#§N` anchors are its section numbers. **Lives in Downloads — fragile; move beside the transcripts.** Cites two references not in hand (`Field_Operations_Decisions_Log.md`, `pasted_content_4.txt`) — see Owed |
| bill-2026-09-02 | `~/Desktop/Transcripts/MHMW/Bill-9-2-2026.txt` | Tuesday working session (Bill), post-Alaska — a live **Timeline demo that closed T1's design** plus a full **sub-access permission matrix** (T3). `#LNNN` anchors are line numbers in the **raw** transcript: it is continuous prose and directly citable, so there is no `-clean.md` companion. Findings: `processed/Bill-9-2-2026.md`, which also folds in **Daniel's own page-by-page notes** and a **reconciliation section** recording where those notes supersede the audio (ASAP display, CarMid, drag-writes-dates-only, Ship Complete freeze). Note the first transcription pass hit a Whisper repetition loop that destroyed the back half; it was re-run clean the same day and the broken output is kept as `Bill-9-2-2026.BROKEN.txt` |
| bill-2026-08-21 | `~/Desktop/Transcripts/MHMW/Bill-8-21-2026-clean.md` | Thursday standup (Bill), pre-Alaska — T1-first confirmed, punch→release + splicing, N9 elevated + spec'd, N5 color rule reversed, prompt library, iPad-first. `#LNNN` anchors are line numbers in the **cleaned** transcript (raw `Bill-8-21-2026.txt` is too interleaved to cite). Findings: `processed/Bill-8-21-2026.md`. Daniel's own notes to follow |
| fieldops-2026-08-20 | `~/Downloads/MHMW_Brain_Trello_Replacement_Subcontractor_Field_Operations_Build_Package.md` | The delivered Trello-replacement / subcontractor field-ops functional spec (Manus-prepared, Aug 2026) — the Owed W5 written scope. `#§N` anchors are its section numbers. **Lives in Downloads — fragile; move beside the transcripts if it's to be a durable citation source.** Its own cited sources (`BRAIN_KNOWLEDGE_BASE.md`, `07_TM_Module.md`, …) are the Procore-replacement package, also outside this repo |
| bill-2026-08-15 | `~/Desktop/Transcripts/MHMW/Bill-8-15-2026-clean.md` | Friday standup (Bill) — **the reset**: Procore renewed, Trello promoted. `#LNNN` anchors are line numbers in the **cleaned** transcript, not the raw (`Bill-8-15-2026.txt` is too interleaved to cite). Findings: `processed/Bill-8-15-2026.md` |
| bill-2026-08-06 | `~/Desktop/Transcripts/MHMW/processed/Bill-8-6-2026.md` | Submittal-system working session (Bill, Colton) — primary transcript; `#LNNN` anchors are its line numbers |
| bill-2026-07-22 | `~/Desktop/Transcripts/MHMW/processed/Bill-7-22-2026.md` | Ops/roadmap review — the October deadline surfaces; A2, C3-origin, N8, J1-drop |
| eos-todos-2026-08-29 | `~/Desktop/Reference/eos-todos-reference/` | The HPB EOS app's standalone To-Dos page, delivered by Daniel 2026-08-29 as `eos-todos-reference.zip` (44 files, Next.js/Firestore). **Outside the repo on purpose** — same convention as the transcripts, and this repo is public while that is another app's source. Scoped for our use in `SCOPE-for-MHMW.md` inside that same directory — the doc was committed to `docs/design/todos-page/` on 2026-08-29 and removed again when BUG-17 was parked, so it now sits with its source material rather than in the repo |
| daniel-2026-09-05 | session notes (no transcript) | Daniel's 2026-09-05 roadmap session — set `queue.now` to AUD2 + N16 ("build now"), specified N16 (time-framed hours-released with a billing-tag breakdown, admin-wide), and carried the AUD2 / N1 / `NaN` measurements taken read-only against sandbox the same day |
| daniel-2026-09-03 | session notes (no transcript) | Daniel's ASAP rework, taken live 2026-09-03 — BUG-20, plus the "treat ASAP as a hard date everywhere" call on the downstream classifiers. No line anchors; cited by slug only |
| daniel-2026-08-29 | session notes (no transcript) | Daniel's own bug list, taken live 2026-08-29 — BUG-16/17/18, plus the archive-rules confirmation request. No line anchors; cited by slug only |
| notes-2026-08-04 | daily notes (no transcript) | Daniel's 2026-08-04 notes — N5 origin, N4 symptom |
| pr#NNN | GitHub PRs on the milehigh repo | Build provenance for merged work — #323–#334 (2026-08-06/08), #336–#338 (2026-08-09, v2.0.338), #339 (2026-08-10), #344/#345 (2026-08-20, archive rules · install hours on the subs tab), #348 (2026-08-21, BUG-12 + Carmen chat placement), #349 (2026-08-24, photo upload + client-side compression — see N9), #347 (2026-08-29, credential scrub), #360 (2026-09-03, BUG-19 DWL bounce-back), #361 (2026-09-03, T1 core — timeline drag-to-assign, release hub, Users page), #364 (2026-09-03, BUG-20/BUG-22 ASAP as a colour), #366 (2026-09-04, BUG-21 zoom anchor), #367 (2026-09-04, Job Log photo badge), #369 (2026-09-04, To-Dos two-column + mentions — BUG-17's first half) |
