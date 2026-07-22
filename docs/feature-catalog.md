# MHMW Feature Catalog — 2026-07-22 Meeting

Every feature discussed in the 2026-07-22 Bill review and the Lexi conversation,
with current codebase state, a plan, dependencies, and effort. Ranked summary at
the end.

Source findings: `~/Desktop/Transcripts/MHMW/processed/`. Meeting rollup:
[`ops-planning.md`](ops-planning.md).

**Effort:** S = under a day · M = 2–4 days · L = 1–2 weeks · XL = 3+ weeks.

> ### 🔴 Read this first
>
> **There is no backup of production.** Confirmed 2026-07-22 — neither the
> Postgres database nor the disk holding every PDF and photo. This is **K4**,
> it is scheduled for **this week**, and it outranks every feature below it.
> Nothing in this catalog is worth building if the data it operates on cannot
> be recovered.

**A note on state.** A survey of `origin/main` before writing this changed
several plans from "build" to "wire." Already on main: `app/brain/lookahead/`
(parser + crosscheck), `app/brain/pdf_review/`, `app/brain/projects/`,
`app/brain/install_schedule/`, `app/brain/metrics/`, `app/brain/material_orders/`.
Already modeled: `SunbeltRental`, `ReleasePhoto`, `BBReviewFeedback`,
`DrawingVersionComment`, `Notification`. Not on main: `app/brain/tm/` (empty
package — the real work is on `feature/tm-ingestion`).

---

## A. Data capture — the ranked list

> **Shared shape across T&M, change orders, and punch lists.** All three are
> release-anchored records with a creator, an assignee, a status, a date,
> attachments, and notes. Bill described a punch list as *"effectively a T&M
> ticket, very similar"* [L545], and Daniel confirmed the three are
> deliberately similar structures — *"can separate if needed, don't think it's
> that deep."*
>
> **Build them as sibling tables, not a polymorphic base model.** Share the
> conventions (column names, status vocabulary) and the UI layer (attachment
> component, assignee picker, status chips). Do **not** build an abstract parent
> the three then fight over — they will diverge (COs carry no photos, T&M
> carries financials later, punch lists carry completion evidence), and three
> tables that look alike are far cheaper to evolve than one that has to serve
> all three.

### A1. Time & materials — **HIGH (Bill), committed Monday 7/27**

> **Requirements confirmed with Daniel 2026-07-22.** Scope below is settled, not
> inferred from the transcript.

**Scope decisions:**

| Decision | |
|---|---|
| **Paper ticket ingestion — DROPPED** | Origination path only. Tickets are created in the app, not scanned in. |
| **Sub-facing layer — not on the Monday docket** | Deferred, not cancelled |
| **O&P / financials — nothing yet** | No rates, no pricing, no contract terms in v1 |
| **Signature — iPad canvas capture** | Not typed-name-only |

**State:** `feature/tm-ingestion`, 4 commits, ~4,700 lines, unmerged. Ships
`TMTickets.jsx`, `TMTicketFormModal.jsx`, `TMTicketAttachments.jsx`, `tmApi.js`,
three migrations, three test files, `docs/specs/tm-module-build-doc.md`.
`app/brain/tm/` on main is an empty package.

> **`docs/specs/tm-module-build-doc.md` is a long-term Brain vision document,
> not the v1 requirement set.** It describes O&P separation, contract
> integration, permission tiers, automated GC distribution, and 14-day
> follow-up — none of which are in scope here. Do not build to it.

**The branch was built for the dropped path.** `raw_extraction`,
`extract_model`, `extract_error`, `source_storage_key`, `source_filename`, the
extraction service, and `tests/test_tm_extract.py` all exist to serve paper
intake. Status defaults to `pending_review` — a review-the-extraction state.
What survives the scope cut: the `tm_tickets` table, the form modal, the
attachments component, the tickets page, and the header fields added by
`reshape_tm_tickets_p1` (location, gc_company, gc_contact_name, foreman_name,
created_by, attachments).

**So Monday is a build, not a merge** — the authorization handoff is the module,
and it is the part that doesn't exist.

**Plan:**
1. **Strip the ingestion path.** Trim the extraction columns out of
   `add_tm_tickets` rather than shipping dead schema — the migrations have not
   run anywhere yet, so this is free now and awkward later. Drop the extraction
   service and `test_tm_extract.py`.
2. **Build the authorization handoff.** Add `assigned_to`, and status states for
   seeded → shared → filled → confirmed. A PM or lead seeds the ticket, shares
   it to the person doing the work, they fill it, it returns to the originator
   to confirm. **Installers cannot self-start** — that gate is the point.
3. **Signature: iPad canvas capture.** Replace the `signature_present` boolean
   with a stored signature image (storage key) plus `signature_name` and
   `signed_at`. **Build the canvas on pointer events, not mouse events** —
   native HTML5 drag is already inert on iPad across ~10 components in this app
   for exactly this reason.
4. Rebase on main, run `pytest tests/tm/`, confirm migration order
   (create → attachments → reshape) and per-file idempotency against
   `migrations/README.md`.
5. Hand over migration commands per environment. No prod DDL from Claude.
6. Ship to a small group and collect the "this sucks / this is great" pass.

**Tripwire for later:** the sub-facing layer is safely deferred *only because
there are no financials yet*. When O&P lands, the role gate ships in the same
commit — gated at the serializer, never at the component. A sub role must never
receive rates in an API response.

**Depends on:** nothing. **Effort:** M

---

### A2. Change orders — **HIGH (Bill)**

> **Requirements confirmed with Daniel 2026-07-22.** Scope below is settled.

**v1 is email ingestion. That is the whole feature.**

| Decision | |
|---|---|
| **Capture only — the Brain does not generate the CO PDF** | It records the CO you already sent. No contract terms, no O&P math, no PDF rendering. |
| **No T&M → CO conversion yet** | The two modules stay independent in v1 |
| **No 14-day GC follow-up in v1** | Deferred to a follow-up pass |
| **Backfill from the existing Excel CO log — yes** | Bill confirmed it exists and agreed to send it (transcript L1190–1196) |

**State:** Nothing built. The ingestion machinery exists — `RawSourceRecord`,
`LakeIngestState`, `GraphSubscription`, `MicrosoftDelegatedToken` are modeled
and the bb@mhmw.com mail path already lands records. A CO is another document
type through a pipeline that already runs.

**Plan:**
1. `ChangeOrder` model: project, nullable release link, source email id, status
   (open / executed), amount, dates. Leave a nullable T&M link column for later
   even though nothing writes it in v1.
2. Ingest path: Carmen CC'd on the outbound customer email → existing mail poll
   lands a `RawSourceRecord` → classifier tags it CO → extract the PDF
   attachment and the thread. **No create button of any kind** in v1.
3. Extraction reuses the material-order extractor pattern in
   `app/brain/material_orders/` — closest working analogue, same shape of
   problem.
4. Projects-page section with an executed / open filter.
5. Backfill from Bill's Excel CO log as a one-off under `scripts/`, dry-run by
   default. Whether it can attach to a job or release depends on what columns
   the file actually has — unknown until it arrives.

**Blocked on Bill:** the CO log (Excel) and a sample CO email. Both are open
action items from the meeting; neither is on Daniel. The sample email drives the
classifier, so this cannot start without it.

**Effort:** M — smaller than originally scoped now that generation, conversion,
and follow-up are all out.

**Deferred to follow-up passes:** T&M → CO conversion · CO request PDF
generation with O&P separation · automated GC distribution · 14-day aging
chase. All four are described in `docs/specs/tm-module-build-doc.md`, which is a
long-term vision document — **do not build to it.**

---

### A3. Punch list — **MED+ (Bill)**

> **Requirements confirmed with Daniel 2026-07-22.** Scope below is settled.

| Decision | |
|---|---|
| **Internal only for v1** | Ships to MHMW employees. Does not wait on external user access (I3). |
| **PM-created for now** | Same authorization posture as T&M |
| **Informational, not a gate** | An open punch item does not block job completion or invoicing — *yet* |
| **Sibling table to T&M / CO** | Shared shape and UI, separate table. See the section note above. |

**State:** Nothing built. `ReleasePhoto` covers capture; `ChecklistItem` and
`todos_routes.py` cover the to-do half.

**Plan:**
1. `PunchListItem`: release FK, created_by, responsible_party, due date, status,
   notes. Follows A1's handoff conventions rather than inventing its own.
2. "Create punch list" button inside the release modal — rides on H2 universal
   modal.
3. Responsible party defaults to the last installer resolved from the install
   assignment; reassignable. Reassignment goes to an MHMW employee.
4. Attachments reuse `ReleasePhoto` and the board photo stack. PDF support
   exists but is rare — *"pretty rare, I think, we would ever mess with that."*
5. Completion photos close the item.
6. Lands in the assignee's list; D2 personal page makes it visible.

**Depends on:** D2 personal page (soft — without it, items are assigned but hard
to find), H2 universal modal (soft). **No longer blocked on I3** now that v1 is
internal-only. **Effort:** M

**Later:**
- **External access (I3)** extends this to subcontractor installers, who are the
  majority of its real audience. Until then the meeting's own fallback applies:
  reassign to an MHMW employee and backfill.
- **Gating.** Daniel's reaction to making an open punch item block
  ready-for-invoicing or job completion: *"great idea"* — deferred, not
  rejected. Natural pairing with I4 installer invoicing.

---

### A4. Lookahead upload + markup — **MED (Bill)**

> **Requirements partly confirmed with Daniel 2026-07-22.** The interaction
> layer is explicitly **not** settled and needs a design pass before build.

**What this feature is for, in Daniel's framing:** *"an efficient way to
cross-reference our internal dates against the schedule."* The markup exists
because **lookaheads are more general than our scope** — they don't reliably
name our work, so the PM needs to be more granular than the GC's document.

| Decision | |
|---|---|
| **Picker over drawn flags** | Preferred direction. Bill described PDF markup; Daniel: *"I do not love Bill's suggestion but it might be the best solution."* Not settled. |
| **Plus an independent add** | For releases **not listed** in the lookahead at all — the schedule won't mention them |
| **May cover submittals as well as releases** | And possibly in coherent blocks rather than one-by-one |
| **Output lands on the project page panel** | For now |
| **Four-week lookaheads only** | Full project schedules explicitly excluded — they drift too much |

**State:** **The engine is done and on main.** `app/brain/lookahead/` has
`parser.py`, `crosscheck.py`, `service.py`, and `samples/`. Validated live on
real Alta Metro data — *"nailed it."*

**Why the markup layer exists at all:** Alta Metro matched because the schedule
literally said *"Building B structural steel."* Bill named the limit himself —
*"if it said Building B exterior finishes, it's probably not going to say
guardrails."* Precise matches are the exception, not the rule.

**Plan:**
1. Upload a four-week lookahead PDF from the project page; persist file +
   parsed record, versioned per week so drift between weeks is visible.
2. Run the existing crosscheck on upload.
3. **Interaction layer — needs a design pass.** Direction: a list of parsed
   schedule lines with a release/submittal picker per line, plus an independent
   add for our scope the lookahead never mentions, possibly grouped in coherent
   blocks. Not a drawn-on-PDF markup unless the design pass says otherwise.
4. Flags become training data for next week's match — **see K1 before choosing
   where that data lives.**
5. Surface results in a project page panel.

**Depends on:** projects page (D1) for the upload surface; K1 for the learning
store. **Effort:** M for upload + crosscheck surfacing; the interaction layer is
unscoped until designed.

**Deferred:** the *covered-by* problem. The crosscheck flags a missing release
that isn't missing, because the shop combines near-identical scopes into one
record (B–D embeds became a single release). Without an acknowledgment
mechanism it re-flags every week and people stop reading it. Daniel: *"I know
this is going to take some work, so defer for now."* **This is the thing that
will erode trust in the feature if it ships without it** — revisit before wide
rollout, not after.

---

### A5. New project origination — **DEFERRED**

> **Fully deferred by Daniel 2026-07-22**, with the October context in view.
> Ranked HIGH by Bill in the meeting; not being worked now.

**State:** Nothing built. `Projects` exists but is a geofence/job-site record
linked to the job log by `job_number` string, not a foreign key — it is not a
project container.

**What it would be:** intake of contract, project schedule, estimate, and
drawings at project creation; project contacts form; spec-section generation
from the estimate. New projects going forward, no retrofit.

**Unresolved when deferred:**
- **Filing cabinet or generator?** Storing documents against a project is
  modest. *"Try and get it to create the spec section afterwards"* — reading an
  estimate and emitting structured scope items that seed submittals and releases
  — is the front of the whole pipeline. Never settled.
- **Cut-points for in-flight projects.** Bill named the *"weird, disgusting
  overlap"*: existing projects already have submittals done downstream, so
  origination must be able to stop partway. Unsolved.
- **Whether it forces the `Projects` model rework** — a real container with FKs
  to releases and submittals, i.e. the `project_id` backfill deferred on the
  projects-tab work. If so, A5 and D1 are one piece of work rather than two.

**Consequence for B2.** Bill tied origination directly to the Procore exit —
*"in order for us to get the Procore in place, we're probably going to need to
be able to get the project origination documentation in place too"* [L1548–1550].
With A5 deferred, B2 either proceeds without its stated precondition or slips
with it. **Resolve when B2 is planned**, not before.

**Effort if revived:** L

---

### A6. RFIs — **DEFERRED**

> **Deferred by Daniel 2026-07-22.** Not even a placeholder for now.

**State:** Nothing built.

**What it would be:** email-ingested RFI records, both internal (we ask the GC)
and inbound (the GC distributes to us), with a projects-page section.
Explicitly **not** pulled from Procore — most GC RFIs aren't ours and MHMW never
sees them. Bill ranked it lowest in the meeting: *"a little priority thing at
this point… it probably just needs to have a placeholder for a future
evolution."*

**The expensive part behind it — ASI drift detection.** A new drawing set lands
after the contract is signed and someone must diff old against new for changes
to our scope. MHMW's contract drawings plus our markups are the source of truth.
Bill described the target behavior: flag *"it seems like there's some changes to
the embeds in this area, you need to review,"* pull in the estimator, spin
action items. That is a drawing-diff engine, not an RFI record, and it should be
scoped separately if it's ever picked up.

**Effort if revived:** S for the record + section, L for the drift engine.

---

## B. Procore exit — October

> **Whole section deferred from Daniel's build queue 2026-07-22.** B1 and B4 are
> **Bill's** to own and drive; B2 waits on the working session and Bill's
> lifecycle flowchart; B3 is deferred as a feature but carries an open
> correctness question that should be answered regardless.
>
> **The October date is unchanged.** Nothing here being on Daniel's deferred
> list makes the deadline softer — it makes the handoff to Bill the thing that
> has to work.

### B1. Procore data export — **BILL OWNS. Deferred from Daniel's queue.**

> **Ownership resolved 2026-07-22: Bill.** Deferred as build work for Daniel.
> The deadline does not move because an owner was assigned — **October is still
> the expiry and this is still the highest-risk item from the meeting.**

**State:** `app/procore/` already has the API client, `ProcoreToken`, and a
running webhook sync. `Submittals` and `SubmittalEvents` have been populating
the Brain for months.

**The job is smaller than "export Procore."** Structured submittal data is
partly captured already. The likely gaps are what the webhook never carried:
attachments and drawing sets, workflow template definitions, correspondence, and
submittal history predating the sync. So the real task is **finding the delta
between Procore and what the Brain already holds.**

**Recommended first move for Bill — ask Procore for a bulk export.** Most
platforms offer one on contract termination, and it beats scraping the API on
every axis. One email, before anyone builds anything.

**If it has to be built:**
1. Inventory, and it's cheap — enumerate Procore against `Submittals` /
   `SubmittalEvents` / the drawing tables. Roughly a day, and every other
   decision depends on it.
2. Target per category: raw documents into the lake (`RawSourceRecord`),
   structured data into existing models.
3. Pull via the existing client.
4. **Verify completeness before the subscription lapses**, spot-checked against
   known projects. There is no second attempt.
5. Attachments will be the slow part — file volume and rate limits.

**Open:** archival vs operational (does the Brain need to *serve* submittal
history and drawings after October, or just retain it?) and whether closed
projects need more than archival treatment. Both unanswered.

**Effort if it lands back on Daniel:** M–L, unknowable until the inventory
exists.

---

### B2. Submittal workflows + PM-based templates — **DEFERRED pending working session**

> **Deferred by Daniel 2026-07-22.** Not planned from the transcript — the
> meeting itself ended on *"we need to sit down and go through that workflow"*
> [L783], and Bill has already sent a document containing the full lifecycle
> flowchart. Planning around both would be guessing at something that exists on
> paper.

**State:** Nothing built. `Submittals` + `SubmittalEvents` + the Procore sync
exist; there is no internal workflow engine.

**What the meeting specified, for whoever picks this up:**

- **PM-owned templates.** Procore allows one template, so today it is a giant
  list where you click the right PM with the right drafter every time — *"one
  for Danny, one for Rich, one for Gary… it's super painful."* Assign the PM to
  a project and their templates load automatically.
- **The agent is the second step in the chain.** After sub-GC, before DRR, so
  feedback lands before a human spends time on it. Dalton submits → Carmen
  reviews → then Bill and the PM.
- **Workflow instance per submittal:** ordered steps, assignee per step, current
  step, history. Steps generate to-dos, which surface on D2.
- Soft-linking sub/DRR/FC is tracked separately as **B3**.

**Prerequisites before planning:**
1. The working session with Bill.
2. Bill's lifecycle flowchart, plus the AI-step additions he owes.
3. A decision on A5 (origination), which he named as a precondition
   [L1548–1550] and which is also deferred.

**This is the Procore replacement**, so it carries the October date. Bill called
it *"probably the next thing we really need to start working on"* at L752 — 300
lines before ranking T&M as HIGH, with neither statement referencing the other.
That conflict is still unresolved.

**Effort:** XL

---

### B3. Soft-link sub / DRR / FC — **DEFERRED**

> **Deferred by Daniel 2026-07-22.** But see the open correctness question
> below — it should not be deferred silently, because it may not be a feature
> at all.

**State:** Partial infrastructure — `SubmittalReconcile`,
`add_submittal_release_link`, `app/brain/submittal_matching/` with a matcher,
and `linked_release_id` + `link_status` on `Submittals` for the DRR→release
link.

**What Bill asked for:** sub, DRR, and FC are *"completely separate and not
linked at all"* in Procore and *"a pain in the ass to go find."* He wants them
**soft**-linked — explicitly not a full merge, which would overload the thread.

---

#### ⚠ Open question — possible sync correctness bug, not a feature

Bill's description conflicts with a prior investigation which concluded that
**one** Procore submittal advances GC→DRR→FC rather than three records
existing, and that our sync **freezes `type` at create**.

Verified while cataloguing: `submittal_id` is unique; `type` is set once in the
create path at `app/procore/procore.py:763`; the other `type` reference nearby
is the "created" event payload, not an update. No path was found that re-syncs
`type` on update — though the update function was not exhaustively walked.

**The two cases diverge completely:**

| If… | Then B3 is… |
|---|---|
| Three separate Procore records | The feature Bill described — a nullable predecessor link plus a resolver. **S–M.** |
| One record advancing, type frozen at create | **Not a feature — a sync bug.** The three "unlinked things" are one submittal we misrepresent, and everything keying off `type` reads a stale value: DWL DRR filtering, `start_install` ("only ever set on DRR submittals"), Rel assignment. |

**Cheap resolution:** a read-only SQL check against sandbox — distinct `type`
counts per project, and whether GC/DRR/FC submittals share numbering lineage.
No DDL, no writes.

**This should be resolved even while the feature stays deferred.** If it is the
second case, it is a live data-correctness issue affecting the DWL today.

**Effort:** S–M as a feature; unknown as a bug fix until diagnosed.

---

### B4. Customer-owned Procore access — **BILL OWNS. Deferred.**

> **Ownership resolved 2026-07-22: Bill.** Routed to him as a question for his
> Procore rep rather than a technical spike for Daniel — a rep can answer it in
> a sentence, where a spike costs half a day and may hit a permissions wall only
> a rep can lift.

**State:** Unknown, and that unknown *is* the item.

**The situation:** MHMW leaves its own Procore in October but stays connected to
**customers'** Procore instances. Bill wants that project data flowing into the
Brain — *"being able to pull that data out of there into the brain would be
huge opportunity."* Neither party knows whether MHMW's credentials can read
projects it does not own. It surfaced independently in the projects-page
meeting the same morning.

**The question for the rep:** can a company read project data from a Procore
instance it is not the owner of, and what scopes or permissions would the
customer have to grant?

**Why it matters beyond curiosity:** the answer bounds how rich the projects
page (D1) can ever be. Worth knowing before promising project data that cannot
be fetched.

**Effort:** S if it comes back as a spike.

---

## C. BB / Carmen

### C1. Note field on accept/reject — **P1. Diagnosed 2026-07-22: missing control on one of two surfaces.**

> **Not a new feature.** The backend and one frontend surface already implement
> this fully. The Procore document review surface — the one Bill uses — is
> missing the notes control entirely.

**What already exists:**
- `BBReviewFeedback` has `notes` (Text), `decision` (accepted|rejected),
  `rule_id`, `finding_snapshot` (freezes the finding so feedback survives rule
  edits), user attribution, and a `(review_id, finding_index)` unique
  constraint. Its docstring describes exactly the loop Bill asked for, with
  examples in his idiom: *"BB is right, this rise is 8″"* / *"false alarm, that
  flight pours into a topping slab."*
- `bbReview/shared.jsx` renders the **complete** control: accept/reject buttons
  plus a notes textarea, saved on blur with dirty-tracking and a "saved"
  indicator.

**The defect:** `bbReview/DocumentRow.jsx` → `FindingRow` (the Procore document
review surface) renders Accept and Reject and **no notes field**. No `notes`
state, no textarea, and `saveProcoreDocumentReviewFeedback` is called without a
`notes` key (lines 121–126). Its own normalizer (lines 46–56) maps `notes` out
of stored feedback, but `FindingRow` reads only `initial?.decision` — so any
existing note is **silently dropped from view** on that surface.

**Bill's actual workflow**, confirmed by Daniel: look at a finding → Accept →
add a note describing why. Step three is impossible where he works.

**Plan:**
1. **Extract the control from `shared.jsx` into one reusable component** and use
   it in `DocumentRow.jsx`, injecting the save endpoint (the two surfaces post
   to different routes). Fixing `DocumentRow` by copying the textarea across
   would leave two implementations to diverge again — that divergence is what
   caused this.
2. Include `notes` in the `saveProcoreDocumentReviewFeedback` payload.
3. Read `initial?.notes` so prior notes render instead of vanishing.
4. Verify the Procore-document feedback route accepts and persists `notes` —
   the column exists and the sibling endpoint saves it, so worst case this is a
   one-line route change.
5. Regression check: a note saved on one surface must be visible on the other.

**Why it ranks high for its size:** it is the input to every downstream learning
loop (C5, C6, and K1). Every review Bill works without it is training data
permanently lost. He gave the clearest articulation of any feature in the
meeting — a rule can be valid in general and wrong in context, and without the
note nobody ever learns which.

**Depends on:** nothing. **Effort:** S

---

### C2. Parts + hardware list generation — **EXPERIMENTAL TRACK. Test branch, no integration point yet.**

> **Direction set with Daniel 2026-07-22:** *"this will be a test branch but
> something we should absolutely get moving on… no clear integration point yet,
> just testing phase."* Deferred as a product feature; **active as an
> experiment.** Sample documents are in hand.

**State:** Nothing built. The knowledge exists — the Division 05 KB and the
"MHMW 101" conventions are already submitted, and the review system runs the
latest KB today.

**What makes this hard:** the drawing shows holes, not hardware. A saddle clip
takes two tech screws every time and the drawing never says so. FP42.5 means a
4×4 base plate with two ½" holes. Hole geometry implies the fastener — 2-hole is
~90% Titans into concrete; 4-hole with ½" is lags into wood; 7/16 for a lag vs
½ for a Titan, except sometimes ½ for lags too. None of it is on the sheet. It
lives in Bill's and David's heads and a drafter reconstructs it by counting.

**The failures it targets:** *"Hardware kills us."* Plus the periodic miss —
closed risers exist on the prints with a fab drawing, don't make the sheet, get
missed downstream. Roughly every six months.

**Testing phase — the only committed work:**
1. Run Banana Boy against the sample FC sets and read the output qualitatively.
   This is a **measurement**, and it answers the question that decides
   everything else: is this a prompt/KB problem or a genuinely hard extraction
   problem?
2. Bill's hand-built Excel parts page is the comparison baseline for a
   quantitative diff, if one is wanted. Still an open action item on him — but
   **not a blocker for the qualitative first pass.**

**Design direction for when it graduates:**
- Encode the discovery chain explicitly in `app/brain/pdf_review/rules.py`:
  identify part → determine mounting substrate → infer hardware.
- Hole-geometry priors as rules, gated behind the substrate discovery step.
- **Flag rather than guess.** *"We have 58 unfilled holes, what's going in
  there?"* The flag **is** the feature — a confident wrong hardware count is
  worse than an admitted gap, since the whole point is catching what humans
  miss.
- Output as an added cover sheet, approve/modify before commit.
- Slot into the DRR→FC gap — the last thing submitted before FC.

**Open, and deliberately unanswered during testing:**
- **Structured record or generated document?** Structured line items could later
  feed `MaterialOrder` and purchasing; a generated PDF sheet cannot. Materially
  different ambition, and it shapes the schema — decide before graduating, not
  after.
- Does it run inside the BB review or as a separate action?
- Does the approved list drive anything downstream, or is it purely part of the
  submittal package?

**Effort:** S to test. L to productionize.

**Why it deserved a rank it never got:** it targets the single named worst
recurring failure in the business and drew the strongest reaction in the
meeting, but fell out of the ranking exercise entirely.

---

### C3. Universal PDF tool — **P2. Absorbs former C4, C6, C7.**

> **Scoped with Daniel 2026-07-22:** *"one unified PDF markup tool, with a
> review panel… the goal is that there is a universal PDF tool whether that's
> on the DWL or the JL."* **More brainstorming wanted before build.**

**One tool, one stack, both surfaces.** Bill described it as a single thing —
*"we need an improved PDF viewer. So improve markup with the review tab, but
better versioning history so that you can look back and get the findings tagged
so you don't rerun. You can also see all the findings"* [L666–671]. It had been
catalogued as four separate items; it is one.

**What it comprises:**

| Was | Capability |
|---|---|
| C3 | Markup toolbar available inside the review window — *"we'll just throw the PDF markup tools right in this window"* |
| C4 | **Screenshot attach + resize.** Snip a detail from another drawing and paste it as a visual reference: *"your detail looks like this, but I really want it to look like this."* Paste-from-clipboard matters more than file upload. The board already does this — Bill made the comparison himself: *"exactly what you're doing with the bug tracker."* |
| C6 | **Version history + findings tagging.** `ReleaseDrawingVersion` exists. Tag findings to the version that produced them so a review is never re-run against unchanged input, and all findings for a release are viewable together. A review takes ~5 minutes, so this saves both spend and wall-clock. |
| C7 | **Available on both DWL and Job Log.** Review runs rarely on the job log — it should already have run upstream — but markup is used there for as-built errors and missing dimensions. |

**State:** PDF markup exists in the job log drawing viewer; the review window
lacks it. Screenshot attachment exists on the board. `ReleaseDrawingVersion`
exists. The pieces are all present and none of them are connected.

**Design constraint worth fixing now:** markups made in the review view should
anchor to the same `ReleaseDrawingVersion` the review ran against, so a markup
and a finding on the same sheet are addressable together. C5 depends on that
being true.

**Note the precedent:** C1's defect was two divergent implementations of the
same control. Building this as one component used by both surfaces is the
direct lesson.

**Next step:** a brainstorm/design pass before build. **Effort:** L as a unified
tool (lower than the four separate items summed).

---

### C5. Accept into knowledge base — **P2**

**Plan:** An action *inside* the unified PDF tool (C3): on a markup, a note
field plus an "accept into knowledge base" flag. Flagged items accumulate;
a periodic agent pass distills them into rule updates. Bill's framing: *"create
your own review note."*

His reasoning is the clearest case for the whole learning loop: *"if this
dimension is missing in this location, the railing that looks like that 47 times
later is missing it — now we've got the closer eyes"* [L641–643].

**Depends on:** C1 (the note data), C3 (the surface), **K1** (where the signal
lives — decide before building). **Effort:** M

---

### C8. Procore markup rotation bug — **ELEVATED. Attack soon.**

> **Raised in system priority by Daniel 2026-07-22:** *"need to fix, we should
> elevate this in the overall system priority… should be a quick fix and
> something to attack soon."* Fix regardless of the October Procore exit.

**State:** Procore-sourced markups render in the wrong position — rotated 90°
and offset from where they were placed. Bill demonstrated it live and diagnosed
it himself: *"if you rotated it 90 it would be right where it's supposed to
be"* [L156–160]. Not illegible, just displaced.

**Likely cause:** the markup coordinate space is not being rotated alongside the
page. Procore stores annotation coordinates against the page's native
orientation; if the renderer applies page rotation to the image but not to the
annotation transform, markups land rotated and offset by exactly that amount —
which is what Bill saw.

**Plan:**
1. **Pin the exact location first** — find where markup coordinates are mapped
   on ingest/render. This is the first task on the branch and it validates the
   "quick fix" assumption before anyone commits to it.
2. Reproduce with a known landscape sheet.
3. Apply the page rotation matrix to annotation coordinates, not just the page
   image.
4. **Verify against a portrait sheet too** — the trap here is a hardcoded 90°
   swap that fixes landscape and breaks portrait.

**Effort:** S expected — unconfirmed until step 1.

---

### C9. Carmen Miranda rename — **DEFERRED, waiting on Bill. Conversion confirmed.**

> **Confirmed 2026-07-22:** BB **will** be converted to Carmen Miranda.
> Deferred until Bill delivers.

**Blocked on Bill:** an avatar image, and a decision on the email — keep BB's or
mint a new one. He raised the wrinkle himself: *"you could keep BB internal if
you want, but then there's two of them"* [L98–100].

**Recommended scope — display layer only** (proposed, not yet confirmed):

`BB` is load-bearing as an internal identifier — `BBDrawingReview`,
`BBReviewFeedback`, `BBChatConversation`, `BBChatMessage`, `User.is_bb_chat`,
`app/brain/bb_chat/`, `frontend/src/components/bbReview/`, `BBReviewPanel.jsx`,
and the **bb@mhmw.com mailbox the entire email ingestion path depends on**.

Renaming user-visible strings and the avatar is an afternoon. Renaming schema,
modules, and the mailbox is not, and carries real risk for zero user-visible
gain. Recommendation: **`BB*` stays as the internal name in code, models, and
mail; only display strings and the avatar change.**

**Effort:** S for display-only.

---

### C10. Carmen runs Brain actions — **DEFERRED**

> **Confirmed deferred 2026-07-22.** Also flagged as a later evolution in the
> meeting itself.

**The idea:** trigger a review on a release and have Carmen run it while you
step away — *"it takes about five minutes, maybe you're stepping out for 30
minutes."* Start with triggering one known task and reporting back, then extend
as tasks prove repeatable. Bill's framing: *"check the box and then let the
leash off on that one"* [L536–544].

**Effort:** M

---

## D. Views and pages

### D1. Projects page rework — **ELEVATED. Ships with A1 (T&M) and A2 (COs).**

> **Elevated by Daniel 2026-07-22**, alongside T&M and change orders —
> *"ideally that will give us more reason to interact with this page."* The
> three are one push: the page is the reason the data is worth capturing, and
> the data is the reason the page is worth visiting.

**State:** Shipped and seen. `app/brain/projects/`, `Projects.jsx`,
`ProjectDetail.jsx`. Alta Metro carries live data; the rest is mock. Bill's
verdict: *"this is awesome… the PMs liked it."*

---

#### The box grid is shared with D2 — build it once

Bill asked for draggable boxes **in the project context**: *"when we select the
project… just some boxes, right, and I want to be able to like grab and move the
box too so somebody wants to see something different"* [L439–442].

250 lines later he described the personal page as *"very similar to this, but
it's just defined to the individual"* [L692] — pointing at the projects page and
saying the personal page inherits its shape. He never separately asked for drag
on the personal page; he asked for the **same kind of page**.

**So this is one component:** a configurable box-grid shell — draggable,
per-user positions, boxes that summarize and drill through — rendered once with
**project-scoped** data and once with **user-scoped** data (D2).

Same lesson as C1 (two divergent feedback controls) and C3 (four separate
markup items that were one tool). Build the shell once.

This also partly resolves D2's open question: if the personal page is the
projects page bound to a person, *"does it kill the DWL"* becomes tractable —
the DWL is one more box, showing your rows instead of everyone's.

---

**Sections, sorted by data availability** (the defers made this scopeable):

| Status | Sections |
|---|---|
| **Available now** | Releases · submittals · schedule/lookahead · **rentals** |
| **Landing soon** | T&M (A1) · change orders (A2) · punch list (A3) |
| **Deferred** | RFIs (A6) · project contacts (rides with A5) |
| **Never specified** | Budget items — Bill said *"some of this is going to be really hard to backfill"* and no source was ever named |

**Rentals is pure wiring** — `SunbeltRental`, `SunbeltRentalSnapshot`, and
`RentalReports.jsx` all exist. Bill: *"for sure we can get rentals in there."*
Cheapest real data on the page.

**First slice:** the box-grid shell plus the four sections whose data exists,
labelled slots for the three landing soon, and **drop the deferred ones rather
than shipping empty tabs.**

**Plan:**
1. Box-grid shell — draggable, positions persisted, shared with D2.
2. Admin vs non-admin gating. **Open:** Bill flagged it but never said where the
   line falls. With no budget or O&P data in v1, there may be nothing to gate
   yet — worth confirming rather than building speculative gates.
3. Keep all projects as tiles. Bill converted from expecting a dropdown.
4. Click a summary box → drill into the full list.
5. Wire the four available sections.
6. **Keep the four-dot stage indicator untouched.** Unrequested, and the warmest
   reaction in the meeting — *"the Domino's pizza tracker… it's so simple, it's
   so small."*

**Open:** Bill owes a markdown/full-page spec he was updating with the meeting's
notes. Building the layout before it lands risks rework on exactly the part he
is specifying.

**Effort:** L

---

### D2. Personal "My Open Items" page — **ELEVATED. Ships on the K2 grid engine.**

> **Elevated by Daniel 2026-07-22**, alongside D1 — *"we will build a similar
> grid engine to display custom metrics."* See **K2**.

**State:** `ToDos.jsx` and `app/brain/todos_routes.py` exist; `Notification`
exists. No per-user aggregate view. Bill traces the idea to a text Daniel sent
him — *"the cover page where you would open up the brain and it would tell you,
hey you're Dalton, this is what you need to do"* [L690].

**Plan:**
1. Render the **K2 grid engine** bound to a user instead of a project.
2. Aggregate everything under your open responsibility: to-dos, tasks,
   submittal reviews, drawing reviews, RFIs, punch list items.
3. Outstanding vs accomplished, with checkboxes.
4. Any role — a fabricator clicks their name and sees their assignments. PMs
   will be the heaviest users, but Bill sees value *"across the board."*
5. Photo feedback in the feed (D3).
6. Opt-in streams — *"do you want to know what orders are happening in Dencol."*

**One constraint that shapes the model:** **only PMs are project-scoped.**
Everyone else touches every project — *"it's pretty rare… the only ones that
don't care about the other projects is the project manager"* [L710–719]. So do
not build per-project user assignment for the rest of the company. The personal
page is the correct cut for them; a project filter is not.

**On "does this kill the DWL" — smaller than it looked.** Bill's proposal was
that admins keep the drafting workload, the weekly pass runs against it, *"and
then it just populates their little to-do list. And that's all they need."*
Under a shared grid engine that is not a replacement: **the DWL becomes one box
on your page showing your rows instead of everyone's.** Admins keep the full
view. Nothing is retired; it is scoped per viewer.

**Deferred — how the DWL weekly pass populates to-dos.** Daniel 2026-07-22:
*"little bit of both and in the works, kinda defer."* Partly built already, and
the auto-vs-confirm question overlaps F2 (meeting-derived assignment), where the
meeting's answer was propose-then-human-confirms. Worth noting the weekly DWL
pass **is** a meeting where assignments get spoken — the same machinery as F1/F2,
pointed at drafting.

**Depends on:** K2. Needed by: A3 punch list, B2 workflows. **Effort:** L

---

### D3. Photo feedback loop — **DEFERRED**

> **Deferred by Daniel 2026-07-22** — *"cute idea, defer."*

**State:** `ReleasePhoto` exists and photos already flow. Would be a query and a
surface, not a capability.

**What Bill described:** when a release you worked on gets installed, the photo
comes back to you. *"We never see what's going on… that's probably one of the
biggest things guys like — I've never seen it when it's done."* Morale. He was
clear it cuts both ways: *"Yeah. Oh look how short it is."*

**Solved design question, recorded for whenever this revives:** attribution
needs no new fields. There is no "drafted by" or "fabricated by" column, but
`ReleaseEvents.internal_user_id` already records who moved a release through
each stage — so *everyone who touched this release* is derivable from the event
stream. That is also the better definition: it includes the fabricator who
welded it, not just whoever's name is on the drawing.

**Depends on:** D2 for the surface. **Effort:** S

---

### D4. Timeline view — **MEDIUM. One combined item (absorbs former D5, D6, D7).**

> **Combined and elevated to medium by Daniel 2026-07-22** — *"this is one big
> pile… correct to keep these combined."* Four asks against one surface, and
> D5's panel depends on D4's filter model existing.

**State:** In flight — mirror cards and the timeline/jay-view work. Bill has
used it and likes it: *"having these cards in here with the shipping planning is
wonderful. The photos, the mirroring, all very good."*

**What it comprises:**

| Was | Ask |
|---|---|
| D4 | **Filter groups: fabrication, paint, install.** Same filter set as the main job log view. Install = today's view, with shipping planning / shipping complete / install teams as sub-filters. Long term each becomes a supervisor's sequencing lane. |
| D5 | **Unassigned panel.** A second vertical column of unassigned releases; drag into an installer lane and **the drop is the assignment** — it creates the mirror card and sets the date. Needed as a panel rather than a filter because unassigned items have no date and cannot render on the timeline at all. |
| D6 | **Drag a card to a different day**, install adjusting retroactively. *"This isn't happening today, I'm going to move it right there."* Extends the num_guys slider, which Bill already confirmed he likes. |
| D7 | **Photo config + bug.** Photos on shipping lanes, **off** installer lanes (horizontal stretch — the lanes run out of room). Separately: photos don't pre-populate on timeline cards the way they do elsewhere. That one is a bug, not a preference. |

**The detail not to lose:** cards enter the unassigned pool **post-fab** —
welded QC → paint — **not at release**. Bill was specific, and the reason is
that everything-ever-released would drown the panel: *"it's only items that have
made it through welded QC, so you have a little bit of lead up because they
still gotta paint them."*

**Already confirmed correct, no work:** mirror-card move restrictions. Shipping
planning ↔ complete and changing install team are allowed; cross-card moves are
blocked. *"That is exactly what we're looking for."*

**Rejected — do not build:** meeting notes on timeline cards. Bill: *"I hate the
idea of having that information in there when we talk about the project. It just
needs to not be specific to that release"* [L9–12].

**Long term, not this item:** fab and paint mirror cards on the same pattern —
same data, different view, 1:1 — and assigning fab to a person so a supervisor
can sequence their lane. The timeline becomes the live calendar.

**Effort:** L combined. D7's bug is the cheapest piece and can ship early on its
own.

---

## E. Scheduling

### E1. Tee-time fab capacity — **GO. Integration approach still open.**

> **Approved 2026-07-22:** *"tee time system is a go, but still working on the
> correct integration."* The concept is settled; **how it attaches to the
> existing date-setting flow is not.**

**State:** `app/brain/install_schedule/` on main; concept doc exists; capacity
calibration measured ~400 hrs/week from prod events.

**Settled behavior:**
1. **Shop only.** Release → paint complete. Once it's on the truck it's out of
   scope.
2. **Warn, don't reject.** Gray the date, allow selection anyway, pop *"potential
   overload of labor in this date… this needs to be confirmed,"* and record who
   overrode it. Bill opened wanting a hard reject and both parties talked each
   other out of it — correctly, since the staging data isn't authoritative yet.
   *"Then it's on your ass that you said that it's going to be overloaded."*
3. **Show the conflict, not just the wall:** what occupies the space, the next
   available slot, and what would have to move.
4. **Recommendations for fabrication only.** Installation stays visual — *"for
   installation, I think visually, this is more than enough… it's very easy to
   visually see he's busy this week."*
5. **Queue order confirmed correct as built:** hard date → fab order → conflict
   resolution.

**Still open — the integration point.** Where the capacity check attaches: on
green-date entry in the job log, inside the install modal, as a panel on the
timeline (D4), or its own page. Bill's description implies point-of-entry
interception (*"if you go to put a date, it would pop up something saying you
have a crash"*), but this was not decided.

**Reference data from the live analysis in the meeting:** welded QC needs to land
~6 days before the hard start-install date on average; the July 4 shutdown week
and low Friday output were both visible; paint runs ~3–4 days.

**Depends on:** E2, E3. **Effort:** L

---

### E2. Stage-weighted remaining hours — **WITH BILL + SHOP MANAGER**

> **Status 2026-07-22:** Bill is reviewing the data with his shop manager.
> Part of the same review as E3.

**Plan:** Remaining fab hours reduce as stages complete — 600 hours isn't 600 if
fit-up is done. Plus estimated paint (~3–4 days) and ship. paint↔fab distance
varies widely by product type (a big Ultralox fab job has no paint at all) and
is trainable later.

**Blocked on:** the stage-weight rework emailed to Bill 7/22 — **do not apply
the new weights until he approves.** Two things ship with it: the legacy Trello
alias map, and **both percentage maps in a single commit** so the system is
never left half-migrated.

**Effort:** M

---

### E3. Capacity data hygiene — **IN PROGRESS (Bill + shop manager reviewing data)**

> **Status 2026-07-22:** in progress. Bill is going over the data with his shop
> manager — the Louie conversation from the meeting, now happening.

**Three rules, all settled in the meeting:**
1. **Only same-stage start→complete pairs are credible.** cut start→cut
   complete, fit-up start→fit-up complete, weld start→weld complete. *"From cut
   start to cut complete would be the only valid understanding of hours consumed…
   as it goes from there until fit-up start, that's unaccounted for time"* — parts
   sitting on the floor waiting for a fabricator.
2. **Exclude stage-jumping releases entirely.** cut start → fit-up start with no
   cut complete is an invalid data point, not a long one.
3. **Anchor on cut start, not release.** A release can sit two months if the
   project doesn't need it, and that drift poisons the average.

**Why this is the first thing, not the last:** every downstream capacity number
depends on it, including the ~400 hrs/week throughput figure the entire tee-time
model rests on. Daniel said *"I'll probably do that later"* in the meeting; it
gates everything above it.

**Effort:** S

---

## F. Meeting → action

### F1. Meeting extraction bands — **LOW–MEDIUM. Combined item (absorbs former F2). Revisit.**

> **Scoped with Daniel 2026-07-22:** *"effectively, we are splitting the meeting
> extraction into tighter bands than to-dos… we will go back over this."*
> **Low–medium priority, and a revisit is expected before build.**

**The reframe that matters:** this is not new categories bolted onto to-dos. It
is **refining the extraction taxonomy itself** — today everything lands as a
generic to-do; the ask is for extraction to resolve into tighter, typed bands.

**State:** `Meeting`, `ChecklistItem`, `MeetingLearning`, `ExtractionSignal`,
and `BrainDrift` all exist. Extraction is mature; bb-meeting-v3 drift detection
already follows the detect-and-surface posture this needs.

**The bands, as described:** installation / fab / paint actions, alongside
drafting which already works this way. Bill: *"instead of global to-dos, we have
— that would be a separate action… probably under installation, then we'd have
fab, maybe we have paint actions."* His reaction to the idea: *"that's a really
good idea"* — and when Daniel pointed out it was his own, *"you take credit,
you're the boss."*

**The behavior it enables** (was F2): when a spoken responsibility attaches to a
mention, propose an assignment in the timeline to that installer with the spoken
date, and check capacity. Bill's example: *"when we're doing the production
meeting and we're saying Osvaldo is going to install this next Thursday, then
that would be an assignment… and then it can pre-plan our shipping."* Plus a
completion ETA confirmed on the to-do.

**Proposals, never auto-applied.** *"It would add it as an option to add and
wouldn't automatically add it — you have to approve everything."* Same posture
as the D2 DWL question and as existing drift detection: surface, don't write.

**Sits downstream of two elevated items.** The assignment surface is the
timeline (D4); the capacity check is tee-time (E1). The **extraction half is
buildable independently** of both, which is the natural first slice if this
moves before they land.

**Effort:** M

---

## G. Adoption

### G1. Desktop notifications — **HIGH PRIORITY. Elevated — near-term win.**

> **Elevated by Daniel 2026-07-22:** *"high priority, elevate — and a huge near
> term win."* Small effort, outsized adoption return.

**State:** `Notification` and the bell exist. `/admin/metrics` showed **nobody
used mentions all week** — every mention surface already built is invisible to
the people being mentioned.

**The problem in Bill's words:** *"you could mention someone and they might not
see it for a week."* And the model he wants: *"when I get a text it pops up on
my screen, when I get a Teams message I get a little thing… that flags you,
because you're sitting there at your computer, you just see that thing pop up."*

**Why the return is disproportionate:** it adds no surface. It makes existing
investment work — mentions, the board, notifications, and `pdf-mentions` on its
branch are all built and effectively unseen. Everyone is already on Chrome, and
the Brain already runs as a PWA with the banana icon; Bill runs it that way on
his iPad and phone.

**Plan:**
1. Web Push from the Brain; users opt in via Chrome's permission prompt.
2. **Training doc** — Daniel committed to one, and Bill will make sure everyone
   is on Chrome.
3. **Start with mentions only** (recommended, not yet confirmed). Expanding to
   to-do assignment and review completion later is easy; recovering from
   notification fatigue is not.

**The one real risk — the opt-in moment.** Chrome's permission prompt is
one-shot in practice: if someone dismisses it, re-requesting is painful and
often blocked. **The in-app moment that triggers the ask matters more than the
push plumbing behind it.** Ask in context, after an action that makes the value
obvious — not on first page load.

**Effort:** S

---

### G2. Photo-gated stage advancement — **DEFERRED**

> **Confirmed deferred 2026-07-22.** Also deferred in the meeting itself.

**The idea:** a release cannot advance to welded QC without an attached photo.

**Bill wants it, but was explicit about sequencing** — gate *after* adoption,
not to force it: *"once we start these guys and they're more power users and
they're starting to really function with it more, that's the spot where we'll be
able to gate those things."*

**The payoff is already visible without any gate.** Katie needs photos for
billing and today walks the shop with a stack of papers photographing work she
often can't identify — *"I don't know what it is most of the time, what it's
supposed to look like, where it's at."* That is **J1**, and it is the argument
for why capture matters before gating exists.

**Revisit trigger:** a photo-attach rate on `/admin/metrics` high enough that
gating formalizes existing behavior rather than imposing new behavior.

**Effort:** S

---

## H. Polish and bugs

### H1. Polish sweep — **ONE SWEEP. Tracked as a single item (absorbs former H2–H5).**

> **Scoped with Daniel 2026-07-22:** *"track as one sweep."* Not cherry-picked,
> not elevated — one pass covering all five.

| Was | Item | Detail |
|---|---|---|
| H1 | **Rolling calendar** | Current week as the first row, then ~4 weeks. **Not** two side-by-side months — both parties started there and converged away: *"the current week would always be at the top and then it would show the next four weeks. I don't think you need to do two months."* Mirrors the staging dropdown's roll-forward. The real pain is stale dates stranding you mid-navigation, which Bill hit live during the meeting. **Highest daily-use value in the sweep** — every hard date in the system goes through this control. |
| H2 | **Universal / full-screen modal** | *"Anytime we have a modal pop, go full screen — bigger modal all the way, just leave a little space you can click around it to close it out. Less scrolling, more information."* One rich modal across card view, description, and release detail. **A3's punch-list button lands inside it**, so A3 has a soft dependency on this piece of the sweep. |
| H3 | **Small items** | "Mark all received" on materials · banana indicator on the job log when a review has run · combine hyperlink + description into one column (David's call: target description) |
| H4 | **Visual** | Job log blue lighter and more transparent; keep gray for completed rows. Dark mode *"needs an update… something changed and it's weird."* **Daniel owes mockups before building** — Bill: *"I'll come back to you with some mock-ups and you guys can start to deliberate on it."* |
| H5 | **Metrics load times** | `/admin/metrics` fans out to several APIs. Cache or parallelize. Bill liked the content immediately — load time is the only thing between him and using it regularly. |

**Effort:** M for the sweep. H2 is the largest piece; the rest are S.

## I. Subs and external access

### I1. Subs view + OCIP visibility — **ELEVATED. (Absorbs former I2.)**

> **Elevated by Daniel 2026-07-22:** *"should be a super easy UI page to build so
> we can elevate."* Matches what he told Lexi — *"probably not a ton of data,
> it'll just be who's assigned."*

**State:** Nothing built. Installer assignment exists on releases;
`ProjectManager` exists.

**What Lexi asked for**, twice and unprompted: *"You'd go up here and click subs.
You'd get a list of all your subcontractors. And what they're doing. And all the
jobs that they're currently assigned to."* — *"That's what I need."* With
paid/not-paid per line. She'd take a paid yes/no flag on the release *"as a
start, at a minimum,"* but the tab is the real ask.

**Column-by-column data reality — this is why v1 is easy:**

| Column | Source | v1? |
|---|---|---|
| Sub → releases → projects | **Exists** — installer field on releases | ✅ |
| Paid / not-paid | **No source in the Brain.** QuickBooks, or manual entry | ✖ later |
| OCIP flag | **New column on `Projects`** + someone to set it | ✅ cheap |

**The OCIP piece is where the value is, and it's one column plus a rule:** flag
which projects carry controlled insurance, surface which subs are assigned to
them, alert on an unenrolled sub on an enrolled project.

**Why this outranks where the meeting left it.** The invoicing story reads as
convenience. The insurance story does not — on OCIP projects MHMW is *required*
to enroll each sub, and Lexi cannot enroll someone she doesn't know is there.
**It has already failed:** *"I did not know I had Eduardo out there… he fell
through the cracks and has been working on a project he's not involved in."*
Daniel's response in the moment: *"not good."*

Root cause under both payoffs: **she finds out a sub is on a project when they
bill her.** The information arrives after the risk has been taken. This is the
only item in either transcript with a realized compliance failure behind it, and
it never entered the ranking exercise — it surfaced in a hallway conversation.

**The dependency is cultural, not technical.** The view is only as good as
installer/sub assignment in the job log, which *"some guys do and some guys
don't."* Daniel's read: the tool has to exist first — *"once you have your
system, then you can go out there and get on their ass."*

**Plan:**
1. Subs tab: subcontractor → releases → projects, from existing assignment data.
2. OCIP flag on `Projects`; surface unenrolled subs on flagged projects.
3. **Ship rough v1 to Lexi *and* Bill together** — Bill needs the same picture
   to push PMs on assignment discipline.
4. Lexi emails back useful / not useful.
5. Paid status and QuickBooks later.

**Effort:** S–M for v1.

---

### I3. External user access — **ELEVATED. Ships with T&M processing.**

> **Elevated by Daniel 2026-07-22:** *"as soon as T&Ms are rolling, we will need
> this, so needs to be elevated with T&M processing."*

**Why T&M forces it.** The confirmed A1 flow has a PM seeding a ticket and
**sharing it to the person doing the work** — frequently a subcontractor
foreman, not an employee. The branch's own build doc lists **Subcontractor** as
the first permission tier. A1's Monday v1 works internally; the moment T&M is
actually *rolling* in the field, the fill-it-out step lands on someone with no
account.

**A1's deferred sub-facing layer and I3 are the same piece of work.** Both are
"a role that sees only what's assigned to it, without financials." Building them
separately means building it twice.

**State:** Greenfield. `User` has `is_admin`, `is_drafter`, `is_active`,
`is_bb_chat` — **no external role**. The app was built assuming every
authenticated user is staff.

**Plan:**
1. External role: sees only what is assigned to them, no financials.
2. **Parity with what a Trello card exposes today** — Bill's stated bar, and
   Trello shows very little: *"right now they can see the cards that are
   assigned to them, and that's it."*
3. **Audit every endpoint for financial leakage under the new role.** This is
   the real cost and the real risk — not the flag, but what gets missed.
   Serializer-level gating, never component-level.
4. This **is** the Trello decommission path.

**Blocks:** A1 sub-facing T&M · A3 punch list reaching subcontractor installers
(most of its real audience) · I4 installer invoicing · Trello decommission.

**Effort:** L — and the risk profile is "what you miss," not "what you build."

---

### I4. Installer ready-for-invoicing — **DEFERRED**

> **Confirmed deferred 2026-07-22**, even with I3 elevated. Also flagged as a
> long-term evolution in the meeting.

**One button in the field:** ready for invoice → creates the invoice, logs it in
our system, sends to billing, copies the installer's own email.

**Bill's reasoning:** *"those guys are all treadmill-y. They're working, they're
doing work, they don't have time to go and fucking do invoicing. They've got to
be on the job site doing this. So they need to just push a button that says it's
ready for invoice."*

He paired it with photo evidence — *"Mark, this is ready for invoicing? Sure,
buddy. Have some photos."* Same evidence-at-completion loop as A3's completion
photos and J1's billing photos.

**Gated behind I3.** **Effort:** M

---

## J. Other — **ALL DROPPED**

> **Assessed by Daniel 2026-07-22:** *"these are irrelevant basically."* All
> three dropped. Recorded for the archive only — not backlog.

**J1. Katie's billing photo link.** `InvoicingReport.jsx` and `ReleasePhoto`
exist; would have been wiring to surface the last-stage-change photo on the
invoicing report. Context: Katie walks the shop with a stack of papers
photographing work she often can't identify.

**J2. Dencol → Carmen routing.** Supplier order emails to John Rendon + Carmen
instead of CC-ing every department, with Carmen routing to the right people's
to-dos. Bill called it *"very down the road."*

**J3. Drafting timeline.** Not enough data — one item sitting alone in a week.

---

## K. Cross-cutting architecture

### K2. Configurable grid engine — **ELEVATED. Shared by D1, D2, and metrics.**

> **Scoped with Daniel 2026-07-22:** *"we will build a similar grid engine to
> display custom metrics."* Elevated alongside D1 and D2, which both render on
> it.

**What it is:** a configurable box-grid shell — draggable boxes with per-user
persisted positions, each box summarizing something and drilling through to the
full list.

**Where the requirement came from.** Bill asked for it in the **project**
context: *"when we select the project… just some boxes, right, and I want to be
able to like grab and move the box too so somebody wants to see something
different"* [L439–442]. Then 250 lines later he described the personal page as
*"very similar to this, but it's just defined to the individual"* [L692] —
pointing at the projects page and saying the personal page inherits its shape.
He never asked for drag twice. He asked for the same **kind** of page.

**Three consumers:**

| Surface | Bound to | Boxes show |
|---|---|---|
| **D1 Projects page** | A project | Releases, submittals, schedule, rentals, T&M, COs, punch |
| **D2 Personal page** | A user | Your to-dos, reviews, RFIs, punch items, your DWL rows |
| **Metrics** (`Metrics.jsx`, `/admin/metrics`) | The company | AI cost, BB accept rate, stage averages, mentions usage |

The third is what Daniel's *"custom metrics"* framing adds — the metrics page is
already a grid of summary boxes built bespoke. It is the same shape.

**Why it is its own entry:** three surfaces, one pattern. Built per-surface it
becomes three implementations that drift. This catalog already contains two
instances of exactly that failure — **C1** (two divergent accept/reject
controls, one missing the notes field, which is why Bill couldn't leave notes)
and **C3** (four separately-catalogued markup items that were one tool). Build
the shell once, bind it three ways.

**Plan:**
1. Grid shell: layout, drag, per-user position persistence.
2. A box contract — title, summary content, drill-through target, optional
   empty state.
3. Bind project-scoped (D1) first, since it's the one with an elevated deadline.
4. Bind user-scoped (D2).
5. Retrofit metrics opportunistically — not urgent, and it validates the
   contract against a surface that already exists.

**Open:** do box positions persist per user, per role, or per (user, surface)?
Per (user, surface) is the safe default and costs nothing extra.

**Effort:** M for the shell. It is a prerequisite for D1 and D2, not additional
work beside them.

---

### K1. Learning substrate — **decision needed before C1 ships**

**Raised by Daniel 2026-07-22:** *"probably need to rethink the learning tables
ecosystem because we will have many learning loops going forward."*

**State:** One loop is built and has its own tables — `MeetingLearning` and
`ExtractionSignal` in `app/brain/meetings/`, which distill aliases, owner maps,
and patterns back into meeting extraction.

**The loops now visible in this catalog:**

| Loop | Signal captured | Feeds |
|---|---|---|
| Meeting extraction (built) | Aliases, owner maps, patterns | To-do extraction |
| **C1 BB accept/reject notes** | Why a finding was right or wrong in context | Review rules |
| C5 Accept into knowledge base | Elevated markups + notes | Review rules |
| **A4 Lookahead matching** | Schedule line → release/submittal aliases | Next week's match |
| Submittal matching (partial) | Text/job-rel match corrections | `app/brain/submittal_matching/` |

**Why this is urgent rather than architectural navel-gazing:** C1 is ranked P1
and is itself a learning loop input. If the substrate question isn't at least
sketched before it ships, C1 invents its own storage, then A4 invents a third,
and the "run it all through agents to determine which rules need updating"
behavior Bill described has to reconcile four incompatible shapes.

**The decision is not "build a framework."** It is: do these loops share a
signal table with a `domain` discriminator, or stay separate with a shared
convention? Either is defensible. Choosing nothing is what costs.

**Plan:** A short design pass before C1. Inventory what each loop actually needs
to store (input, human verdict, rationale, resulting rule change), decide
shared-vs-separate, write it down. Do not build a framework ahead of the second
real consumer.

**Effort:** S to decide, and it unblocks clean work on C1, C5, and A4.

---

### K3. Data infrastructure — object storage migration — **ADDED 2026-07-22. Scoped as a migration, not a tune-up.**

> **Scope set by Daniel 2026-07-22:** *"I want to prepare our data infrastructure
> for way more PDFs/photos/emails/etc. Both volume and type of data is going to
> see a big jump."*

---

#### The finding that defines this item

**Every binary in the system lives on a Render persistent disk.**

- `Config.PDF_STORAGE_ROOT` and `Config.PHOTO_STORAGE_ROOT` (`app/config.py:105–118`),
  falling back to `<repo>/app/storage/` when unset.
- Writers: `app/brain/job_log/features/pdf_markup/storage.py`,
  `app/brain/job_log/features/photos/storage.py`,
  `app/brain/board/photos/storage.py`.
- Pointers: `storage_key VARCHAR(512)` on `BoardItemPhoto`,
  `ReleaseDrawingVersion`, and `ReleasePhoto`.
- **No object storage exists.** `requirements.txt` contains no `boto3`, no
  `azure-storage-blob`, no S3 client of any kind.

**Four consequences, all of which arrive precisely when volume jumps:**

| Consequence | Why |
|---|---|
| **Horizontal scaling is capped at one instance** | A Render persistent disk mounts to a single instance. No scale-out, and deploys with a disk attached generally mean downtime |
| **The binaries are almost certainly not backed up** | Postgres backups do not cover a mounted filesystem. The failure mode is the ugly one: a database that looks perfectly intact, with every `storage_key` pointing at nothing |
| **Fixed capacity ceiling** | Render disks are sized manually and do not grow elastically. "Way more PDFs and photos" hits a wall you must anticipate rather than discover |
| **New data types land on the same disk** | Emails, Procore exports, T&M attachments, parts sheets — every new type in this catalog inherits all three problems above |

---

#### Part 1 — Object storage migration (the core work)

**The schema does not need to change.** `storage_key` is a 512-char string; it
holds an object key as happily as a filesystem path. This is data movement plus
an adapter, not a migration in the DDL sense.

**Plan:**
1. **A storage abstraction** — one interface, three current call sites. Today
   each feature knows the filesystem directly; none of them should know the
   backend at all.
2. **Choose the backend.** The standing Render→Azure thesis makes **Azure Blob**
   the natural target — object storage is a clean first Azure beachhead that
   moves data without moving the app. S3-compatible is the alternative if that
   thesis is not yet firm.
3. **Backfill** existing objects, keeping `storage_key` values stable where
   possible so no row rewrite is required.
4. **Dual-read during cutover** — read from object storage, fall back to disk —
   so the migration is reversible and never drops a file mid-flight.
5. Retire the disk only after a verified inventory count matches.

**Sequencing note:** this should land **before** the volume jump, not during it.
Migrating 10k objects is a script; migrating 500k while they are actively being
written is an operation.

#### Backups — split out as K4

Backups were originally bundled here. **They are now K4 and are CRITICAL.**
Confirmed 2026-07-22: **there is no backup.**

One connection matters for sequencing: **object storage solves the binary-backup
problem structurally.** Versioning and replication are built into every object
store; a disk requires a bolted-on cron that someone must maintain and nobody
tests. That is an argument for pulling this migration *earlier* rather than
writing a disk-backup script with a short shelf life.

**Effort:** L

---

### K4. Backups — **🔴 CRITICAL. This week.**

> **Confirmed by Daniel 2026-07-22: there is no backup.** Elevated above every
> other item in this catalog. Nothing else here matters if the data is not
> recoverable.

**This is not a feature and should not be queued behind features.** Every item
in this document assumes the data it operates on continues to exist.

#### What is unprotected

| Asset | State |
|---|---|
| **Production Postgres** | No backup. Every release, submittal, event stream, and audit trail |
| **Binary storage disk** | No backup. Every marked-up PDF, release photo, board photo |
| **The combination** | Worse than either alone — a restored DB with no files gives you `storage_key` rows pointing at nothing, which *looks* like a successful restore |

#### Why this is worse than it looks

- **The event streams are the irreplaceable part.** `ReleaseEvents` and
  `SubmittalEvents` are append-only history that cannot be reconstructed from
  Trello or Procore. Releases could theoretically be re-entered; their history
  could not.
- **It removes the backstop prod migrations assume.** `migrations/README.md`
  documents a prod incident that shaped the current migration discipline. That
  discipline reduces the chance of damage; it does not undo damage.
- **It compounds B1.** Procore data pulled before October has **no second
  source**. Restoring it is not an option — it would no longer exist anywhere.

#### Plan for this week

1. **Enable managed Postgres backups** with point-in-time recovery. Fastest path
   to non-zero protection; do this first, today.
2. **Add an independent logical backup** — scheduled `pg_dump` to object
   storage, in a different provider account or region. Managed snapshots living
   in the same account as the database are a *correlated* failure: an account
   compromise or billing lapse takes both.
3. **Protect the binaries.** Either a scheduled sync of the storage disk to
   object storage, or **pull K3's migration forward** and get versioning and
   replication for free. The second is more work now and less maintenance
   forever.
4. **Test a restore into a scratch environment.** Not a checkbox — restore, boot
   the app, open a release, open its PDF. **An untested backup is a belief.**
   This step is the one that most often reveals the backup was never valid.
5. **Write down the RPO/RTO you actually have** once tested, so the next
   decision is made against a number rather than an assumption.

#### Guardrails

- **Read-only against prod for diagnosis.** Confirming what exists is `SELECT`
  and provider-console inspection. No DDL, no writes.
- **Restore testing goes to a scratch database**, never over anything live.
- Daniel runs anything that touches prod; Claude writes the scripts and the
  commands.

**Effort:** S–M for steps 1–2 and 4. Step 3 is S as a sync script, L if folded
into K3.

---

## L. Design system

### L1. Styling v3 — full application redesign — **ADDED 2026-07-22. XL.**

> **Scope set by Daniel 2026-07-22:** *"we need a full redesign."* Not a
> token/theme layer — a component redesign touching every page.

**Supersedes H1's visual sub-item.** The polish sweep had contained "job log
blue lighter, keep gray for completed rows, fix dark mode." Those are v3
decisions. Doing them inside a sweep locks in choices v3 then has to unpick.
**H1 keeps only behavioral items**; all styling moves here.

---

#### The sequencing conflict, and the recommendation

A full redesign touching every page collides directly with Tier 1, which builds
**three new surfaces** — K2's grid engine, D1 projects, D2 personal — plus D4's
timeline rework. Built in the current system, all four get redesigned later.

**Three options:**

| Option | Cost |
|---|---|
| v3 first, then build | Delays every Tier 1 item behind an XL |
| Build Tier 1 now, redesign after | Guarantees rework of K2, D1, D2, D4 — the newest code in the app |
| **v3 foundation first, new surfaces built native, legacy migrated progressively** | **Recommended** |

**The recommended shape:** establish the design system and component primitives
first — the parts K2/D1/D2 actually consume (cards, tables, modals, form
controls, chips, the grid shell itself). Build the new surfaces natively in v3.
Migrate the legacy pages — job log, DWL, board, archive — progressively behind
that foundation.

This keeps Tier 1 moving, avoids building the newest pages twice, and lets the
oldest pages migrate at whatever pace is comfortable. **K2 is the natural first
consumer of v3 primitives**, which is convenient: it is already scheduled ahead
of D1 and D2.

---

#### Known inputs — the only styling signal on record

- **The DWL reads better than the job log**, and Bill believes the blue is why:
  *"the drafting workload, this is so much more satisfying."*
- **Blue should be lighter / more transparent / gentler.** The old job log's
  pale blue did the one job that matters — *"just enough for your eye to track
  the lines."*
- **Gray must be retained for completed rows.**
- **Dark mode is broken** — *"dark mode needs an update… something changed and
  it's weird."*
- **Daniel owes mockups before building.** Bill: *"I'll come back to you with
  some mock-ups and you guys can start to deliberate on it."*

#### Two constraints a v3 system must absorb

1. **iPad is a real target, and it is currently broken.** Bill runs the Brain as
   a PWA on his iPad and phone. Native HTML5 drag is inert on iPad across ~10
   components — job log reorder, DWL, archive, gantt stage-change, the PM board.
   Only `Board.jsx` uses dnd-kit and works. **A full redesign is the moment to
   fix touch systematically rather than component-by-component** — and D4's
   timeline and K2's grid are both drag surfaces, so this is not optional for
   them.
2. **Dark mode is a first-class mode, not a filter.** It is already in use and
   already degraded. A redesign that treats it as an afterthought reproduces the
   current problem in new paint.

**Effort:** XL. Foundation (tokens + primitives) is M and unblocks K2; the
progressive legacy migration is the long tail.

---

## Ranked summary

**Revised 2026-07-22** after a full item-by-item walkthrough with Daniel against
his meeting notes. This supersedes the initial ranking, which was inferred from
the transcript alone.

---

### 🔴 TIER 0 — CRITICAL, this week

| Item | Effort | Note |
|---|---|---|
| **K4 Backups** | S–M | **There is no backup.** Not a feature — the precondition for every other item being worth building. Postgres *and* the binary storage disk are both unprotected |

---

### TIER 1 — Elevated, near-term

Ordered by sequence, not just importance. Prerequisites first.

| # | Item | Effort | Note |
|---|---|---|---|
| 1 | **A1 Time & materials** | M | Committed **Mon 2026-07-27**. Origination path only — paper ingestion dropped, which means this is a **build**, not a merge |
| 2 | **I3 External user access** | L | Elevated *with* T&M — the fill-it-out step lands on sub foremen. Same work as A1's deferred sub-facing layer |
| 3 | **K2 Grid engine** | M | **Prerequisite for D1 and D2.** Not extra work beside them |
| 4 | **D1 Projects page** | L | Elevated with A1/A2 — *"gives us more reason to interact with this page"* |
| 5 | **A2 Change orders** | M | Email capture only. **Blocked on Bill** for the CO log + a sample email |
| 6 | **D2 Personal page** | L | Renders K2 bound to a user |
| 7 | **G1 Desktop notifications** | S | *"Huge near-term win."* Makes every existing mention surface visible |
| 8 | **C1 Note field defect** | S | Diagnosed: the control exists on one surface, missing on the one Bill uses |
| 9 | **C8 Procore markup rotation** | S | Elevated. Fix despite the October exit |
| 10 | **I1 Subs view + OCIP** | S–M | Assignment data already exists; OCIP is one column and a rule |

**Four of these are S.** C1, C8, G1, and most of I1 are small, unblocked, and
independent — they can land while the larger items are in flight.

---

### In progress / with Bill

| Item | Status |
|---|---|
| **E3 Capacity data hygiene** | In progress — Bill reviewing data with his shop manager |
| **E2 Stage-weighted hours** | With Bill + shop manager. Do not apply new weights until approved |
| **E1 Tee-time** | **GO.** Concept settled; the integration point is still open |

---

### Newly added — unranked, needs scoping

| Item | Note |
|---|---|
| **K3 Data infra: object storage migration** | **L.** All binaries sit on a single Render disk — no object storage exists. Caps scaling at one instance. Pulling it forward is one way to solve K4 step 3 |
| **L1 Styling v3 — full redesign** | **XL.** Recommendation: v3 foundation first, new surfaces built native, legacy migrated progressively — otherwise K2/D1/D2/D4 get built twice |

---

### TIER 2 — Medium

| Item | Effort | Note |
|---|---|---|
| **D4 Timeline view** | L | One combined pile (filters + unassigned panel + drag-to-day + photo config/bug) |
| **A3 Punch list** | M | Internal-only, PM-created, informational. Soft dep on H1's modal |
| **A4 Lookahead upload** | M | Engine already on main. **Interaction layer needs a design pass** |
| **C3 Universal PDF tool** | L | One tool, both surfaces. **Needs a brainstorm before build** |
| **C5 Accept into knowledge base** | M | Lives inside C3. Gated on K1 |
| **H1 Polish sweep** | M | Rolling calendar, full-screen modals, small items, metrics load. **Visual item moves to L1** |
| **K1 Learning substrate** | S to decide | **Trigger moved** — see below |

**K1's forcing function changed during the walkthrough.** It was "decide before
C1 ships," on the assumption C1 would invent new storage. C1 turned out to be a
defect fix against `BBReviewFeedback`, which already exists — so **C5 and A4 are
now the first loops that would invent their own tables.** Decide before either.

---

### TIER 3 — Low

| Item | Effort |
|---|---|
| **F1 Meeting extraction bands** | M — splitting extraction into tighter bands than to-dos. Revisit expected |

---

### Experimental track

| Item | Note |
|---|---|
| **C2 Parts + hardware list** | Test branch. Sample docs in hand. No integration point yet — *"just testing phase"* |

---

### Deferred

| Item | Why |
|---|---|
| **A5 Project origination** | Full defer. Was B2's stated precondition |
| **A6 RFIs** | Full defer, not even a placeholder |
| **B1 Procore data export** | **Bill owns.** October expiry unchanged |
| **B2 Submittal workflows** | Waits on the working session + Bill's lifecycle flowchart |
| **B3 Soft-link sub/DRR/FC** | Deferred as a feature — **but carries an open correctness question** |
| **B4 Customer Procore access** | **Bill owns** — a question for his Procore rep |
| **C9 Carmen rename** | Confirmed happening; waiting on Bill's avatar + email decision |
| **C10 Carmen runs actions** | — |
| **D3 Photo feedback loop** | *"Cute idea, defer"* |
| **G2 Photo-gated stages** | Gate after adoption, not to force it |
| **I4 Installer invoicing** | Gated behind I3 |

### Dropped

**J1** Katie's billing photo link · **J2** Dencol → Carmen routing ·
**J3** Drafting timeline — *"these are irrelevant basically."*

---

## Open threads that are not features

**B3's correctness question should be answered even though the feature is
deferred.** If one Procore submittal advances GC→DRR→FC and our sync freezes
`type` at create, then everything keying off `type` reads a stale value today —
DWL DRR filtering, `start_install`, Rel assignment. Resolvable with a read-only
SQL check. See B3.

**There is no backup — see K4.** Confirmed 2026-07-22. Prod Postgres and the
binary storage disk are both unprotected. This outranks everything else in the
catalog and is scheduled for this week.

**E1's integration point is undecided.** Where the capacity check attaches —
green-date entry, install modal, timeline panel, or its own page. Bill's
description implies point-of-entry interception, but it was never settled.

**A4, C3, K3, and L1 all need design/scoping passes before build.** None are
blocked on another person; all were explicitly flagged as needing more thought.

---

## Blocked on Bill

Eight items, none of which Daniel can unblock:

| Owed | Blocks |
|---|---|
| Change order log (Excel) | A2 backfill |
| Sample change order email | **A2 — the classifier can't start without it** |
| Projects page markdown / full-page spec | D1 layout |
| Parts page "brain stem" Excel | C2 quantitative comparison |
| Carmen avatar + email decision | C9 |
| Stage weight approval | E2 |
| Lifecycle flowchart + AI steps | B2 |
| Procore export plan; customer-Procore question to his rep | B1, B4 |

---

## Still needing Bill's call

1. **Does B2 (submittal workflows) outrank A1 (T&M)?** He named both as "the
   next thing," 300 lines apart, neither referencing the other. B2 is now
   deferred, which defers the question rather than answering it — and October
   does not move.

*(Resolved during the walkthrough: B1 ownership → Bill. D2 vs the DWL → the DWL
becomes one box on the personal page rather than being retired.)*
