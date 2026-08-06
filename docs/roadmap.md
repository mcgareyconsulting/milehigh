# MHMW Brain — Roadmap

**Written 2026-08-06.** Replaces `feature-catalog.md` as the working roadmap. The
catalog remains the historical record of what was discussed, ranked, shipped, and
why — this is what we are building and in what order.

**Inputs, in the order they were walked:**

1. **2026-08-06 Bill working session** — transcript findings in
   `~/Desktop/Transcripts/MHMW/processed/Bill-8-6-2026.md`; submittal-system detail
   in [`procore-decommission-plan.md`](procore-decommission-plan.md).
2. **Daniel's notes, 2026-08-04 and 2026-08-06** — items not in any transcript.
3. **[`feature-catalog.md`](feature-catalog.md)** — everything previously ranked;
   added to and collapsed here (see §7).
4. **Clarifying decisions**, resolved 2026-08-06 and recorded inline.

Bill's written spec is
`MHMW_Brain_Procore_Decommission_Submittal_System_Developer_Handoff.md` — his
deliverable, not a repo artifact.

**Effort:** S = under a day · M = 2–4 days · L = 1–2 weeks · XL = 3+ weeks.

---

## 1. The forcing function

**The Procore contract ends in October.** Roughly **eight weeks** from this
document. Bill drew the boundary himself, twice:

> *"brain projects, brain submittal handling, and ball-in-court workflow is the
> absolute core need to have before October so you don't have to re-sign with
> Procore."* — *"Absolutely."* [L802–808]
>
> *"jobs, a job silo, and just a submittal piece. The rest of it is great
> accessories but not terribly important."* [L810–811]

He also closed the catalog's last open question before it was asked — *"the ball
in the court workflows?" — "Yeah." — "Priority one?" — "Yeah."* [L30–35].

**Workstream 1 outranks everything unshipped.** Workstreams 2–4 are real work with
real value and none of them are allowed to consume the October window.

**What we do not lose in October:** invited-user access to customers' Procore
survives [L811–818], so current drawing sets stay reachable through the GC's
environment — which is where the crew already goes. That is why plan-document
hosting is off the critical path.

---

## 1b. Master work table

Every open item in one place. Detail lives in the workstream sections below.
**Effort midpoints used for totals:** S = 0.5d · M = 3d · L = 7.5d · XL = 15d.

### Workstream 0 — Preconditions

| ID | Item | Effort | Depends on | Status |
|---|---|---|---|---|
| **K4** | Backups — Postgres + binary disk | S–M | — | 🔴 **Not started.** Tier 0 since 7/22; runbook unmerged |
| **K3** | Object storage migration + cost numbers for Bill | L | — | Not started. Size generously |
| **N4** | Two-calendar business-day fix + 26-call-site audit | M | — | Not started. Gates E1–E3 |
| | | **~12.5 d** | | |

### Workstream 1 — Procore exit (October)

| ID | Item | Effort | Depends on | Status |
|---|---|---|---|---|
| **P1** | Extend `Submittals` — contract_scope_id, parent_id, phase, state, source | M | — | Not started. **No new table** |
| **P0** | Project origination — Contract Scopes + context doc + must-check notes | M | P1 | Not started |
| **P2** | Intelligent workflow building — templates, instances, 5 responses | L | P1 | Not started. **Blocked on Bill's template export** |
| **P3** | Carmen review as a workflow step | M | P2, C3 | Not started |
| **P4** | Tree of Life — sub-GC → N DRRs, PM-created, pre-filled | M | P1, P2 | Not started |
| **P5** | FC Separator / Phaser — 1 fab + N install releases | M–L | P4 | Not started. **Design against 500-998** |
| **P6** | Distribution — cover sheet + PDF, sent from Carmen | M | P2 | Not started |
| **P7** | Returned submittal ingestion via Carmen mailbox | M | P2 | Not started. Mail path already exists |
| **P8** | Aging / outstanding view — status + timer | S–M | P2, D1 | Not started |
| **P10** | Backfill `phase` + `source` on 3,892 legacy rows | S | P1 | Not started. **Shrank from "unscopeable"** |
| **C3** | Universal PDF tool — absorbs the revision stack (P9) | L | — | Not started. **Promoted onto the critical path** |
| **D1** | Projects page — container for P8 + the submittal section | L | K2 | In progress (`feature/updated-projects`) |
| | | **~48 d** | | |

### Workstream 2 — Money

| ID | Item | Effort | Depends on | Status |
|---|---|---|---|---|
| **N1** | Release tags — Contracted / Change Order / MHMW Cost | S–M | — | Not started. Ships nullable first |
| **N10** | Bulk edit on the job log | M | N1 | Not started. Backfills N1; useful beyond it |
| **N2** | Billing spine v1 — Excel ingest at FC conversion | M | P5 | Not started. **Bill owes a sample** |
| **N2b** | Billing stages → invoicing tab | M | N1, N2 | Not started |
| **J1** | Photos at paint complete as an invoicing gate | S | N9 | Not started. **Un-dropped** |
| **A2** | Change orders — auto-ingest from email | M | — | **Blocked on Bill** since 7/22 |
| **I4** | Installer ready-for-invoicing | ? | I3, N2b | Deferred |
| | | **~14.5 d** | | |

### Workstream 3 — Daily use

| ID | Item | Effort | Depends on | Status |
|---|---|---|---|---|
| **BUG-1** | FC / Procore link graying on the job log | M | — | **Fixed** 2026-08-06 — paginate FC submittals; detail refetch + fallback after FC update; retry empty URL / 30d lookback / active filter |
| **BUG-2** | Ball-in-court uncheck 1 → 0 does nothing | S | — | **Fixed** 2026-08-06 — order `0` clears to NULL (was rejected FE+BE) |
| **BUG-3** | Release-number duplicate — confirm with David/Dalton | S | — | **Fixed** 2026-08-06 — uniqueness is (job, release, job_name); job # wrap allows 410-108 Alta after 410-108 Columbine |
| **BUG-4** | Monday-morning drag-and-drop drop | S | — | **Dropped** 2026-08-06 |
| **BUG-5** | Stage-change hours reaching the fab side — verify only | S | — | **Verified + fixed** 2026-08-06 — pipeline OK; KPI modifiers incomplete vs Banana Code (Weld Complete etc. stayed 100%); aligned FE+BE+hours_summary to `STAGE_HOUR_PERCENTAGES` |
| **BUG-6** | Row 164 — Nov 2025 outlier still in the DWL | S | — | **Dropped** 2026-08-06 (data, not code) |
| **DP** | Drafter edit permissions, `job` → `released` | S | — | Agreed and widened by Bill |
| **N6** | Ship ↔ Install 'Break' button | S | — | Clean and small |
| **N5** | Ship-complete date cascade re-anchor | S | — | Extract date logic from the complete-zone cascade |
| **N7** | Job log modal merge + redesign | M | — | **In flight, uncommitted** |
| **N9** | Photo watermark + GPS — needs Pillow + pillow-heif | M | — | Capture standard settled. **§10.3 open** |
| **H1** | Polish sweep — rolling calendar, full-screen modals, metrics load | M | N7 | Not started |
| | | **~14.5 d** | | |

### Workstream 4 — Carmen

| ID | Item | Effort | Depends on | Status |
|---|---|---|---|---|
| **N8** | Carmen admin reporting — EOS metrics | M | — | **Bill has the metrics list; needs walking** |
| **C5 + K1** | Accept into knowledge base + learning substrate | M | C3 | K1 decision due before C5 |
| **C10** | Carmen runs Brain actions | ? | N8 | N8's second phase |
| **C2** | Parts + hardware list | ? | — | Experimental track |
| | | **~6 d** | | |

### Parked — real work, not October

**D2** personal page · **D4** timeline view · **A3** punch list · **A4** lookahead
upload + markup · **F1** meeting extraction bands · **E1–E3** tee-time (behind N4)
· **K2** grid engine · **L1** styling v3 · **I1** OCIP remainder *(argued against
cutting — it has a compliance failure behind it)*

---

### ⚠ Does it fit? No — and the table is what shows it

| | Working days | Weeks @ 5d |
|---|---|---|
| Workstream 0 | ~12.5 | 2.5 |
| Workstream 1 | ~48 | 9.6 |
| **October-critical total** | **~60.5** | **~12** |
| **Window available** | **40** | **8** |
| Workstreams 2–4 (not October) | ~35 | 7 |

**The October block is roughly 12 weeks of work in an 8-week window.** Prior
estimates in this document said "6–7 weeks, tight but workable" — that was a feel,
not arithmetic, and the arithmetic does not support it. Roughly **four weeks has to
come out of Workstream 1**, or the date moves.

**Recommended cut — what genuinely stops us re-signing with Procore:**

| Keep | Why |
|---|---|
| P1, P0, P2, P4, P7, P10 | The record, the workflow, DRR creation, and a way for returns to land. Without any one of these there is no system |
| **C3 narrow** — revision viewer only, not the universal tool | Meets the need; the universal-tool brainstorm moves after October |
| **D1 minimal** — submittal tab only | Bill named "brain projects," but a container is enough |
| FC conversion + release into the job log | The hand-off to everything that already works |

**≈ 29 days ≈ 6 weeks.** With Workstream 0 that is ~8.5 weeks — still tight, but
real rather than aspirational.

**Deferred past October, each because a manual process exists and works today:**

| Defer | Manual today |
|---|---|
| **P5 FC Separator** | Colton's copy-paste-delete ritual |
| **P6 Distribution** | Download, find the file, email it |
| **P8 Aging view** | Nobody has it now either |
| **P3 Carmen review step** | The review can be run manually; this is the value-add, not the replacement |
| **C3 full / D1 full** | Narrow versions ship instead |

**This needs Bill's agreement, not just ours.** He should choose which of these he
loses rather than discovering in week seven that four of them didn't make it.

---

## 2. Workstream 0 — Preconditions

Not features. Everything below sits on these.

| ID | Item | Effort | Note |
|---|---|---|---|
| **K4** | **Backups** | S–M | 🔴 Tier 0 since 2026-07-22, still nothing enabled. A runbook sits unmerged on `claude/render-backup-data-architecture-vlizsr`. **October is what converts this from a risk into a certainty** — the Brain becomes the system of record for submittals and drawings, and neither Postgres nor the binary disk is recoverable today |
| **K3** | **Object storage + cost numbers** | L | Every binary is on one Render disk. Bill asked for numbers on the record [L662–666]. Procore's document history does not fit that shape. Archival policy agreed in the meeting: closed projects keep metadata + a text record, drawing files get dropped [L666–683]. **Size generously** — the retention posture decided 2026-08-06 is *"handle as much as possible and slide irrelevant data out as those things become more clear,"* so prune later rather than filter on the way in |
| **N4** | **Two-calendar business-day fix** | M | See below |

### N4 — the two calendars

**MHMW runs two working calendars and the code knows about neither.**

| Calendar | Departments | Days |
|---|---|---|
| **Shop** | fabrication, **paint** | **Mon–Thu, 4×10s. Permanent.** |
| **Field** | ship, install | Mon–Fri |

Drafting and admin follow Mon–Fri unless corrected.

There is **one** business-day helper — `add_business_days` /
`calculate_business_days_before` / `calculate_business_days_after` in
`app/trello/utils.py:257` — it is hardcoded Mon–Fri, and it has **26 call sites**.
Everything downstream of a business-day count is computed on a calendar that
matches neither department: `comp_eta`, the drafting deadline
(`start_install − 15 biz days`), ship-date auto-fill, `app/brain/lookahead/
schedule_builder.py`, and the tee-time projection math.

Surfaced as *"lookahead schedule dates are wrong"* [8/4 notes]. It is not a
lookahead bug.

**Work:** add a calendar parameter to the helper, then audit all 26 call sites and
decide which calendar each one wants. The audit is the job, not the helper.

**Note:** the measured ~400 hrs/wk fab throughput is already 4-day-aware
(100/day × 4) and does **not** need re-deriving. N4 affects the projection math
that spreads that capacity across dates, not the capacity figure.

**Sequencing:** N4 lands **before** E1/E2/E3 (tee-time, stage weights, capacity
hygiene). Calibrating on the wrong week means calibrating twice.

---

## 3. Workstream 1 — Procore exit · **October**

Full model, slice detail, and the migration risk live in
[`procore-decommission-plan.md`](procore-decommission-plan.md). This is the
feature inventory.

### The structure, settled 2026-08-06

```
Project
 └── Contract Scope              one discrete package of work sold
      └── Submittal (sub-GC)     ← the root; one record, many revisions
           ├── DRR ── 1:1 ── FC ── 1:N ── Release(s)   ← only via the FC Separator
           ├── DRR ── 1:1 ── FC ── 1:1 ── Release
           └── DRR ── 1:1 ── FC ── 1:1 ── Release
```

**"Contract Scope" is the final term.** Singular *Contract*. Never Spec Section,
Scope Breakdown, or CSI language [L990–1004]. **DRR→FC is 1:1, enforced** — Bill
rejected one DRR feeding several FCs outright [L1398–1420]. **FC is terminal for
review** [L403–406]. **As-Built is a version series on the released FC**, not a new
record type [L48–52].

### Items

| ID | Item | Effort |
|---|---|---|
| **P0** | **Project Origination** — project creation sets up Contract Scopes and takes a **context document** (see below). Absorbs catalog **A5** and note **N3** | M |
| **P1** | Contract Scope + native submittal record | M |
| **P2** | **Intelligent workflow building** — the BIC engine | L |
| **P3** | Carmen review as a workflow step; entry point is the response | M |
| **P4** | Tree of Life — sub-GC → N DRRs, PM-created, pre-filled from the parent | M |
| **P5** | **FC Separator / Phaser** — DRR → FC → 1 fab release + N install releases | M–L |
| **P6** | Distribution package — cover sheet + PDF, sent from Carmen on-behalf-of, 2-week follow-up | M |
| **P7** | Returned submittal ingestion via the Carmen mailbox | M |
| **P8** | Aging / outstanding view, siloed by our phases — **status + timer**, not a real Carmen queue | S–M |
| **P9** | Revision stack + obsolete watermark + overlay compare — **built inside C3** | — |
| **P10** | ~~Legacy Procore submittal migration~~ — **mostly dissolved, see below** | S |
| **C3** | **Universal PDF tool** — promoted from Tier 2 into the critical path | L |
| **D1** | Projects page — the container for P8 and the submittal section | L |

### P0 — Project Origination

**The context document and the must-check notes are one document**, uploaded at
project creation (Claude-Projects style). It carries project context *and* the
must-haves-to-verify Bill asked for right after telling the intumescent-paint
story [L1036–1040].

**This is the cheap version of Mission Brief.** Bill pushed Mission Brief to phase
three [L1019–1020] because it needs estimate parsing, drawing clips, and
historical retrieval. A manual context upload gets most of the drafter-facing
value now, and gives the estimate-derived version somewhere to land later.

### P2 — Intelligent workflow building

Bill's phrase, coined live [L289–299]. **The reviewer's response mutates the
workflow.** Today in Procore he has to hand-append himself as a ninth step to see
a revision [L246–256].

| Response | Behavior |
|---|---|
| **Approved** | → drafter, may advance to the next phase. No Carmen review |
| **Approved as Noted** | → drafter addresses notes → **Carmen verifies they landed** → clears = release, fails = re-notify the drafter |
| **Revise & Resubmit** | all approvers finish → back to drafter → **auto re-add every approver**. Loops indefinitely |
| **Review Skipped** | **one reviewer clears another who is slow or away.** Records who clicked and on whose behalf; keeps the skipped person notified |
| **Void** | closes the record out |

**Five responses, not six.** *Rejected* is dropped — it and *Void* do the same
thing to the record, and offering both only makes people wonder which they mean.
Confirmed 2026-08-06; Bill was already lukewarm on it: *"not necessarily
rejected… it would close one out and just leave it as voided"* [L390–393].

Plus canned responses and a freeform box. Anyone insertable at any point
(*"Louis needs to see this"*); **Carmen suggests insertions**; templates key on
**project × phase**; the drafter runs Carmen first as their own baseline so
self-fixable problems never reach a PM; a review already run upstream is
**referenced, not re-run**.

All Procore material/order statuses are **dead** — the job log and email orders
cover that now [L206–216].

**Surface:** the Drafting Work Load's **"Procore Status" dropdown becomes the
intelligent-workflow actions dropdown** [L1141–1161]. That is the drafter's daily
surface. Touchpoints: `DraftingWorkLoad.jsx`, `SubmittalRow.jsx`,
`SubmittalCard.jsx`, `useFilters.js`, `transformers.js`, over
`app/brain/drafting_work_load/`.

### P5 — FC Separator

The only sanctioned FC → many-releases path [L1430–1524]. Produces **one fab-only
release** (all fab hours, zero install, stops at welded QC → paint) and **N install
releases** (zero fab, hours apportioned). **Location comes from the description;
quantity drives the hours** — *"there's a thousand hours and a thousand pieces, we
have 200 here, there's 200 hours."*

Replaces a manual copy-paste-delete ritual: Colton builds one release with
everything, copies it, deletes the install portion for the fab one, then makes N
more copies and edits quantities [L1451–1454].

**Design against 500-998** — Bill committed to trigger us when it goes to FC
[L1488–1491]. Do not finalize the UX before that lands.

### FC is immutable

**Resolved 2026-08-06.** There is no such thing as a revision to an FC. Once a
drawing is FC it is frozen — which is what Bill was describing when he said
*"once it's FC, we don't review it anymore"* [L403–406].

**Post-FC changes are as-builts**, and they are already handled by the existing
**job log PDF modal markup** feature. This confirms the transcript reading that
As-Built is a version series rather than a new record type [L48–52], and it
closes the "what happens to a partly-released FC when a revision lands" question
by removing the case.

**It also reinforces collapse ②** (§7). The as-built path already lives in the
job log markup stack; the submittal revision stack must be the same tool, not a
second one.

### P10 — the migration, and why it mostly went away

**Two decisions on 2026-08-06 collapsed what was the plan's largest unscoped
risk.**

**① `Submittals` *is* the native record — extend it, don't replace it.** No new
`BrainSubmittal` table. The existing model gains `contract_scope_id`,
`parent_id`, `phase`, `state`, and a `source` discriminator (Procore vs Brain).

The consequence is large: **the 3,892 legacy rows need no migration at all.**
They are already in our database from months of webhook sync. They become rows
with a null `parent_id` and a `phase` derived from the existing `type`.
Everything downstream — DWL filtering, Rel assignment, `start_install`,
`linked_release_id` — keeps working untouched, because the table it reads from
never moved.

**② The cut-over gate is the project, not the submittal.** New projects
originate in the Brain; projects already running stay where they are. That is a
far cleaner line than a per-submittal cut-point, and **660 Fox Hill fits it
exactly** — it is a new project, which is why it works as the pilot.

**What remains is small:** a backfill script that sets `phase` and `source` on
existing rows, and a decision about what the Brain shows for Procore-originated
submittals after October.

**Reconstructing legacy trees is explicitly deferred** — *"cross that bridge when
we get there."* Legacy DRR/GC/FC stay as three unlinked records
(`submittal-id-coherence-audit.md`). The native model prevents the problem going
forward; it does not retroactively fix it, and it does not need to.

**One question this opens** — see §10.1: if the gate is *new projects only*, what
happens to projects still mid-flight in Procore when the subscription lapses?
Since we already hold their rows, this is probably "the Brain becomes the UI for
records it already has" rather than a migration — but it needs stating.

---

## 4. Workstream 2 — Money

One thread across both meetings, sequenced. **Not October-critical** — it is the
natural release valve if Workstream 1 needs the room.

| ID | Item | Effort |
|---|---|---|
| **N1** | **Release tags** — `Contracted` / `Change Order` / `MHMW Cost`, required, drives invoicing filters | S–M |
| **N2** | **Billing spine v1** — Excel ingest at FC conversion | M |
| **J1** | Photos at paint complete as an invoicing gate — **un-dropped** | S |
| **N2b** | Billing stages → invoicing tab | M |
| **A2** | Change orders — auto-ingest from email | M |
| **I4** | Installer ready-for-invoicing | later |

### N1 — release tags

The classifier that makes the invoicing tab work. The 8/6 conversation described
*how much* is invoiceable per stage; the tag says *whether, and against what*.
Contracted bills against the SOV, Change Order against the CO, MHMW Cost against
nobody.

**Ship it without waiting on A2.** The `Change Order` tag is useful as a marker
before COs exist as records — *"we will grow into COs."* The exact meaning of
**MHMW Cost** is with the client.

**Backfill happens through a bulk-edit function on the job log**, not a migration
default — decided 2026-08-06. That is a **new item worth more than this one use**:
bulk edit is generally useful and there is currently no way to change a field
across many releases at once.

| ID | Item | Effort |
|---|---|---|
| **N10** | **Bulk edit on the job log** — multi-select rows, set a field across them. Backfills N1; useful well beyond it | M |

Sequencing: N1 ships with the column nullable, N10 backfills it, and only then
does the field become required. That avoids a required column with no way to
populate it.

### N2 — where the Excel enters, resolved

The transcript is explicit [L637–647]:

> *"So DRR to FC, drop in the final PDF pack, work with the Excel in the short
> term — take this Excel, drop it in as well. That's how we go from FC to
> released. And then on the invoicing tab is where we see this breakdown of data
> in the short term… Eventually, this will be information in the admin view
> project tab, and information will be spliced out per department."*

- **Entry point: the FC conversion modal** — the same moment the drafter drops the
  final PDF pack. Not the project page.
- **Display: the invoicing tab now**, the admin project tab later, spliced per
  department.
- **Store the file and extract the data.** He starts at *"just this data, not the
  sheet"* [L502] and softens once he sees 340 KB [L648–653].
- **Back-end only** — nothing renders on the submittal [L506–508].

**Excel is v1 of this integration.** Quote/estimate integration — SOV generation,
department budgets flowing natively, and the decrement-against-contract-value
check that catches double-selling a stair [L478–487] — is **v2**, and it is what
makes the whole thing more than data entry.

### Billing stages [L607–631]

| Gate | Invoiceable |
|---|---|
| Material ordered | 100% material |
| Fab complete | 100% fab |
| Paint complete | 100% paint — no split; **photos required** |
| Install % | equipment **and** install labor at the install percentage |

Budget vs actual per department reconciles to the original quote value so variance
in either direction doesn't create an accounting error [L550–560].

**J1 un-drops here.** It was cut as *"irrelevant basically"* on 7/22. Paint
invoicing requires photographs [L613–616], which makes it a gate, not a
nice-to-have — and N9 (below) is what makes those photos usable.

---

## 5. Workstream 3 — Daily use

The stuff people touch every day. Cheap, unblocked, and currently costing time.

### The bug pile

Kept as its own pile rather than folded into a polish sweep. Items may be elevated
out of it at any point.

| Item | Source |
|---|---|
| **FC / Procore link graying on the job log** — gray = missing `viewer_url`. **Fixed** 2026-08-06: paginated submittal fetch; Final PDF Pack detail refetch + workflow fallback after FC updates; retry worker treats `''` as missing, 30d lookback, `active_releases_filter`. Number vs name click difference is intentional (name → modal, # → drawing/Procore) | [L1334–1371] |
| **Ball-in-court uncheck 1 → 0 does nothing** — Bill self-noted it live. **Fixed** 2026-08-06: ORDER # `0` / uncheck maps to NULL (unordered); previously FE and BE rejected 0 so the cell appeared to do nothing | [L1064–1068] |
| **Release-number duplicate** — uniqueness is **(job #, release #, project name)**. Same project (incl. archived) cannot re-issue; same digits under a different name after job-# wrap is allowed. Migration: `releases_unique_job_release_name.py` | [L1051–1095] |
| ~~Monday-morning drag-and-drop drop~~ — **Dropped** 2026-08-06 | [L1376–1378] |
| Stage-change hours → fab total — **Verified**: stage write works; remaining fab is computed (not stored). **Gap fixed**: sparse FAB_MODIFIER/SQL ignored mid-fab stages so totals did not drop on those steps. Now derived from Banana Code matrix. SchedulingConfig still uses separate legacy map (scheduling only) | [L1322–1330] |
| ~~Row 164 — a November 2025 outlier still in the DWL~~ — **Dropped** 2026-08-06 (data, not code) | [L1057–1090] |

### Features

| ID | Item | Effort |
|---|---|---|
| **N7** | **Job log modal merge + redesign** — **in flight, uncommitted** on the `feature/unified-release-modal` worktree. Soft dependency for punch-list and T&M entry points | M |
| **N9** | **Photo watermark + GPS** — new 2026-08-06 | M |
| **N10** | **Bulk edit on the job log** — see Workstream 2 | M |
| **N5** | **Ship-complete date cascade** | S |
| **N6** | **Ship ↔ Install 'Break' button** | S |
| **DP** | **Drafter edit permissions**, `job` → `released` columns | S |
| **H1** | Polish sweep — rolling calendar, full-screen modals, metrics load times | M |

### N9 — photo watermark

Client ask, 2026-08-06: stamp uploaded job-log photos with **date, who took it,
current stage**, plus **GPS coordinates**.

**Three of the four fields already exist.** `ReleasePhoto` carries
`uploaded_at`, `uploaded_by_user_id`, and `stage` (`app/models.py:1053`). They
are simply not burned onto the image. Only GPS is a new column.

**But there is no image library in this codebase.** No Pillow, no piexif, no HEIC
decoder — `save_photo` writes raw bytes and nothing ever decodes an image
(`app/brain/job_log/features/photos/`). Watermarking means adding an image
pipeline, plus **`pillow-heif`**: the upload path accepts HEIC by ftyp sniffing
and stores it undecoded, and iPads shoot HEIC by default. That is why this is an
**M, not an S** — the metadata is free, the rendering is not.

- **Keep the original clean, generate a stamped derivative.** Never burn over the
  only copy.
- **`Projects.geofence_geojson` already does point-in-polygon** via PostGIS in
  `drafting_work_load/service.py:682`, so *"was this photo actually taken on
  site"* is a query with a working precedent — not new infrastructure.

#### GPS source — tested 2026-08-06, and the answer is "not from EXIF"

A real field photo was parsed directly (`test-location-datea.jpg`, Pixel 6a,
captured 2026-08-04):

```
APP1 EXIF segment: 359 bytes
IFD0: Make=Google  Model=Pixel 6a  DateTime=2026:08:04 15:40:53
>>> NO GPS IFD POINTER (0x8825)
```

**EXIF was not stripped wholesale — make, model and capture time all survived.
GPS specifically is absent.** The 359-byte APP1 block is the tell: a native Pixel
camera JPEG carries a far larger EXIF block with maker notes, so this file was
**re-encoded in transit** and that pass dropped the GPS IFD while keeping the
basic tags. Had location merely been off at capture, a fuller native block would
be expected.

**Conclusion: a real photo from a real field device reached the business with no
usable location. Do not build on EXIF GPS.**

Two limits on the test — the device was **Android, not an iPad**, and the file came
off a desktop copy rather than through the Brain's `<input type="file">` →
`save_photo` path. Neither changes the recommendation; both mean a sample taken
from production photo storage would still be worth running.

**Therefore:**

- **Browser geolocation at upload is the primary source.** Captured at a moment we
  control, one permission prompt, and its weakness — truthful only when uploading
  on site — is exactly what the geofence check exists to detect.
- **EXIF GPS is an opportunistic bonus**, read when present, never depended on.
- **Record which source each coordinate came from**, and mark a photo *verified on
  site* via the geofence rather than trusting the coordinate blindly.
- **Take the capture date from EXIF when present, falling back to `uploaded_at`.**
  The client asked to stamp *the date*, and **capture date ≠ upload date** — a
  photo taken Thursday afternoon and uploaded Friday morning must say Thursday.
  `DateTime` survives the transit that kills GPS, so this one is reliable.

#### Capture standard — devices, settings, and the one purchase decision

**The fleet is personal phones plus company-owned iPads** (confirmed 2026-08-06).

> ### ✅ Hardware requirement already met — and it is a **standing spec**
>
> **The company iPads have cell service** (confirmed 2026-08-06), so they carry a
> real GNSS receiver and this feature works on them.
>
> **Keep this as a purchasing requirement, not a resolved question.** Wi-Fi-only
> iPads have **no GNSS receiver at all** — they geolocate by triangulating known
> Wi-Fi networks, which on a job site returns nothing or something wrong by miles,
> and **no software fixes it.** Any future tablet added to the field fleet must be
> a cellular model. The GNSS chip works even with no SIM and no active plan; only
> the assistance data (faster first fix) wants a network.
>
> **Bonus from the existing plans:** cellular iPads can upload *from the job site*
> without hunting for Wi-Fi, which is the exact behavior the training item below
> depends on.

**The principle: don't recover location from the file — capture position and image
in the same interaction.** `<input type="file" accept="image/*"
capture="environment">` opens the camera directly; fire
`getCurrentPosition({enableHighAccuracy: true})` in the same handler. "Taken here,
now" then holds by construction rather than by inference.

Cost to weigh: in-app capture loses the native camera's review-and-retake, and a
failed upload on poor site signal can lose the photo. **Queue locally and retry**
rather than uploading synchronously.

**Three provenance states, all of which will occur in a mixed fleet:**

| State | Meaning |
|---|---|
| **Captured on site** | in-app capture, geolocation inside the geofence |
| **Position at upload** | library upload + geolocation — where the *uploader* was, not the photo |
| **No location** | permission denied, or no fix — indoors, between structures, or a device without GNSS |

The third state must exist and must be visible. Silently degrading to a
plausible-looking wrong coordinate is worse than reporting nothing.

**Personal phones — consent posture.** `getCurrentPosition` on an explicit user
gesture only; **never request background or persistent location.** Not because it
wouldn't work, but because the first person to see an "always allow" prompt on
their own phone will decline and tell everyone else to. We are stamping a photo,
not tracking a person, and the permission model should visibly match that claim.

**A location denial must never block the upload.** If v1 refuses a photo without
coordinates, adoption dies in week one. Home-screen install matters more on phones
than tablets — it persists the permission instead of re-prompting, and repeated
prompts are what turn an *Allow* into a *Deny*.

**Company iPads.** MDM can enforce Location Services, pre-grant the browser's
location permission, and push the home-screen install. Also set Camera → Formats →
**Most Compatible** (JPEG not HEIC) — a nicety on managed devices, **not** a way to
avoid the HEIC decoder: personal iPhones shoot HEIC and their settings are not
ours to change, so **`pillow-heif` is required regardless.**

**Training — one behavior, higher leverage than any of the above:** *upload from
the job site, at the time of the work.* It makes geolocation truthful, the stage
stamp accurate, and Katie's evidence identifiable while it still is.

**Accuracy expectation, to be set with the client before this ships.** Phone and
cellular-tablet GPS outdoors is **5–20 m**. That reliably answers *which job site*
— geofence polygons are large. It does **not** answer *which building* or *which
bay*, and it degrades badly indoors and between tall structures. **Pitch it as site
verification, not position tracking.** Sold as the latter, it loses credibility the
first time someone checks a coordinate against where they know they stood.

> **⚠ Open — shared-tablet attribution.** The client asked to stamp *who took the
> photo*. That comes from the logged-in Brain user, not the device. **If crew share
> one iPad under a generic login, every photo carries the same name and the field
> is worthless** — which is exactly the metadata Katie needs. Decide before
> building the watermark: individual logins on shared tablets, a "who is this"
> picker at capture, or tablet photos carrying no attribution while phone photos
> do. See §10.3.

**This is what makes J1 work.** Katie's 7/22 problem was *"I don't know what it is
most of the time, what it's supposed to look like, where it's at."* A stamped
photo is self-describing, which is exactly what the invoicing pile needs.

### N5 — ship-complete date cascade

The complete-zone cascade keeps its `job_comp X → install stage` behavior. **The
date manipulation is extracted out of it and re-anchored to the ship-complete
stage**, so it fires sooner: drop ASAP and the red color, drop green/yellow too,
and set the date to the ship-complete event date. Touches
`neutralize_install_date_cascade`.

---

## 6. Workstream 4 — Carmen

| ID | Item | Effort |
|---|---|---|
| **N8** | **Carmen admin reporting — EOS metrics** | M |
| **C10** | Carmen runs Brain actions — N8's second phase | later |
| **C2** | Parts + hardware list — experimental track | ? |
| **C5 + K1** | Accept into knowledge base + the learning substrate | M |

### N8 — Carmen admin reporting

Started as *"David's fab hours report."* It is not a report page — it is a
**Carmen tool**: *"Hey Carmen, pull my EOS data for last week,"* and she gets the
answer out of the data we already track.

**Method:** take the EOS metrics the client actually tracks, walk them one by one,
identify which are derivable from current data, and build the tool against those.
The gaps become their own findings.

**This absorbs C10 and makes it shippable.** C10 ("Carmen runs Brain actions") has
been deferred with no trigger because it implies a leash conversation. N8 is the
same capability **read-only** — pull, summarize, report. That is exactly the
progressive path Bill described on 7/22: *"then progressively letting the leash
off as tasks prove repeatable."* Ships on `app/brain/carmen_chat/tools.py`, which
already does tool-calling.

---

## 7. What was added and what collapsed

Recorded so these decisions don't get re-litigated from memory.

### Off the board

**Shipped:** A1 T&M · C1 note field · C8 markup rotation · C9 Carmen rename ·
G1 desktop notifications · I1 subs view v1 · I3 external access v1 · E4 lookahead
builder
**Dissolved:** B3 soft-link — the native model makes it a foreign key
**Dropped, staying dropped:** J2 Dencol→Carmen · J3 drafting timeline
**Un-dropped:** **J1** — paint invoicing requires photos, so it's a gate

### Collapses

| # | Collapse | Why |
|---|---|---|
| ① | **A5 + N3 + P1 + must-check notes → P0 Project Origination** | A5 had been deferred with no shape since 7/22. It now has one, and the context doc + must-check notes are **one document**. The cheap version of Mission Brief lives here |
| ② | **P9 revision stack folds into C3** | Bill on 7/22: *"this needs to now become our profile markup system."* Building the submittal viewer separately ships two markup stacks and merges them later at full cost. **Cost: C3 is promoted from Tier 2 into the October path** |
| ③ | **N8 absorbs C10** | Same capability, read-only first. Gives C10 a trigger it never had |
| ④ | **N4 becomes a precondition of E1/E2/E3** | The projection math runs on a Mon–Fri week for a Mon–Thu shop |
| ⑤ | **N1 + N2 + J1 + billing stages + invoicing tab → Workstream 2** | One thread across both meetings. **A2 is a dependency, not a gate** — N1 ships with the CO tag ahead of CO records |
| ⑥ | **H1 splits** | Bugs are not polish. N7 is too big for a sweep |

### Parked — real, not October

**D2** personal page · **D4** timeline view · **A3** punch list · **A4** lookahead
upload + markup · **F1** meeting extraction bands · **E1–E3** tee-time (behind N4)
· **K2** grid engine (now serving D1 and the invoicing tab) · **L1 styling v3** —
the 7/22 sequencing conflict now has an unambiguous answer: **not before October**

**Argued against cutting:** **I1's OCIP remainder.** Small and unglamorous, with an
actual compliance failure behind it.

---

## 8. Sequencing

| When | What |
|---|---|
| **This week** | K4 backups · K3 storage numbers for Bill · the bug pile · drafter permissions · N6 |
| **Weeks 1–3** | P0/P1/P2 the spine — **extending `Submittals`, no new table** · N4 |
| **Weeks 3–4** | C3 + P9 revisions and Carmen review · N5 · N9 |
| **Weeks 4–6** | P6 distribution · P7 returned ingestion · P8 aging |
| **Weeks 6–7** | P4 Tree of Life · FC conversion · **P5 Separator**, designed against 500-998 |
| **Weeks 7–8, slippable** | N1 → N2 → billing stages → invoicing tab |
| **Alongside** | N7 modal merge · N8 Carmen reporting |

**Pilot discipline matters more than the schedule.** **660 Fox Hill** runs in
parallel with Procore from the first slice [L1041–1049], so that when the contract
lapses the system has been carrying a real project for weeks rather than being
switched on the day the alternative disappears. 645 is the backup pilot.

**Honest read — see §1b for the arithmetic.** Workstream 1 as fully scoped is
**~12 weeks against an 8-week window.** The sequence above describes the whole
thing; **the version that actually fits is the reduced scope in §1b**, which keeps
the record, the workflow, DRR creation, and returned-submittal ingestion, and
defers the FC Separator, distribution, the aging view, and the full C3/D1 builds
to after October.

Two decisions on 2026-08-06 did make this materially better — extending
`Submittals` rather than replacing it, and gating cut-over at the project rather
than the submittal, removed the one item that could not be sized, and removed it
by deciding rather than deferring. That is real progress. It is not four weeks of
progress.

Two conditions still carry the plan. **Workstream 0 happens this week** rather
than opportunistically; backups have been Tier 0 for over two weeks with nothing
enabled, and October is what converts that exposure from a risk into a certainty.
And **Workstream 2 is allowed to slip** — it is the release valve, and nothing in
it stops us leaving Procore.

The remaining unknowns are §10.1 — what happens to projects still running in
Procore when the subscription lapses — and **whether Bill accepts the reduced
October scope.** Both are his calls, and the second should be put to him early
rather than discovered late.

---

## 9. Owed by Bill

| Owed | Blocks | Since |
|---|---|---|
| **Procore workflow template export / screenshots** (the 8-step, per-PM list) | P2 — we are replicating them | 8/6 |
| **Trigger on 500-998 going to FC** | P5 design | 8/6, committed |
| **Sample release Excel (billing sheet)** | N2 | 8/6 |
| **Carmen "best project engineer" chat doc** | Workstream 4 framing | 8/6 |
| **Confirmation that Mission Brief is out of October scope** | It contradicts his own written spec — he should confirm it, not discover it | new |
| **What happens to in-flight Procore projects when the subscription lapses** | §10.1 — possibly a contract-renewal question, not a build one | new |
| **The EOS metrics list** | N8 — *in hand, needs walking* | 8/6 |
| Procore bulk-export request; customer-Procore question to his rep | P10, B1/B4 | 7/22 |
| Change order log Excel + sample CO email | A2 | 7/22 |
| Stage weight approval · Carmen avatar | E2 · C9 cosmetics | 7/22 |

---

## 10. Open questions

**Nine were asked 2026-08-06. Seven are resolved and recorded inline; the two
below are what remains, plus one the answers opened up.**

### 10.1 In-flight Procore projects at the October line — **new, unanswered**

The cut-over gate is now *new projects originate in the Brain, existing projects
stay where they are.* Clean — but the Procore subscription still lapses in
October, and some projects will be mid-flight when it does.

Three possibilities: they get pulled over at that point, the subscription is
extended read-only for a tail, or they are forced across early.

**The likely answer is cheaper than it sounds.** Because `Submittals` is the
native record and we have been syncing those rows for months, we already hold the
data. This is probably *"the Brain becomes the UI for records it already has"*
rather than a migration — but it needs deciding rather than assuming, and it is
Bill's call because it may be a contract-renewal question.

### 10.3 Shared-tablet photo attribution — **new, decide before N9 builds**

The watermark stamps *who took the photo*, sourced from the logged-in Brain user.
On a shared company iPad under a generic login, every photo carries the same name.

Three options: individual logins on shared tablets (best data, most friction in a
work-gloves-on context), a "who is this" picker at capture time (light friction,
trivially falsifiable), or accept that tablet photos carry no attribution while
phone photos do (honest, and phones will be the majority of real field capture
anyway).

Needs deciding before the watermark is built, because it changes what is rendered
onto the image.

### 10.2 What MHMW Cost means, and the tag backfill — **with the client**

Backfill mechanism is settled (N10, bulk edit). The remaining question is
semantic: is **MHMW Cost** rework, warranty, no-charge, or something else? It
determines whether those releases are excluded from invoicing entirely or tracked
as internal cost.

### Resolved 2026-08-06

| Question | Answer |
|---|---|
| Coexist or replace | **Neither — extend.** `Submittals` *is* the native record. §3 P10 |
| Cut-over rule | **New projects gate**, not per-submittal. §3 P10 |
| Archival vs operational | **Defer; retain generously**, prune as clarity comes. §2 K3 |
| GPS source for N9 | **Tested 2026-08-06: no GPS in a real field photo.** Browser geolocation is primary, EXIF opportunistic. Capture date *does* survive and should be preferred over upload date. §5 N9 |
| Review Skipped / Rejected / Void | **Review Skipped stays** (one reviewer clears another who is slow). **Rejected dropped**, Void kept. Five responses. §3 P2 |
| Carmen's ball-in-court for aging | **Defer the real queue**; ship status + timer. §3 P8 |
| Revision to a partly-released FC | **The case does not exist.** FC is immutable; post-FC changes are as-builts in the job log markup. §3 |
| Release tag backfill | **Bulk edit on the job log** (N10), not a migration default. §4 N1 |
| `feature/unified-release-modal` | **Uncommitted work in the worktree.** N7 is in flight |

---

## 11. The error this is all for

Bill's motivating story, and the clearest statement of what Carmen is for
[L1021–1035]:

A structural steel job with **intumescent (fireproofing) paint**. The submittals
were correct and everything was labeled correctly. The embeds shipped to the job
site were **primed** — red oxide — so the paint field was toggled to *primed* at
that moment. The structural package then released **inheriting primed**, and never
got the fireproofing. The crew had to fireproof on site.

> *"Which was not cheap."*
>
> *"That type of linear opportunity is we want to make sure Carmen's tracking
> that. If it's like, hey, this is supposed to be this — are we sure this is
> correct?"*

That is the argument for P0's must-check notes, for P3's verification pass, and
for why the data lineage in Workstream 1 is worth building properly rather than
quickly.

---

## Source meetings

| Date | Meeting | Findings |
|---|---|---|
| 2026-08-06 | Submittal system working session (Bill, Colton) | `~/Desktop/Transcripts/MHMW/processed/Bill-8-6-2026.md` |
| 2026-08-04 | Notes only, no transcript | Incorporated here |
| 2026-07-22 | Ops / roadmap review — the October deadline surfaces | `~/Desktop/Transcripts/MHMW/processed/Bill-7-22-2026.md` |
