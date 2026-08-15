---
project: MHMW
updated: 2026-08-15
verified: origin/main @ 4c048ca (PR #340 font wave)
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
  now: T1
  next: [T2, AUD1]             # BUG-8/BUG-9 built 2026-08-15; BUG-10's code half built
  awaiting: [A1, N11, BUG-10]  # BUG-10 awaits the Render APP_BASE_URL change, and A1 awaits BUG-10
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
deliverable, not a repo artifact. Procore integration teardown (webhooks, outbox,
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

**All three cleared 2026-08-15** (branch `claude/roadmap-review-bugs-uinik2`).
One of them is not finished by the code alone — see BUG-10's Owed line.

| ID | Fix | Entry point | Pri |
|---|---|---|---|
| BUG-9 | ~~Fab order not flipping 2→1 at paint → complete; order cleared inconsistently~~ **built** | `app/brain/job_log/features/fab_order/tier.py` (tier logic: Complete=NULL, 0, 1, 2, dynamic 3+) | **high** |
| BUG-10 | Sub invite email ships a `localhost:5173` link — `APP_BASE_URL` unset | `app/config.py:76`, `app/brain/tm/subcontractors/command.py`. Code half **built** (loud fallback); **the Render config change is still owed** | **high — unblocks A1** |
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

### T1 · Timeline assignment — drag, assign, unassigned lane
*W5 · not-started · class build · due — · deps — · owner daniel · src bill-2026-08-15#L75 · upd 2026-08-15*

Effort L. **Priority 1 of the whole lane** and Bill's top ask, stated twice:
*"being able to **move the cards around and assign them**, and then **the vertical
column of unassigned so we can plug and play**"* [#L61]; *"**we're so close already
with the timeline view**… getting the **mirror cards**, and then being able to
**assign the cards and the dates into those individual people, is going to be the
most critical bit of it**"* [#L75].

The job it must do, in his words: see what's ready to ship, see what's **stored at
Mile High**, grab anything **past paint complete** and drop it where it goes —
*"use that for visual planning for the guys."* **Base is confirmed:
`feature/jay-view` (day-bucket timeline) + `feature/mirror-cards` (installer lanes
as gantt range bars).** **Un-parks D4**, which dissolves into this item.

**Drag is a real scheduling write** (confirmed intent, 2026-08-15) — dropping a
card writes the installer field that drives `comp_eta` / `num_guys`, not a
view-local arrangement. That is the point of the feature, not a side effect.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L61 — move/assign cards + a vertical unassigned lane to plug and play from
- 2026-08-15 · transcript · src bill-2026-08-15#L75 — mirror cards + assigning cards and dates to individual people is "the most critical bit"; purpose is visual planning off ready-to-ship / stored-at-Mile-High / past-paint-complete
- 2026-08-15 · decision · src — — priority 1 of W5; base = jay-view + mirror-cards; drag writes the real schedule; absorbs parked D4

### T2 · Admin member management — permissions + onboarding, consolidated
*W5 · not-started · class build · due — · deps — · owner daniel · src bill-2026-08-15#L83 · upd 2026-08-15*

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

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L83 — admin user view: add, assign permissions, invite, see all users, reset password, block
- 2026-08-15 · decision · src — — one page covering staff + subs; sub invite relocates here; admins own elevation/deferral; consolidation of scattered admin surfaces invited; runs in tandem with T1

### T3 · Subcontractor visibility — short-term scope
*W5 · not-started · class build · due — · deps T2 · owner daniel · src bill-2026-08-15#L93 · upd 2026-08-15*

Effort M. **Short term:** subs see their **T&M tickets plus the relevant data for
that job release**, pulled into the sub view. **Mid term this item dissolves into
T2** — visibility becomes a property of a role (sub / drafter / PM / admin),
not a per-surface decision.

**Do not build release-wide sub visibility now.** Bill's *"mostly the fab hour is
the only thing they don't actually see"* [#L93] is his eventual posture, not the
short-term scope. His written scope arrives with the Trello doc (Owed).

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L93 — "give them everything that they need, but not show them what they shouldn't see"; fab hours named as the main exclusion; scope to be detailed in his doc
- 2026-08-15 · decision · src — — short term = T&M + that job release's data; mid term collapses into the T2 role model

### T4 · Trello teardown
*W5 · not-started · class build · due — · deps T1 · owner daniel · src bill-2026-08-15#L69 · upd 2026-08-15*

Effort M, unknown until T1 lands. The actual decommission: mirror cards, the
board sync, `TrelloOutbox`, the list mapper, the webhook queue and its drainer.
Read-only is available as a staging step. Sequenced after T1 because the timeline
must be doing Trello's job before the plug comes out.

**Trail**
- 2026-08-15 · decision · src — — end state is dead, not read-only; expedited; teardown waits on T1

### A1 · T&M package — gated, then elevated
*W5 · blocked · class build · due — · deps BUG-10 · owner daniel · src bill-2026-08-15#L145 · upd 2026-08-15 · blocked-on BUG-10 since 2026-08-15*

Effort M. **Blocked on the invite link** — Bill cannot evaluate the sub side
without a sub in the system: *"I still can't get a sub added to it to see how it
looks on the back end yet"* [#L145]. **Elevates the moment BUG-10 lands**, which
makes that config fix the pivot for two lanes.

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
*W1 · not-started · due — · deps — · owner daniel · src bill-2026-07-22#notes · upd 2026-08-08*

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
**It shipped ahead of its own definition:** Open question 2 (what *MHMW Cost*
means) is still unanswered, so the third value is a live field with undefined
semantics. Cheap now, expensive if it accumulates rows under the wrong
reading — worth closing before N10 backfills against it.

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
*W2 · not-started · due — · deps N9 · owner daniel · src bill-2026-07-22#notes · upd 2026-08-06*

Effort S. **Un-dropped 2026-08-06.** Cut on 7/22 as "irrelevant basically" —
but paint invoicing requires photographs, which makes this a gate, not a
nice-to-have. N9 is what makes those photos usable: Katie's 7/22 problem was
*"I don't know what it is most of the time, what it's supposed to look like,
where it's at"* — a stamped photo is self-describing.

**Trail**
- 2026-07-22 · transcript · src bill-2026-07-22#notes — dropped as "irrelevant basically"
- 2026-08-06 · decision · src bill-2026-08-06#L613 — supersedes the 7/22 drop: paint invoicing requires photographs; J1 is the gate, N9 makes it work

### I4 · Installer invoicing — Subs → Invoice Paid
*W2 · built · due — · deps — · owner daniel · src bill-2026-07-22#notes · upd 2026-08-10*

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

**Banked as working:** the N5 shipping-stage rule (ship planning / ship complete
→ dump the color, keep the hard date) is confirmed correct in production
[#L127]; Bill hedged only about *"some old outliers"* [#L131].

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L115 — installer assignment and stage change both silently create hard dates; two independent reports the same morning
- 2026-08-15 · transcript · src bill-2026-08-15#L207 — Install Complete = physically installed; drop-ship should read Complete; "Complete = invoice marked off" was discussed and never built
- 2026-08-15 · decision · src — — merged the date-handling and staging questions into one audit; assigning an installer assigns no date; user agency over automation; client-facing ruleset is a deliverable

### AUD2 · Release-number uniqueness ruleset
*W3 · not-started · class audit · due — · deps — · owner daniel · src bill-2026-08-15#L177 · upd 2026-08-15*

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

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L159 — DWL issued a number already in use; worst case was the same job *and* the same release number
- 2026-08-15 · transcript · src bill-2026-08-15#L177 — Bill diagnosed it himself: the DWL side never checks the archive, the job log catches it later; "it should have caught that when it got to 108"
- 2026-08-15 · transcript · src bill-2026-08-15#L173 — instances 410-108 (archived twin Columbine Square) and 500-140 (Novel Flatirons); asks for auto-advance over blocking
- 2026-08-15 · decision · src — — full audit with client confirmation; year-as-metadata rejected (dates already in the record) with the reason owed back to Bill; uniqueness research replaces it

### N12 · Release Modal — distribute the one-stop surface
*W3 · in-progress · class build · due — · deps — · owner daniel · src bill-2026-08-15#L49 · upd 2026-08-15*

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

**Unchanged, and still AUD2's:** collision still **blocks and suggests** rather
than auto-advancing — Bill wants advance [#L173] and that is a client decision,
not a bug fix. Long-term identity likewise.

**Trail**
- 2026-08-15 · build · src — — archive-aware generator, scoped to the job number; block-vs-auto-advance deliberately left to AUD2

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
*W3 · in-progress · class fix · due — · deps — · owner daniel · src bill-2026-08-15#L81 · upd 2026-08-15 · owed daniel/set-APP_BASE_URL-in-render*

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

**Rider built 2026-08-15; the config change is NOT done and cannot be done from
a session — it is a Render dashboard edit.** The fallback is no longer silent:
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

> ⚠️ **Still owed: set `APP_BASE_URL` to the Brain's public domain in Render**
> (per deployed environment). Until that lands, invites now **fail loudly**
> instead of mailing a dead link — which is the correct failure, but it is still
> a failure, and **A1 stays blocked**. Re-test by sending Bill an invite and
> confirming the link opens.

**Trail**
- 2026-08-15 · transcript · src bill-2026-08-15#L81 — invite link broken on a real send to an external mailbox
- 2026-08-15 · note · src — — root cause found in code: unset `APP_BASE_URL` → localhost fallback; same var breaks the ticket-assignment link
- 2026-08-15 · build · src — — rider shipped: outbound links refuse to build against the localhost default outside local, checked before any write; config change in Render still owed, so A1 remains blocked

**The items W3 already carried, unchanged by the 8/15 pass:**

### N5 · Shipping-stage date discipline
*W3 · built · due — · deps — · owner daniel · src bill-2026-08-06#L1322 · upd 2026-08-08*

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

### N9 · Photo watermark + GPS
*W3 · not-started · due — · deps — · owner daniel · src bill-2026-08-06#notes · upd 2026-08-06*

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
verification (5–20 m), not position tracking. **Gated by Open question 3
(shared-tablet attribution) — decide before building the watermark**, because
it changes what is rendered onto the image. This is what makes J1 work.

**Trail**
- 2026-08-06 · transcript · src bill-2026-08-06#notes — client ask: stamp date, who took it, current stage, GPS coordinates
- 2026-08-06 · note · src — — EXIF test on a real field photo (Pixel 6a): Make/Model/DateTime survived, GPS IFD absent — re-encoded in transit; do not build on EXIF GPS
- 2026-08-06 · decision · src — — browser geolocation primary, EXIF opportunistic; capture date from EXIF falling back to uploaded_at; provenance recorded per coordinate; denial never blocks upload; cellular-tablet standing purchase spec (company iPads confirmed cellular)
- 2026-08-06 · question · src — — opened Open question 3: shared-tablet attribution; decide before the watermark is built

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

---

## Parked — real work, off the path

**Read "October" in this section as the old W1 window.** These blocks were parked
against a deadline that no longer exists (2026-08-15), so their re-check triggers
are still valid as *dependency* statements — "after P2 ships" — but their urgency
language is historical. Anything whose trigger is a W1 item is now gated behind
that lane reopening.

Each block states its re-check trigger. Also parked without blocks here
(reasoning retained in `docs/feature-catalog.md`): **D2** personal page ·
~~**D4** timeline view~~ *(un-parked 2026-08-15 — dissolved into **T1**)* ·
**A3** punch list · **A4** lookahead upload + markup ·
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
| **A1** | **BUG-10** *(ours, not Bill's)* | 2026-08-15 | Set `APP_BASE_URL` so the sub invite link resolves. Bill cannot test T&M until a sub is enrolled — *"I still can't get a sub added to it"* [bill-2026-08-15#L145]. **Elevates the moment this lands.** |
| N11 | bill/yellow-date-channel | 2026-08-15 | Which channel the yellow-date prompt uses — email, in-app, or both |
| P2 | bill/workflow-template-export | 2026-08-06 | Export or screenshots of the Procore workflow templates (the 8-step, per-PM list) — we are replicating them. **Dormant with W1 from 2026-08-15** |
| A2 | bill/co-log-excel-and-sample-email | 2026-07-22 | The change order log Excel + one sample CO email |

---

## Owed

External dependencies, all Bill's unless noted.

**Live — these block or shape current work:**

| Owed | Blocks | Since |
|---|---|---|
| **Trello phase-1 spec doc** — *"I'm gonna do like a chat this weekend… we should have something for you for early next week"* [#L59, #L263]. Also carries the **sub visibility scope** [#L93] | **Nothing — treated as a gap filler, not a gate** (decided 2026-08-15). T1 proceeds without it; his detail folds in on arrival, backed by his own *"we probably already have pretty good working understanding"* | 2026-08-15 |
| **T&M change notes** — *"if I can get you something today"*; originals lost [#L155] | A1's shape (not its start — that's BUG-10) | 2026-08-15 |
| **Katie's staging feedback** *(from Katie, not Bill)* | An input to AUD1, not a gate | 2026-08-15 |
| **Distribution channel for the yellow-date prompt** — email, in-app, or both | N11 | 2026-08-15 |
| **Confirm the updated uniqueness ruleset** — including *why* `340-26` is not needed | AUD2's change step | 2026-08-15 |
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

**Delivered since 2026-08-06:** the EOS metrics list — walked 2026-08-09, N8
built against it.

---

## Open questions

Nine were asked 2026-08-06; seven are resolved (see Resolved log). These
remain:

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
2. **What MHMW Cost means, and the tag semantics** *(source §10.2 — with the
   client)*. Gates **N1** becoming a required field. Backfill mechanism is
   settled (N10 bulk edit); the remaining question is semantic — rework,
   warranty, no-charge, or something else? It determines whether those
   releases are excluded from invoicing entirely or tracked as internal cost.
   **Answers: the client (Bill / office).** **Now urgent rather than tidy:**
   N1 shipped 2026-08-09 with MHMW Cost as a selectable value, so releases are
   being tagged against a meaning nobody has fixed. Every day this stays open
   is rows to re-read later.
3. **Shared-tablet photo attribution** *(source §10.3 — decide before N9
   builds)*. Gates **N9**. The watermark stamps *who took the photo* from the
   logged-in Brain user; on a shared company iPad under a generic login every
   photo carries the same name — exactly the metadata Katie needs, made
   worthless. Options: individual logins on shared tablets · a "who is this"
   picker at capture · tablet photos carry no attribution while phone photos
   do. Changes what is rendered onto the image, so it precedes the build.
   **Answers: Bill.**

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

---

## Sources

| Slug | Path | Role |
|---|---|---|
| bill-2026-08-15 | `~/Desktop/Transcripts/MHMW/Bill-8-15-2026-clean.md` | Friday standup (Bill) — **the reset**: Procore renewed, Trello promoted. `#LNNN` anchors are line numbers in the **cleaned** transcript, not the raw (`Bill-8-15-2026.txt` is too interleaved to cite). Findings: `processed/Bill-8-15-2026.md` |
| bill-2026-08-06 | `~/Desktop/Transcripts/MHMW/processed/Bill-8-6-2026.md` | Submittal-system working session (Bill, Colton) — primary transcript; `#LNNN` anchors are its line numbers |
| bill-2026-07-22 | `~/Desktop/Transcripts/MHMW/processed/Bill-7-22-2026.md` | Ops/roadmap review — the October deadline surfaces; A2, C3-origin, N8, J1-drop |
| notes-2026-08-04 | daily notes (no transcript) | Daniel's 2026-08-04 notes — N5 origin, N4 symptom |
| pr#NNN | GitHub PRs on the milehigh repo | Build provenance for merged work — #323–#334 (2026-08-06/08), #336–#338 (2026-08-09, v2.0.338), #339 (2026-08-10) |
