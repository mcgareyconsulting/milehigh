# MHMW Ops Planning

Synthesized from in-person meeting transcripts. The transcripts themselves are
**not** in this repo — they live locally at `~/Desktop/Transcripts/MHMW/`, with
per-meeting findings in `~/Desktop/Transcripts/MHMW/processed/`.

Every claim cites its source meeting so it can be traced back to the transcript
on the machine that holds it. See `~/Desktop/Transcripts/README.md` for the
pipeline.

**Sources rolled up so far:** `Bill-7-22-2026` · `Lexi` (both 2026-07-22)

**Per-feature plans, effort, and ranking:** [`feature-catalog.md`](feature-catalog.md)

---

## 0. The forcing function

**Procore's contract ends in October 2026.**

Bill stated this mid-meeting believing Daniel already knew; he didn't. It
converts the Procore replacement from an open-ended goal into a dated one,
roughly ten weeks out, and it is the constraint everything else sequences
around. It already killed a feature in-flight: a proposed "close DRR →
auto-create FC in Procore" backend was cut on the spot as throwaway work.

Two consequences are underscoped:

- **Data extraction from Procore before the subscription lapses.** Raised,
  agreed important, **no owner and no date**. This is the highest-risk open item
  from the meeting — it has a hard cliff behind it and nothing scheduled in
  front of it.
- **Customer-owned Procore instances persist.** MHMW stays connected to
  customers' Procore after leaving its own. Pulling that data into the Brain is
  a separate problem with unknown access; it also surfaced in the projects-page
  discussion the same morning.

---

## 1. Priority order

As stated by Bill in the 2026-07-22 review. Quoted rankings are his words.

| Rank | Item | Basis |
|---|---|---|
| **HIGH** | Time & materials | *"that's a high priority item"* |
| **HIGH** | Change orders + backfill of the existing CO log | *"I put it also as high… along with T&M"* |
| **HIGH** | New project origination / ingestion | *"new projects — yes, and getting those going"* |
| **HIGH (dated)** | Procore replacement: submittal workflows | October cliff; *"the next thing we really need to start working on is the workflows for the drafting department"* |
| **MED+** | Punch list | *"medium plus"* |
| **MED** | Lookahead schedule upload + markup | Daniel proposed medium-low, Bill settled on medium — not a needle-mover since anyone can already read the schedule |
| **LOW** | RFIs | *"a little priority thing at this point… needs a placeholder for a future evolution"* |

**Committed:** a first T&M version by **Monday 2026-07-27** — enough to start
tracking, with the data model expected to change after real use.

**In flight, not re-prioritized:** tee-time fab capacity, timeline filters and
mirror cards, the subs view for Lexi.

**Sequencing note.** Three of the four HIGH items (T&M, change orders, project
origination) are data-capture features that feed the projects page. The fourth
is the Procore replacement. They aren't competing — origination is a
*precondition* for the Procore replacement, since replacing submittal workflows
requires the contract, schedule, estimate, and drawings to already be in the
Brain.

---

## 1b. What the priority list does not cover

**The ranking is an ingestion queue, not a roadmap.** Every ranked item is a
data type the Brain does not hold yet — T&M, change orders, punch lists,
lookaheads, RFIs, project origination. The ranking exercise started at
transcript L1034 and ran to L1215; roughly two-thirds of the meeting happened
outside it and was never ranked at all.

That unranked two-thirds contains work that is larger, more urgent, or
structurally prior to items on the ranked list. Placement below.

### Preconditions — ranked work hits a wall without these

| Item | Blocks | Why |
|---|---|---|
| **External user access to the Brain** | Punch list (MED+), installer invoicing loop, Trello decommission | A punch list assigns work to installers who are frequently not employees. Without outside-user access, punch lists can only be assigned to MHMW staff — which is the fallback, not the design. This is also *"effectively Trello"*: assigned items only, no financials, parity with the current card. |
| **Project origination** | Procore replacement (HIGH, dated) | Ranked as its own HIGH item, but it is a dependency, not a peer. *"In order for us to get the Procore in place, we're probably going to need to be able to get the project origination documentation in place too."* |
| **Procore data export** | Everything after October | Unowned. No plan. Hard cliff. |

### Unranked but arguably above the ranked list

| Item | Case for it | Line |
|---|---|---|
| **Submittal workflow / PM-based templates** | Bill called it *"probably the next thing we really need to start working on"* — a priority statement made ~300 lines before the ranking exercise, and never reconciled with *"T&M is a high priority item."* This **is** the Procore replacement, so it carries the October date. | L752–753, L792–820 |
| **BB parts + hardware list generation** | Drew the strongest reaction in the meeting, and targets the single named worst recurring failure (*"hardware kills us"*). Came out of the ranking exercise entirely — it landed as an experiment (*"see how Banana Boy generates the parts list as a start"*), not a scheduled item. | L166–302, L367–369 |
| **Personal "My Open Items" page** | Not a feature so much as a strategic bet: Bill thinks it *"almost kills the drafting workload"* for non-admins. That is an architectural decision about how the whole company reads the Brain, and it deserves an explicit call rather than a queue position. | L687–745 |

### Rides with a ranked item — no separate slot needed

| Item | Rides with |
|---|---|
| Projects page rework (gating, tiles, draggable boxes, drill-down) | T&M + change orders + origination — all three land on this page |
| Rentals, project contacts, CO executed/open filter | Projects page sections |
| Punch list creation from inside the release modal | The universal-modal work |
| Timeline filters (fab/paint/install) + unassigned panel | Tee-time and mirror cards, already in flight |

### Confirmed done — no work

Mirror-card move restrictions · ship date + bidirectional install modal ·
materials column · the four-dot stage indicator · the old job log is not missed.

### Bugs — cheap, unblocked, no ranking required

| Bug | Line |
|---|---|
| Photos don't pre-populate on timeline cards | L1 |
| Procore-sourced markups render rotated 90° and offset | L149–165 |
| Dark mode *"needs an update… something changed and it's weird"* | L880–884 |
| Job log blue too heavy; needs gray for completed rows | L867–890 |
| `/admin/metrics` load times | L1228–1234 |

### One polish pass — small, batchable, high daily-use value

Rolling calendar (current week first row, ~4 weeks) · full-screen modals with a
click-out margin · "mark all received" on materials · banana indicator on the
job log · combine hyperlink + description · universal modal for card view ·
timeline photo config (on for shipping lanes, off for installer lanes).

### Cheapest leverage in the meeting

**Desktop notifications.** Small, and it directly closes the loop on the
metrics finding that *nobody used mentions all week*. Every mention feature
already built is currently invisible to the people being mentioned. Needs the
Chrome opt-in training doc alongside it.

**Photo feedback loop** — showing installed photos back to the person who
drafted or fabricated it. Bill's read: *"that's probably one of the biggest
things guys like — I've never seen it when it's done."* Adoption play, not a
capability.

### Explicitly deferred in the meeting

Photo-gated stage advancement (wait for power users) · installer "ready for
invoicing" button · giving Carmen the ability to run Brain actions ·
Dencol orders routed to Carmen instead of CC-all (*"very down the road"*) ·
drafting timeline view (not enough data; one item alone in a week) · a library
of standard details to snip from (Bill lukewarm — MHMW already has symbols).

### Needs a call from Bill

1. **Does the submittal workflow outrank T&M?** He said both were the next thing
   to work on, 300 lines apart, and nobody noticed the conflict. October forces
   the question.
2. **Is the personal page replacing the DWL for non-admins?** If yes it moves up
   sharply and changes what the DWL is for.
3. **Who owns Procore data export, and by when?**

---

## 2. Decisions

| Decision | Rationale | Source |
|---|---|---|
| Procore replacement is dated to October | Contract lapse | Bill 7/22 |
| Do not build the DRR→FC Procore backend | Throwaway against the October exit | Bill 7/22 |
| Tee-time is shop-only; warns rather than rejects | Staging data isn't good enough yet to be authoritative | Bill 7/22 |
| Tee-time v1 scope ends at paint complete | Once it's on the truck it's out of scope | Bill 7/22 |
| Only same-stage start→complete pairs are credible capacity data | cut complete→fit-up start is unaccounted staging time; exclude stage-jumping releases entirely | Bill 7/22 |
| Measure fab capacity from cut start, not release | A release can sit two months before cut start; that drift poisons the average | Bill 7/22 |
| Lookahead ingestion uses four-week lookaheads, not full project schedules | Full schedules drift tremendously and would induce confusion | Bill 7/22 |
| Lookaheads are uploaded and marked up, not email-forwarded | Markup is the training signal | Bill 7/22 |
| T&M and change orders are separate records | ~90% of T&Ms become COs, but COs also come from RFIs/ASIs with no T&M | Bill 7/22 |
| Change orders auto-ingest from email; no create button | Carmen is CC'd on the outbound customer email | Bill 7/22 |
| Installers cannot start a T&M | A PM or lead authorizes and seeds it, then shares it out | Bill 7/22 |
| Punch lists attach to a release; responsible party defaults to the last installer | — | Bill 7/22 |
| MHMW contract drawings + our markups are the source of truth for ASI/RFI drift | — | Bill 7/22 |
| Don't pull RFIs directly from Procore | Most GC RFIs aren't ours and we never see them | Bill 7/22 |
| Notes do not belong on the timeline view | *"It just needs to not be specific to that release"* | Bill 7/22 |
| Photos on shipping planning/complete cards; none on installer cards | Horizontal stretch — install lanes run out of room | Bill 7/22 |
| Mirror-card move restrictions are correct as built | *"That is exactly what we're looking for"* | Bill 7/22 |
| Meeting-derived responsibilities become per-department actions, not global to-dos | Installation / fab / paint actions; drafting already works this way | Bill 7/22 |
| Meeting-derived install assignments are proposals, human-confirmed | — | Bill 7/22 |
| BB is renamed "Carmen Miranda" | — | Bill 7/22 |
| Build a subs view, shipped to Lexi and Bill together | Bill needs the same picture to push PMs on sub assignment | Lexi 7/22 |

## 3. Open questions

| Question | Owner | Blocking |
|---|---|---|
| How do we pull our data out of Procore before October? | **unowned** | **Yes — hard deadline, no plan** |
| How much access do we have to customer-owned Procore instances? | Daniel | Projects page data richness |
| Does Carmen keep the BB email or get a new one? | Bill | Rename rollout |
| Fab-hours overload check: daily, weekly, or by stage? | open | Tee-time v1 |
| How do we handle origination overlap for in-flight projects? | open | New project ingestion |
| What's the admin vs non-admin line on the projects page? | open | Projects page GA |
| Does the paid flag live on the release or only in the subs view? | Daniel | Subs view v1 |
| Does Lexi want to be on Katie's invoicing report? | Lexi | No |

---

## 4. Candidate scope

Detail, line-cited, lives in the per-meeting findings files. This is the index.

### Time & materials — HIGH

Authorization-gated creation (PM/lead seeds, worker fills, originator confirms).
Signature box with typed name. **Two layers: admin with financials that creates
the CO, and a sub-facing layer without them** — sub cost-blindness is the point.
Photos, video, people on the job. No backfill: T&M is still paper, possibly
scanned into KU SharePoint, and the explicit decision was *"leave that sucker
alone, create our own new one."*

### Change orders — HIGH

Auto-ingest by CC'ing Carmen on the outbound customer email; capture the request
PDF, attachments, and the thread. Log, follow up, execute. Filter executed vs
open on the project page. Backfill from the existing active CO log (Excel, Bill
to send).

### New project origination — HIGH

Contract, project schedule, estimate, and drawings in; spec section generated
out. Precondition for the Procore replacement. Needs explicit "stop here"
cut-points for in-flight projects whose submittals are already done.

### Procore replacement: submittal workflows — HIGH, dated

- **PM-based workflow templates.** Procore allows one template, producing a
  giant list where you must click the right PM with the right drafter every
  time. Assign the PM to the project → their templates load. *"Super painful"*
  today.
- **The agent is the second person in the workflow** — after sub-GC, before DRR,
  so feedback lands before a human spends time on it.
- **Soft-link sub / DRR / FC.** They're completely unlinked in Procore and hard
  to find, but a full merge would overload the thread.
- Bill has already sent a full-lifecycle flowchart; it needs the AI steps added.
- **A dedicated working session on the workflow is an open action item.**

### Punch list — MED+

"Create punch list" from inside the release modal. Photos, video, PDFs, notes,
due date. Responsible party defaults to the last installer, reassignable — and
reassignment always goes to an MHMW employee, backfilled later. Lands in that
person's to-dos; completion photos close it.

**Blocked on external user access to the Brain.** This is the actual Trello
replacement: external users see only what's assigned to them, no financials,
parity with what a Trello card exposes today.

### Lookahead schedules — MED

Upload a four-week lookahead PDF to the project tab, view it, mark it up to flag
where releases belong ("guardrails go here" under exterior finishes), which
trains recognition for next week's. The Alta Metro cross-check was validated
as-is: *"nailed it."*

### RFIs — LOW / placeholder

Email-ingested, internal and inbound. Forward to Carmen → triggers review →
pulls old vs new drawings → flags changes → includes the estimator → creates
action items. ASI (new drawing set after contract signing) is the main driver.

### Projects page

Admin vs non-admin gating. All projects as tiles (Bill converted from expecting
a dropdown). Draggable boxes. Click a summary → drill into the full list.
Sections: submittals, releases, schedule, T&M, budget, rentals, CO log,
contacts, RFIs, punch list. Everything schedule-shaped renders as a timeline —
*"timeline, timeline, timeline."*

**The four-dot stage indicator was unrequested and landed hardest of anything
shown.** *"It's really just four dots… it kind of bridges that gap, but it's so
simple, it's so small."* — *"The Domino's pizza tracker."*

### Personal "My Open Items" page

Per-user: outstanding items, completed items, checkboxes. To-dos, tasks,
submittal reviews, drawing reviews, RFIs assigned to you. Any role, not just
PMs.

**This may retire the drafting workload view for non-admins.** Admins keep DWL
and run the weekly pass, which populates each person's to-do list. Note that
**only PMs are project-scoped** — everyone else touches everything, so
per-project user assignment is the wrong model for the rest of the company.

Includes a photo feedback loop: when a release you worked on gets installed, the
photo shows up in your feed. *"That's probably one of the biggest things guys
like — I've never seen it when it's done."*

### BB / Carmen — drawing review

Validated enthusiastically. Asks:

- **Note field on every accept/reject** — the learning loop. A rule can be valid
  in general and wrong in context.
- PDF markup tools in the review window.
- **Parts + hardware list generation** as an added cover sheet, built pre-FC in
  the DRR→FC gap. Flag unfilled holes. Discovery chain: identify part →
  determine mounting substrate → infer hardware.
- Screenshot attachment onto the sheet, with resizing.
- "Accept into knowledge base" on a markup + note.
- Version history; tag findings so reviews aren't re-run.
- Periodically run all admit/deny notes through agents to update rules.
- Merge with job log markup — *"this needs to become our profile markup
  system."*

**Bug:** Procore-sourced markups land rotated 90° and offset. Suspected
portrait/landscape handling on ingest.

**Next step:** see how Banana Boy generates a parts list, then decide entry
points.

### Scheduling — tee time

Finite weekly fab hours gate green dates. Warn + explicit override, showing what
occupies the space, the next available slot, and what would have to move.
**Stage-weighted remaining hours** — through fit-up means remaining fab hours
are reduced accordingly — plus estimated paint (~3–4 days) and ship.
Recommendations for fabrication; visual-only for installation. Paint↔fab
distance varies widely by product type (Ultralox fab has no paint) and is
trainable. Queue order — hard date, then fab order, then conflict resolution —
confirmed correct as built.

### Timeline view

Same filter set as the main job log view, in three groups: **fabrication, paint,
install** (install = today's view). **Unassigned installs as a second vertical
panel**, dragged into an installer lane — the drop *is* the assignment and
creates the mirror card. Cards enter "unassigned" post-fab (welded QC → paint),
not at release, or the panel drowns. Fab and paint mirror cards later, same data
different view.

**Bug:** photos don't pre-populate on timeline cards the way they do elsewhere.

### Modals / job log polish

Rolling calendar with the current week as the first row and ~4 weeks after — not
two months. Full-screen modals with a click-out margin. "Mark all received" on
materials. Banana indicator on the job log when a review has been run. Combine
hyperlink + description into one column. Universal modal for card view.

Confirmed working: ship date with the bidirectional install modal; the materials
column.

### Visual

Job log blue should be lighter and more transparent; the DWL reads better and
Bill thinks the blue is why. Job log still needs gray for completed rows. Dark
mode needs an update. Mockups to be sent for deliberation.

### Subs view — Lexi

All subcontractors, what they're doing, every job they're assigned to, with
paid/not-paid status. Minimum viable is a paid yes/no flag on the release; the
tab is what she actually wants. QuickBooks integration later. Ships to Lexi and
Bill together, rough v1, feedback by email.

**Hard dependency:** only as good as installer/sub assignment in the job log,
which some PMs do and some don't. The tool has to exist before the discipline
can be enforced.

---

## 5. How the shop actually works

Institutional knowledge captured from the meetings — the material that isn't
written down anywhere else.

**The parts sheet is a manual count.** A drafter goes through the prints,
counts, and fills an Excel cover sheet, built pre-FC in the gap between DRR and
FC — the last thing submitted before FC. Things on the prints don't always make
the sheet: closed risers exist on the drawing and have a fab drawing, but miss
the sheet and get missed downstream. *"Happens more than it should"* — roughly
every six months.

**Hardware is the worst recurring failure.** *"Hardware kills us."* Counting
tech screws, nuts, and bolts by hand off drawings that often don't call them
out.

**Implicit standards live in people's heads.** A saddle clip takes two tech
screws every time, but the drawing just shows holes. FP42.5 is a 4×4 base plate
with two ½" holes. Hole geometry implies hardware: 2-hole ≈ 90% Titans
(concrete); 4-hole with ½" ≈ lags (wood); 7/16 for a lag, ½ for a Titan, though
sometimes ½ for lags too. Already submitted to the KB as "MHMW 101."

**Only PMs are project-scoped.** Everyone else touches every project. Fox Hill
is currently the exception that proves it — Rourke is the only one who's worked
on it, and everyone else will once it moves.

**Drafting can't be scheduled like fab.** Fab is cut and dry hours-per-week;
drafting is start/stop across many jobs. A drafting timeline view isn't useful
yet — it'd be one item sitting alone in a week.

**Stage timing data is only credible within a stage.** Start→complete pairs
inside a single stage are real; the gap between stages is parts sitting on the
floor waiting for a fabricator. That gray area is why naive cut-start-to-fit-up
numbers looked wrong.

### Estimates validated against tracked data

| Stage | Team estimate | Data |
|---|---|---|
| Sub → GC | 8 weeks | **9 weeks** |
| DRR | 15 business days | **18 days** (possibly outlier-driven) |

Close enough that averages are stable enough to build a DRR timeline from.

---

## 6. Pain points

| Pain point | Who absorbs it | Current workaround | Source |
|---|---|---|---|
| Sub presence is discovered by invoice | Lexi | None — information arrives after the risk is taken | Lexi 7/22 |
| A sub worked an OCIP project unenrolled | MHMW (compliance exposure) | Named incident, already happened | Lexi 7/22 |
| Sub invoice verification depends on flawless manual QuickBooks entry | Lexi | *"usually happens, but sometimes doesn't"* | Lexi 7/22 |
| Parallel manual approval forms | Lexi | Maintained by hand | Lexi 7/22 |
| Billing photo hunt | Katie | Walks the shop with a stack of papers, photographing work she often can't identify | Bill 7/22 |
| Installers have no time to do invoicing | Installers | *"They're treadmill-y"* — needs a one-button "ready for invoice" | Bill 7/22 |
| Sub/DRR/FC unlinked in Procore | Drafters, PMs | Manual hunting | Bill 7/22 |
| One workflow template in Procore | Everyone creating submittals | A giant list, click the right PM with the right drafter | Bill 7/22 |
| Procore changed its entire UI mid-day, unannounced | Drafters | Multiple people immediately lost My Open Items | Bill 7/22 |
| Procore had ~10h of webhook downtime, unannounced, status page never updated | Daniel | Read as an MHMW problem | Bill 7/22 |
| Unlimited green dates on any date | Shop | *"Right now I can put unlimited green dates on tomorrow. Never going to happen."* | Bill 7/22 |

---

## 7. Action items

| Item | Owner | Due | Status |
|---|---|---|---|
| First T&M version to start tracking | Daniel | **2026-07-27** | committed |
| Figure out how to pull our data out of Procore before October | **unowned** | before Oct | **open — no plan** |
| Send the change order log (Excel) for backfill | Bill | — | open |
| Send a sample change order email | Bill | — | open |
| Send the updated projects-page markdown build | Bill | — | open |
| Send the parts page / "brain stem" Excel sample | Bill | — | open |
| Provide Carmen avatar + decide on the email | Bill | — | open |
| Investigate access to customer-owned Procore data | Daniel | — | open |
| Send job log color mockups | Daniel | — | open |
| Fix dark mode | Daniel | — | open |
| Improve `/admin/metrics` load times | Daniel | — | open |
| Write the Chrome desktop-notification training doc | Daniel | — | open |
| Make sure everyone's on Chrome | Bill | — | open |
| Exclude stage-jumping releases from capacity data | Daniel | — | open |
| Rework the stage weighting system given the analysis | Daniel | — | open |
| Talk to Louie about the fab capacity model | Bill | — | open |
| Schedule a working session on the full submittal workflow | both | — | open |
| Add the AI steps to the lifecycle flowchart | Bill | — | open |
| See how Banana Boy generates a parts list | Daniel | — | open |
| Build the subs view (rough v1), deliver to Lexi and Bill | Daniel | after in-flight sub work | open |

---

## 8. Adoption signals

Worth tracking separately from scope, because they change what's worth building.

- **Nobody used mentions all week** (from `/admin/metrics`). Bill read it as a
  training gap, not a feature failure: *"this is a flag, this is an opportunity,
  guys it's time for a little training."*
- **Desktop notifications are the proposed fix** — opt-in Chrome notifications
  so a mention surfaces like a Teams message. *"You could mention someone and
  they might not see it for a week."*
- **Photos are already paying off** before the gating features exist — Katie's
  billing workflow is the concrete case.
- **Gating stage advancement on a photo** is wanted but deliberately deferred
  until the crew are power users.
- **The old job log is not missed.** *"Haven't had that moment?" "No, not at
  all."*

---

## Source meetings

| Date | Meeting | Transcript (local) | Findings |
|---|---|---|---|
| 2026-07-22 | Ops / roadmap review | `~/Desktop/Transcripts/MHMW/Bill-7-22-2026.txt` | `processed/Bill-7-22-2026.md` |
| 2026-07-22 | Sub invoicing & OCIP gap | `~/Desktop/Transcripts/MHMW/Lexi.txt` | `processed/Lexi.md` |
