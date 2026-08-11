---
project: MHMW
updated: 2026-08-10
verified: origin/main @ 89c565f — v2.0.339
config:                       # inputs to derived math — store inputs, never results
  horizon:
    - 2026-10-31 Procore contract lapses
  effort_midpoints: {S: 0.5, M: 3, L: 7.5, XL: 15}
queue:                        # agent-maintained, set by agreement in session
  now: K3
  next: [P11, P1, P0]
  awaiting: [A2]
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

**Tier key (workstreams — the project's forcing logic):**

| Tier | Workstream |
|---|---|
| W0 | Preconditions — everything else sits on these |
| W1 | Procore exit — October-critical; outranks everything unshipped |
| W2 | Money — the release valve; allowed to slip |
| W3 | Daily use — cheap, unblocked, currently costing time |
| W4 | Carmen |

**Redaction:** MHMW staff first names (Bill, Colton, Katie, David, Dalton) may
appear. GC/customer companies appear only as job numbers (e.g. 500-998) or
project names already in the record (660 Fox Hill, 645). No contract dollar
values are committed to this file.

**Effort key:** S = under a day · M = 2–4 days · L = 1–2 weeks · XL = 3+ weeks.
Each item states its effort letter in its Now paragraph. **Fit is derived, not
stored:** sum open W0+W1 item efforts via `config.effort_midpoints` against
`config.horizon`. As of 2026-08-06 that arithmetic did not fit the window even
at the reduced scope — which of P3 / P5 / P6 / P8 gets lost, what gets thinner,
or whether the date moves is Bill's call (Owed, row 1). Recompute at render;
do not trust remembered totals.

**The 2026-08-09/10 wave did not change that picture.** N4 closed and K4's
Postgres half closed, which shrinks W0 — but **no W1 item moved**, and W1 is
what the horizon is made of. Everything that shipped on 8/9–8/10 came from W2,
W3, W4, and the parked lane. Eleven weeks remain and Workstream 1 has not
started; the cut-list decision is more overdue than it was, not less.

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

## Workstream 1 — Procore exit (October)

The forcing function: the Procore contract lapses in October
(`config.horizon`). Bill drew the boundary himself — *"brain projects, brain
submittal handling, and ball-in-court workflow is the absolute core need to
have before October"* [bill-2026-08-06#L802] — and invited-user access to
customers' Procore survives the lapse [#L811], which keeps plan-document
hosting off the critical path. Full data model in
`docs/procore-decommission-plan.md`.

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

One thread across both meetings, sequenced (collapse ⑤). **Not
October-critical** — the natural release valve if Workstream 1 needs the room.

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
remainder cleared 2026-08-09** (PRs #336–#338, v2.0.338). Workstream 3 is now
down to two items, neither of them blocking anything in October:

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

---

## Parked — real work, not October

Each block states its re-check trigger. Also parked without blocks here
(reasoning retained in `docs/feature-catalog.md`): **D2** personal page ·
**D4** timeline view · **A3** punch list · **A4** lookahead upload + markup ·
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
| P2 | bill/workflow-template-export | 2026-08-06 | Export or screenshots of the Procore workflow templates (the 8-step, per-PM list) — we are replicating them |
| A2 | bill/co-log-excel-and-sample-email | 2026-07-22 | The change order log Excel + one sample CO email |

---

## Owed

External dependencies, all Bill's. Transcribed from the 2026-08-06 roadmap §9.

| Owed | Blocks | Since |
|---|---|---|
| **The October cut-list decision** — even the reduced scope overruns the window; which of P3 / P5 / P6 / P8 he loses, what gets thinner, or the date moves — his pick, made early, not discovered in week seven | The scope contract for everything above | 2026-08-06 |
| **Procore workflow template export / screenshots** (the 8-step, per-PM list) | P2 — we are replicating them | 2026-08-06 |
| **Trigger on 500-998 going to FC** (committed) | P5 design | 2026-08-06 |
| **Sample release Excel (billing sheet)** | N2 | 2026-08-06 |
| **Carmen "best project engineer" chat doc** | Workstream 4 framing | 2026-08-06 |
| **Confirmation that Mission Brief is out of October scope** — it contradicts his own written spec; he should confirm it, not discover it | P0 scope | 2026-08-06 |
| **What happens to in-flight Procore projects when the subscription lapses** — possibly a contract-renewal question, not a build one | Open question 1 / P10 | 2026-08-06 |
| Procore bulk-export request; customer-Procore question to his rep | P10, B1/B4 | 2026-07-22 |
| Change order log Excel + sample CO email | A2 | 2026-07-22 |
| Stage weight approval · Carmen avatar | E2 · C9 cosmetics | 2026-07-22 |

**Delivered since 2026-08-06:** the EOS metrics list — walked 2026-08-09, N8
built against it. Everything else above is still outstanding, including the
October cut-list decision, which is now four days older against an eleven-week
window.

---

## Open questions

Nine were asked 2026-08-06; seven are resolved (see Resolved log). These
remain:

1. **In-flight Procore projects at the October line** *(source §10.1 — new,
   unanswered)*. Gates **P10** (and the cut-over posture generally). The gate
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

---

## Sources

| Slug | Path | Role |
|---|---|---|
| bill-2026-08-06 | `~/Desktop/Transcripts/MHMW/processed/Bill-8-6-2026.md` | Submittal-system working session (Bill, Colton) — primary transcript; `#LNNN` anchors are its line numbers |
| bill-2026-07-22 | `~/Desktop/Transcripts/MHMW/processed/Bill-7-22-2026.md` | Ops/roadmap review — the October deadline surfaces; A2, C3-origin, N8, J1-drop |
| notes-2026-08-04 | daily notes (no transcript) | Daniel's 2026-08-04 notes — N5 origin, N4 symptom |
| pr#NNN | GitHub PRs on the milehigh repo | Build provenance for merged work — #323–#334 (2026-08-06/08), #336–#338 (2026-08-09, v2.0.338), #339 (2026-08-10) |
