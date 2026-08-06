# Procore Decommission — Path Forward

> ### 📌 Superseded on four points — 2026-08-06, later the same day
>
> **[`roadmap.md`](roadmap.md) §1b and §3 are now the authority.** Written the
> same morning, this document predates the afternoon's decisions and disagrees
> with the roadmap on:
>
> 1. **No new `BrainSubmittal` table** — `Submittals` *is* the native record and
>    gets extended. §1.4's proposed table is retired.
> 2. **§4's migration mostly dissolved** — legacy rows need a backfill, not a
>    migration; cut-over gates at the *project*, not the submittal. **But §4's
>    warning about attachments survives as roadmap P11**: the documents
>    themselves are not in our DB and vanish at lapse.
> 3. **Five workflow responses, not six** — Rejected dropped, Void kept.
> 4. **The slice plan here is the full scope, which does not fit the window** —
>    see roadmap §1b for the arithmetic and the reduced October scope.
>
> The model (§1), the intelligent-workflow rules (§2), and the per-slice detail
> remain the deepest write-up of *how* each piece works. Read them with the four
> corrections above in mind.

**Written 2026-08-06.** Synthesis of three inputs:

1. Bill's written spec — `MHMW_Brain_Procore_Decommission_Submittal_System_Developer_Handoff.md`
   ("Document 001"), the Phase-1 vision.
2. The **2026-08-06 working session** — findings in
   `~/Desktop/Transcripts/MHMW/processed/Bill-8-6-2026.md`. This is the session
   [`feature-catalog.md`](feature-catalog.md) B2 was waiting on.
3. [`feature-catalog.md`](feature-catalog.md) + [`ops-planning.md`](ops-planning.md) — everything
   already ranked, shipped, or deferred.

This document supersedes catalog item **B2** and takes over its planning. The catalog remains the
source of truth for everything *outside* the Procore exit; this is the source of truth for the exit.

**Effort:** S = under a day · M = 2–4 days · L = 1–2 weeks · XL = 3+ weeks.

---

## 0. The forcing function, restated

**The Procore contract ends in October.** Roughly **eight weeks** from this document.

Bill drew the scope boundary himself, twice, and it is tighter than either the catalog or his own
written spec:

> *"brain projects, brain submittal handling, and ball-in-court workflow is the absolute core need to
> have before October so you don't have to re-sign with Procore."* — *"Absolutely."* [L802–808]
>
> *"jobs, a job silo, and just a submittal piece. The rest of it is great accessories but not terribly
> important."* [L810–811]

**Three things must exist in October. Everything else is negotiable, including things Bill's own
written spec lists as Phase 1.**

He also resolved the catalog's last open call. The 7/22 catalog closed asking *"does B2 outrank A1?"*
Bill answered before Daniel could ask:

> *"the ball in the court workflows?"* — *"Yeah."* — *"Priority one?"* — *"Yeah."* [L30–35]

A1 (T&M) shipped 2026-07-26, so nothing was lost to the ambiguity. But from today, **the submittal
system outranks every unshipped item in the catalog.**

### What "leaving Procore" actually costs us, and what it doesn't

One meaningful de-risking from this session: **MHMW keeps access to customers' Procore instances as
an invited user** [L811–818]. The current drawing set is always reachable through the GC's environment,
which is where our guys already go [L732–738]. Losing our own Procore does **not** cut us off from
project drawings.

That removes the panic from B4 as a *blocker* (it remains an open question about programmatic access)
and it demotes plan-document hosting out of the critical path entirely.

What we genuinely lose in October: the submittal workflow engine, the submittal record itself, our
document history, and the aging view. That is exactly the three-item list above.

---

## 1. The model

This is the one section worth getting right before any code. The written spec and the meeting say
different-sounding things and both are correct at different levels.

### 1.1 The tree

> *"the root would be the approved submittal"* [L163] · *"Tree of Life submittal style"* [L177–179]

```
Project
 └── Contract Scope            one discrete package of work sold
      └── Submittal (sub-GC)   ← the root; one record, many revisions
           ├── DRR  ──── 1:1 ──── FC ──── 1:N ──── Release(s)   ← via the FC Separator
           ├── DRR  ──── 1:1 ──── FC ──── 1:1 ──── Release
           └── DRR  ──── 1:1 ──── FC ──── 1:1 ──── Release
```

**The constraints, all from the meeting, all deliberate:**

- **One approved sub-GC → many DRRs.** The PM creates each one. [L164–166, L1398–1403]
- **DRR → FC is 1:1, enforced.** Bill explicitly rejected one DRR feeding several FCs: *"one DRR into
  multiple FCs just allows for opportunity to drop off of data."* Want separate paperwork? Create
  separate DRRs. [L1398–1420]
- **FC → many releases is allowed, but only through the FC Separator** (§2.5), and only along the
  fab-vs-install / by-location axis — never as an ad-hoc fan-out.
- **Every node pre-fills from its parent.** *"We should never retype anything that was typed in there
  once that's job specific."* [L171–173]

### 1.2 "One record, many revisions" — reconciled

The spec says *"One Submittal Record exists for the life of the project. It changes state rather than
creating new records."* The meeting describes a tree. These are not in conflict:

- **Within a node**, the spec is exactly right: a DRR does not become a new row when it's revised, or
  when it's approved, or when it goes to FC. It changes `state` and accrues a **revision**.
- **Between nodes**, the tree governs: a DRR is a child record of its sub-GC, not a state of it.

**This is also the fix for a documented data problem.** `docs/submittal-id-coherence-audit.md` found
that today, a logical scope passes through DRR → GC → FC as **three unrelated Procore records with
three different ids and nothing in the code linking them** — every bridge between them is a human
typing a number twice or a fuzzy title match. Owning the record collapses that problem instead of
working around it. It also **dissolves catalog item B3** (soft-link sub/DRR/FC): there is nothing to
soft-link when the link is the primary key.

### 1.3 States

Per node, from the spec [handoff §Submittal Lifecycle], plus **As-Built** added in the meeting:

```
Draft → Internal Review → Submitted to GC → Returned → Revise & Resubmit
      → Approved / Approved as Noted → Eligible for DRR
      → DRR → Approved for FC → FC → Released → As-Built
```

**As-Built is a version series on the released FC, not a new node type.** Bill: *"that's like the
versioning we have now in the job log, same exact concept."* [L48–52]

**FC is terminal for review.** *"once it's FC, we don't review it anymore. FC is ready to go, print it
out, take it to the guys."* [L403–406] This is why FC is isolated so hard today — crews were building
off DRR sets. [L131–136]

### 1.4 Proposed tables

Sibling-table conventions, per the catalog's own guidance in §A. Names are proposals.

| Table | Notes |
|---|---|
| `ContractScope` | FK to `Projects`. Name, description, estimate reference, contract value. The launch point for every submittal |
| `BrainSubmittal` | The node. `contract_scope_id`, `parent_id` (nullable — DRRs point at their sub-GC), `phase` (sub_gc / drr / fc), `state`, `assigned_drafter`, `pm`, `due_date`, `linked_release_id` |
| `SubmittalRevision` | `submittal_id`, `rev`, PDF reference, uploader, timestamp, `is_current`, `obsolete_at` |
| `WorkflowTemplate` | Keyed on **project × phase** [L335–343]. Ordered default steps |
| `WorkflowInstance` | One per submittal. Current step pointer, history |
| `WorkflowStep` | `instance_id`, `position`, `assignee_user_id`, `state`, `added_by` (for manual insertions), `is_agent_step` |
| `WorkflowResponse` | `step_id`, `response` (the six), `note`, `on_behalf_of_user_id` (for Review Skipped), `responded_at` |

**Naming collision to avoid.** `Submittals` (table `submittals`) already exists and holds
Procore-sourced rows — 3,892 of them across 46 projects, per `docs/submittal-status-drift.md`. Do not
overload it. See §4 on migration.

**Reuse, do not rebuild:** `ReleaseDrawingVersion` and `DrawingVersionComment` already model
versioned PDFs with comment threads. `CarmenDrawingReview` / `CarmenReviewFeedback` already model AI
findings with accept/reject + notes. `RawSourceRecord` + `GraphSubscription` + `LakeIngestState`
already land mail into the lake. The submittal system should sit on top of all four.

---

## 2. Intelligent workflow building

The core new concept from the session, named live and immediately adopted by Bill [L289–299]. It
replaces the spec's static nine-step ball-in-court list — **that list is a default template, not the
mechanism.**

**The problem it solves:** in Procore today, when Bill responds *Revise & Resubmit* because he wants to
see the drawing again, nothing happens. He has to manually append himself as a ninth workflow step.
[L246–256]

### 2.1 Response → behavior

| Response | Behavior |
|---|---|
| **Approved** | Return to drafter with the ability to advance to the next phase. **No Carmen review.** [L303–311, L434–437] |
| **Approved as Noted** | Return to drafter to address notes → **trigger Carmen** to verify the notes were captured. Clears → drafter may release. Fails → re-notify the drafter. [L311–321] |
| **Revise & Resubmit** | *"keep me in the loop"* [L256]. When all approvers finish, return to the drafter, then **automatically re-add every approver** to see the revision. Loops indefinitely. [L322–327] |
| **Review Skipped** | Force-clear a reviewer. **Records who clicked it and on whose behalf.** Keep the skipped person notified. Replaces Procore's "For Record." [L344–384] |
| **Rejected** / **Void** | Close the record out as voided. [L390–393] |

Plus: **canned responses and a freeform box** [L216–220].

### 2.2 Rules that apply across all of them

- **Anyone can be inserted into a workflow at any point.** *"Louis needs to see this and he's not in the
  workflow — boom, we can load him in there."* [L267–269]
- **Carmen suggests insertions.** [L280–286]
- **The drafter runs the Carmen review first, as their own baseline**, before a PM ever sees it — so
  self-correctable problems never reach a reviewer. [L61–65]
- **Review can be run at any point, but a review already run upstream in the sequence is referenced,
  not re-run.** [L64–66] This is a cost control as much as a UX rule.
- **Templates key on project × phase.** A DRR gets a different approver set than a sub-for-GC. [L335–343]

### 2.3 The transitions, and who owns them

| Transition | Owner | Trigger |
|---|---|---|
| Create submittal | PM / Lead Drafter | From a Contract Scope |
| sub-GC → **DRR** | **PM** | A "Create DRR" button appears once the sub-GC is Approved / Approved as Noted. Opens a form pre-filled from the parent; PM adds building/area specifics [L164–172, L419–423] |
| DRR → **FC** | **Drafter** | Button appears once all reviewers are Approved / Approved as Noted. Opens a window, drafter drops the final PDF [L412–416, L440–443] |
| FC → **Release** | **Drafter** | The same action. The FC PDF is **flagged**, not re-uploaded [L444–446] |

> *"the project managers create the workflow for the DRR, and the final execution of the workflow for
> the DRR is the drafter completing the FC."* [L426–427]

### 2.4 Where it lives

**Not a standalone app.** [L1129–1140]

- **Drafting Work Load** is the drafter's daily surface. The existing **"Procore Status" dropdown is
  replaced by the intelligent-workflow actions dropdown.** [L1141–1161] Frontend touchpoints already
  identified: `frontend/src/pages/DraftingWorkLoad.jsx`, `SubmittalRow.jsx`, `SubmittalCard.jsx`,
  `useFilters.js`, `transformers.js`.
- **Project page** gets a submittals section plus the aging view (§3.3).
- Backend: `app/brain/drafting_work_load/` (engine/routes/service, ~2,500 lines) already owns the
  drafter's view of submittals. The workflow engine slots underneath it.

### 2.5 FC Separator

The one sanctioned FC → many-releases path, and a real feature in its own right. [L1430–1524]

**The case:** 1,000 identical brackets. One fab run. Eight install areas. Possibly a different install
crew by area three. Also: embeds and hold-downs, where install happens months after the drop-ship.

**What it produces:**

- **One fab-only release** — all fab hours, zero install hours, stops at welded QC → paint.
- **N install releases** — zero fab hours, install hours apportioned, one per location.

**How the apportioning works:** *"he's not doing the math — there's a thousand hours and a thousand
pieces, we have 200 here, there's 200 hours."* [L1469–1471] **Location comes from the release
description; quantity drives the hours.**

**This is a manual ritual today.** Colton creates one release with everything, copies it, deletes the
install portion to make the fab one, then makes N more copies and edits quantities per section.
[L1451–1454] The feature is worth building because it removes a known-error-prone hand process, not
because it's novel.

**Design against a live case:** Bill committed to trigger Daniel when **submittal 500-998** goes to FC
[L1483–1491]. Do not finalize the separator's UX before that lands.

---

## 3. Sequenced plan

Eight weeks. Slices are ordered so that each one is independently shippable to the pilot project and
none of them blocks on Bill.

### Slice 0 — Preconditions · **this week** · S–M

Not features. The October plan makes the Brain the **system of record for submittals and drawings**,
which changes the risk profile of two items the catalog already flagged.

| # | Item | Why now |
|---|---|---|
| 0.1 | **K4 — backups** | Catalog Tier 0, unresolved since 2026-07-22, a runbook sitting unmerged on `claude/render-backup-data-architecture-vlizsr`. **When Procore goes away, an unrecoverable Postgres and an unbacked-up disk stop being a risk and become the plan.** This is the argument that should finally move it |
| 0.2 | **K3 — object storage decision + cost numbers** | Bill asked for numbers on the record: *"I'll start preparing some numbers for that, so there's some awareness"* [L662–666]. Every binary currently sits on one Render disk. Procore's document history does not fit that shape |
| 0.3 | **Archival policy** | Agreed in the meeting: closed projects get metadata + a text record, and the drawing files get dropped [L666–683]. Write it down; it bounds 0.2's cost estimate |

**Deliverables:** backups enabled and verified · a storage recommendation with dollar figures for Bill ·
an archival policy paragraph in this doc.

### Slice 0.5 — Live bugs and the cheap permission win · **this week** · S

These are the client's current pain, they cost hours not days, and shipping them buys credibility while
the big build is invisible.

| # | Item | Source |
|---|---|---|
| 0.4 | **FC / Procore link graying on the job log** | Colton's top complaint. Breaks when the FC set updates; behaves differently on number vs name click [L1334–1371]. Start at `app/procore/fc_retry_worker.py` + `FcCollectionRun` |
| 0.5 | **Ball-in-court uncheck 1 → 0 does nothing** | Bill self-noted it live [L1064–1068] |
| 0.6 | **Drafter edit permissions, `job` → `released` columns** | Agreed and widened by Bill himself [L1221–1245]. Via the existing gear control, not inline editing — *"I just don't want to accidentally delete in there"* |
| 0.7 | **Confirm the release-number duplicate** | Rollover worked; one duplicate reported secondhand [L1051–1095] |

### Slice 1 — The spine · **weeks 1–3** · L–XL

**Contract Scope → native Submittal → ball-in-court workflow engine.** The "absolute core."

1. Models per §1.4, with an idempotent migration script (per `migrations/README.md` — hand the command
   to Daniel to run per environment; do not execute DDL).
2. The workflow engine: templates, instances, steps, responses, and the §2.1 mutation rules.
3. Contract Scope CRUD on the project page.
4. Native submittal creation from a Contract Scope.
5. **DWL actions dropdown replaces the Procore status dropdown** (§2.4).
6. Events into `SubmittalEvents` (or a sibling) so the existing undo/audit machinery applies.

**Exit criterion:** a submittal is created, routed, responded to, and advanced end-to-end on **660 Fox
Hill** — the pilot Bill named, chosen because it's small and limited scope [L1041–1049] — **in parallel
with Procore, not instead of it.** 645 is the backup pilot.

### Slice 2 — Revisions, PDFs, Carmen in the loop · **weeks 3–4** · L

1. Revision stack per submittal; prior revisions always reachable.
2. **Obsolete watermark** on superseded revisions — Bill's spec is a full-page red treatment, *"you look
   at it and you're like, what the fuck"* [L104–110].
3. Carmen as a **workflow step**, triggered on the Approved-as-Noted return to verify notes were
   captured; failure re-notifies the drafter [L311–321].
4. Overlay comparison between revisions [L100–104].
5. **Carmen's findings stay in the side panel**, never burned onto the PDF — clicking a finding snaps
   the viewer to the page. This is a stated design decision in the spec and matches what already exists.

**Reuse:** `ReleaseDrawingVersion`, `DrawingVersionComment`, `app/brain/pdf_review/`,
`CarmenDrawingReview`, `CarmenReviewFeedback`. Very little of this is new construction.

**Design risk, called out in the meeting:** visualizing per-page granular change across revisions *"is
probably going to take some time to figure out the most appropriate way to visualize"* [L117–119].
Budget a design pass; don't assume the first attempt lands.

### Slice 3 — Outbound and inbound · **weeks 4–6** · L

**Out:**
1. Cover sheet from **estimate data** — description, details, locations. **Not the value.** [L868–871]
2. Merge cover sheet + current revision into one outgoing PDF; pick a distribution list [L872–877].
3. **Send from Carmen, on behalf of the user**, opening an editable draft [L891–909]. The per-user email
   connector is explicitly the later, more ambitious version — do not build it now.

**In:**
4. **Returned submittals arrive through the Carmen mailbox.** Identify project → identify submittal →
   import PDFs and markups → update revision state → assign next ball-in-court → notify. *"No manual
   filing should be required."*

   **This is the least-new slice in the plan.** `RawSourceRecord`, `GraphSubscription`,
   `LakeIngestState` and the Carmen mail poll are already on main; this is a classifier and a router on
   top of an ingestion path that works.

**Aging (3.5) — the one Procore view Bill actually wants back:**

5. **Outstanding submittals with aging, on the project page.** The single useful thing on Procore's
   project page is *all open items*, and specifically how long a submittal has been sitting with the GC
   [L1110–1117]: *"that one, because it's out of our system, it's not in anybody's ball and court, then
   we're just like — where is all this stuff?"*
6. **Siloed by our phases**, which Procore structurally cannot do — *"it just knows submittals is one
   bucket."* **Only sub-for-GC and DRR appear. FC does not.** [L1121–1125]
7. **Mechanic:** on send to the GC, the submittal enters a waiting state with a duration; at the
   two-week mark (editable per project) Carmen drafts the follow-up. Bill described this as landing in
   *"Carmen's ball and court"* [L1117–1120] — see open question 5 on whether that should be a real
   assignee or a status plus a timer.

This is small next to 1–4 in this slice and disproportionately visible to Bill. Do not let it fall off
the end.

### Slice 4 — DRR → FC → Release, and the Separator · **weeks 6–7** · L

1. PM "Create DRR" from an approved sub-GC, pre-filled from the parent [L164–172].
2. Enforce **DRR:FC 1:1** in the model, not just the UI.
3. Drafter FC conversion: final PDF upload, flagged as the FC set, no double upload [L440–446].
4. **Create the release from the submittal page**, pushing into the job log. **Keep the existing job-log
   paste path** — still needed for FCs and verbal work orders. *"still got to be able to ingest it both
   ways."* [L452–458]
5. **FC Separator** (§2.5) — design against 500-998.

### Slice 5 — The billing spine · **weeks 7–8, or the first thing after October** · M–L

Roughly 200 lines of the meeting, and the thing that makes Katie's invoicing real. **It is not required
to leave Procore** — sequence it last inside the window and let it slip past October without drama if
Slices 1–4 need the room.

1. **Ingest the release Excel billing sheet at FC/release** — the data, not the sheet. *"if we copied
   and pasted this in, just this data, not the sheet, that would be perfect."* [L502–503] ~340 KB per
   file, a non-issue [L648–653]. Bill owes a sample.
2. **Back-end only.** *"It's all back-end data."* [L506–508] Nothing renders on the submittal.
3. **Stage → invoiceable gates** [L607–631]:

   | Gate | Invoiceable |
   |---|---|
   | Material ordered | 100% material |
   | Fab complete | 100% fab |
   | Paint complete | 100% paint (no split — photos are required for invoicing anyway) |
   | Install % | equipment **and** install labor, at the install percentage |

4. **Budget vs actual per department**, reconciling to the original quote value so variance in either
   direction doesn't create an accounting error [L550–560].
5. **Katie's invoicing tab**: potential invoiceable value per release → mark invoiced → zeroes → next
   tranche. QuickBooks template generation is downstream of this, not part of it [L509–517].

**Consistency check against the written spec.** The spec puts *"financial permissions & sensitive data
walls"* out of Phase 1 scope, and that still holds — the **data ingest** is in, the **permissions wall**
is not. That is a real deferral with a real edge, and it should be stated to Bill rather than assumed.

---

## 4. The migration nobody has scoped yet

**This is the largest unscoped risk in the plan, and it is not in either source document.**

Production holds **3,892 Procore submittals across 46 projects** (`docs/submittal-status-drift.md`,
scanned 2026-07-28). Many are in flight. In October the source of those rows disappears.

Unanswered:

1. **Coexist or replace?** Does `BrainSubmittal` live alongside `Submittals`, or does `Submittals`
   become a legacy read-only archive? Everything downstream keys off the existing table — the DWL, Rel
   assignment, `start_install`, `linked_release_id`.
2. **The tree has to be reconstructed.** Legacy DRR/GC/FC exist as three unlinked records
   (`docs/submittal-id-coherence-audit.md`). `app/brain/submittal_matching/` has a matcher; it was built
   for a different job and would need evaluating against this one.
3. **Cut-over for in-flight work.** The 7/22 findings already flagged this: projects mid-lifecycle need
   explicit *stop-here* cut-points. A submittal approved in Procore in September and DRR'd in the Brain
   in October has to work.
4. **Attachments are the slow part**, and they always are. File volume plus rate limits, against a hard
   expiry with no second attempt.

**Recommended:** run the inventory in Slice 1 — enumerate Procore against `Submittals` /
`SubmittalEvents` / the drawing tables and quantify the delta. It's roughly a day, it's read-only, and
every other decision here depends on the number it produces. This is catalog **B1**, currently owned by
Bill; the *inventory* should come back to Daniel even if the export negotiation stays with Bill.

**Bill's first move on B1 is still one email** — ask Procore for a bulk export on contract termination.
Most platforms offer one, and it beats scraping the API on every axis.

---

## 5. Explicitly out of the October scope

Each of these is cut with a citation, so nobody has to re-litigate it from memory.

| Item | Why |
|---|---|
| **Mission Brief** (estimate intelligence, drawing clips, historical comparison) | Bill: *"easily phase three."* [L1019–1020] **Directly contradicts his own written spec, which lists it as a Phase 1 deliverable.** The transcript is later and more specific — but this cut should be confirmed with him explicitly, because it is the most visible thing being removed |
| **Plan / takeoff drawing hosting** | *"easily phase two… it could be post-October if we had to, that wouldn't be the end of the world"* [L716–718] · *"Cool bonus if it makes it, not mission critical"* [L770–771]. Reachable through the GC's Procore anyway. Overlaps existing takeoff-viewer work |
| **RFIs · photo capture by project · RFPs** | *"we need it but it's not imperative, we can do it through email if we have to"* [L37–41] |
| **Estimating AI / takeoff ingestion** | Bill was enthusiastic, then cut it himself: *"the estimating build is going to be too big."* [L792–794] |
| **Per-user email connector** | Parked in favor of send-from-Carmen-on-behalf-of [L888–909] |
| **Schedule of values generation** | Out per the written spec; the billing sheet ingest is the stopgap [L498–502] |
| **Financial permissions / data walls** | Out per the written spec. Slice 5 ingests the data; it does not gate it |
| **Everything in the spec's out-of-scope list** | BrainStem full replacement, purchasing, inventory, customer portals, QuickBooks, resource leveling, material futures, T&M (already shipped separately as A1) |

---

## 6. What this does to the rest of the catalog

| Catalog item | New status |
|---|---|
| **B2 Submittal workflows** | **No longer deferred, no longer blocked.** The working session happened. Planning moves to this document |
| **B3 Soft-link sub/DRR/FC** | **Dissolved as a feature.** §1.2 — owning the record makes the link a primary key. The correctness question it raised is answered by `docs/submittal-id-coherence-audit.md`: three separate Procore records, and the new model removes the class of problem |
| **B1 Procore export** | Still Bill's. **The inventory sub-task should come back to Daniel** (§4) |
| **B4 Customer-Procore access** | **De-risked.** Invited-user access survives October [L811–818]. Still worth the rep question; no longer a blocker |
| **K4 Backups** | Unchanged in rank (Tier 0), **strengthened in argument** (§0.1) |
| **K3 Object storage** | **Promoted from unranked to a precondition.** Bill asked for the numbers on the record |
| **K2 → D1 → D2** | Was "the whole critical path" as of 2026-07-26. **It is not any more.** The project page (D1) is now a *dependency* of the submittal work rather than a peer — the submittal section and aging view live on it |
| **A2 Change orders** | Still blocked on Bill. Unchanged |
| **C2 Parts + hardware list** | Stays experimental. The spec lists hardware verification under Carmen; it is not October-critical |
| **L1 Styling v3** | The sequencing conflict the catalog flagged now has a clear answer: **not before October.** The submittal surfaces get built on what exists |

---

## 7. Owed by Bill

Ordered by what blocks soonest.

| Owed | Blocks | Since |
|---|---|---|
| **Procore workflow template export/screenshots** (the 8-step, per-PM list) | Slice 1 templates — we are replicating them | 8/6, implied [L237–244] |
| **Trigger on 500-998 going to FC** | Slice 4 separator design | 8/6, committed [L1488–1491] |
| **Sample release Excel (billing sheet)** | Slice 5 | 8/6 [L473–474] |
| **Carmen "expertise / best project engineer" chat doc** | Slice 2 framing | 8/6 [L1586–1589] |
| **Explicit confirmation that Mission Brief is out of October scope** | §5 — it contradicts his written spec | new, raised here |
| Procore bulk-export request + customer-Procore rep question | B1, B4 | 7/22 |
| Change order log Excel + sample CO email | A2 | 7/22 |
| Stage weight approval · Carmen avatar | E2 · C9 cosmetics | 7/22 |

---

## 8. Open questions

1. **Coexist or replace** for `Submittals` vs `BrainSubmittal` (§4). Needs answering in Slice 1, not
   Slice 4.
2. **Cut-over rule for in-flight projects.** Flagged 7/22, still unanswered. A submittal approved in
   Procore in September and DRR'd in the Brain in October must work.
3. **Does the Brain need to *serve* Procore submittal history after October, or just retain it?**
   Archival vs operational. Bounds §4 and the storage estimate.
4. **How is a Contract Scope created** — manually at project setup, or derived from the estimate? The
   spec implies the estimate; the estimate integration is Phase 3. Manual is the safe answer for
   October, but it should be a decision rather than a default.
5. **Carmen's ball-in-court for GC-side aging** (§3 Slice 3.7 / [L1117–1120]) — is Carmen a real workflow
   assignee with a queue, or is this a status plus a timer? Cleaner as a timer; Bill described it as a
   court.
6. **What happens to a partly-released FC when a revision lands?** Not discussed. Real, given the
   Separator can produce eight releases from one FC.

---

## 9. Honest read on the eight weeks

Slices 1–4 are the October commitment and they total roughly **six to seven weeks of build** with no
slack, against an eight-week window that also contains Slice 0, live bug fixes, and a migration
(§4) that has not been scoped because the information to scope it doesn't exist yet.

**That is tight but not unreasonable**, on three conditions:

1. **Slice 0 happens this week**, not opportunistically. Backups in particular have now been Tier 0 for
   two weeks with nothing enabled — and the October plan is what converts that from a risk into a
   certainty.
2. **The §4 inventory runs early**, in Slice 1. It is the only thing here that can produce a surprise
   large enough to change the plan, and it costs a day.
3. **Slice 5 is allowed to slip.** It is the natural release valve — genuinely valuable, and genuinely
   not required to stop paying Procore.

The pilot discipline matters more than the schedule. **660 Fox Hill runs in parallel with Procore from
Slice 1 onward**, so that by the time the contract lapses the system has been carrying a real project
for weeks rather than being switched on the day the alternative disappears.

---

## Source meetings

| Date | Meeting | Findings |
|---|---|---|
| 2026-08-06 | Submittal system working session (Bill, Colton) | `~/Desktop/Transcripts/MHMW/processed/Bill-8-6-2026.md` |
| 2026-07-22 | Ops / roadmap review — the October deadline surfaces | `~/Desktop/Transcripts/MHMW/processed/Bill-7-22-2026.md` |

Written spec: `MHMW_Brain_Procore_Decommission_Submittal_System_Developer_Handoff.md` (Bill, "Document
001"). Not in this repo — it is Bill's deliverable, not a repo artifact.
