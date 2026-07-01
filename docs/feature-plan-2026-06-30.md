# Feature Plan — Bill meeting, 2026-06-30

**Source:** `Transcripts/Bill.txt` (auto-transcribed) + Daniel's notes.
**Caveat:** the recording only captured the **back half** of the meeting, so this is
not the full picture. Add front-half items as they surface.

Each numbered workstream below is scoped to become its own feature branch. Suggested
branch names and progress checklists are inline. Status legend:
`PLANNED` · `BLOCKED` · `IN PROGRESS` · `SHIPPED`.

**Explicitly dropped from this plan** (captured in transcript, not being tracked here):
business/pricing model, job-log PDF print (fixed), equipment-rental (EquipmentShare)
integration, email ingestion (Dencol/Drexel/BB inbox). Dropped from the *plan doc* —
not from the codebase.

---

## 1. DWL release-number assignment + submittal_id coherence audit  `BLOCKED → audit first`

The DWL "Rel" column assigns a unique release number. We want to change how that
assignment works — but that change is **gated on understanding submittal_id
coherence**, so the audit is step one and everything else here waits on it.

### 1a. System audit — how is `submittal_id` tracked today? (do this first)
The concern: one logical submittal can **open and close / change type** over its life
(e.g. DRR → GC → FC), and we need to know whether our internal `submittal_id` stays
stable across those transitions or gets reassigned.

- [ ] Determine how `submittal_id` is currently stored/derived internally, and whether
      it is stable across a submittal's open/close cycles.
- [ ] Confirm behavior when two submittals share the **same description but differ in
      type** — do they collapse to one tracked id or diverge?
- [ ] Verify whether a type change (open/close) mutates the id we key on.
- [ ] Document the source of truth (Procore id vs. our row id) and any known
      divergence between the event log and the row.
- [ ] Produce a short findings write-up that the rest of §1 and §2 can build on.

### 1b. Due-date / start-install flow for ALL submittal types on DWL  `BLOCKED on 1a`
Implement the specific due-date / start-install date functionality flow on the DWL
across **all types** (not just the current subset). Blocked until submittal_id
coherence (1a) is proven, so a type change can't silently detach the dates.

- [ ] Define the flow per type once coherence is confirmed.
- [ ] Implement on the DWL for all types.

### 1c. "Split a release" (from transcript)
Origin: Flats @ Sandcrete — two stair cores were historically pulled as one release /
submitted together in one Procore. With release numbers now pulled here, that had to be
broken into west core / east core. Requested: a **split function** ("like splitting a
check" — split 1 release 3 ways → auto-assign the next available release numbers,
e.g. stair core 1/2/3).

- [ ] Open question: how does the split reconnect back to Procore?
- [ ] Auto-assign next-available release numbers on split (reuse §2 auto-pull logic).

**Branch:** `feature/dwl-release-assignment` (audit + 1b) — split may fork off later.

---

## 2. `+ Verbal Release` button on the Job Log  `PLANNED`

A quick-entry path for a part a PM is **pushing through before the drafting is done**.
Lets the user capture minimal info up front.

- [ ] New `+ Verbal Release` button on the Job Log.
- [ ] **Identical modal interaction** to the existing `+ Release` on the Job Log.
- [ ] **Identical form fields** to the separate/new-release button.
- [ ] **Auto-pull the next available release number** — same mechanism the DWL uses now
      (do not make the user pick it).

**Branch:** `feature/verbal-release`

---

## 3. PDF Mentions  `IN PROGRESS`

Ties to the existing PDF-mentions feature (per-drawing-version @mention comment threads).

- [x] Attachments button labels the **job + release number** (was bare "attachments").
      *Noted deploying same evening in the meeting — confirm shipped.*
- [ ] **Submit PDF to BB for review** — send a marked-up drawing to Banana Boy as a
      flagged item ("this is an error we found on this set — make sure it's not a legacy
      error going forward"). Example flag: stringers with >6"/>7" space at the last clip.
- [ ] Markup currently lives on the **comment / specific version**, not embedded in the
      PDF itself. Embedding in the actual PDF = bigger lift, **deferred** (current
      notify-on-comment approach is fine to start).
- [x] Name confirmed as **"PDF mentions"** (front end fine as-is).

**Branch:** `feature/pdf-mentions` (existing)

---

## 4. Job Log multi-field row edit  `PLANNED`

Editing a row (release #, install hours, fab hours) currently forces going in/out of the
3-dot menu **per field**. Want to **surface the full row and edit multiple fields at
once**. (Called "easy" in the meeting.)

- [ ] Surface the full row for editing.
- [ ] Allow multiple field edits in one interaction (no re-open per field).

**Branch:** `feature/joblog-row-edit`

---

## 5. DWL green-cell contrast  `PLANNED`

Green cells need **black text** — green-on-green was hard to read in the meeting,
especially on the DWL. (Bill called color his biggest item.)

- [ ] Green background → black text on the DWL date cells.

**Branch:** `feature/dwl-green-contrast`  *(small; could ride along with another DWL branch)*

---

## 6. J-View / Timeline  `PLANNED`

Merge the Trello board value into a **timeline view** in the app, driven by the dates we
already create in the Job Log / DWL.

- [ ] Timeline shows **6-digit job # + description**, bigger cards, **zoom in/out**.
- [ ] Drag cards **left/right** to shift ship dates.
- [ ] Expose **photos** on cards (shipping manifest / cover sheet) — scrollable.
- [ ] **Notes + photos merged into the events** on the timeline (see when each happened).
- [ ] Add **Shipping Planning**, **Shipping Complete**, and **Installers** to the timeline.
      Moving a card to Shipping Complete backtracks to the job log (Jay's flow: works only
      in the list, adds photos, moves to Shipping Complete).
- [ ] **Filters** to toggle Installers / Fab dept / Drawing dept. Purpose: spot
      clashes/overlaps for labor planning (see overloads → call overtime).
- [ ] **Drop the Board view.** Left nav becomes **Table + Timeline** (timeline on right).
- [ ] J-view also needs to cover meetings.

**Branch:** `feature/j-view-timeline`

---

## 7. iPad styling + Banana code  `PLANNED`

- [ ] **iPad styling pass** — Daniel to spend a day on-site with an iPad + Safari and fix
      iPad styling once and for all (Bill has a spare iPad).
- [ ] **Banana code overflow on iPad** — stretches past on iPad; table view doesn't work
      there (too much data). Push iPad users to **cards** or **auto**. Open question:
      default to **auto** except admin view?
- [ ] **Banana-code value review** — possibly drop or evolve. Options floated:
      expose only the current stage; admin button to "remove code and see how it works
      without it"; drop banana code in iPad mode only. Tension: keep the **tiling /
      cascading** effect (complete → less complete) people liked. Leaning: since everyone
      filters by department now, the cascade matters less; may go away to free room for
      **notes**.
- [ ] Mobile vs desktop stay as distinct views (cards win on phone, table doesn't).

**Branch:** `feature/ipad-banana-code`

---

## 8. Meetings / Banana Boy bot  `IN PROGRESS`

- [x] **Calendar auto-schedule** (built, in patch notes): invite **BB to a Teams
      meeting** → note-taker bot self-schedules to join at start; supports recurring, no
      manual link step.
- [ ] **Test:** forward the **Metro** meeting invite (tomorrow ~1:30) to `bb@mhmw.com`;
      verify it joins, adds to calendar, recognizes recurrence. Run tomorrow (prep time).
- [ ] **Lobby caveat:** may not auto-join depending on meeting owner — bot may sit in
      lobby; attendees must admit the note-taker (can object → kick).
- [ ] **AI dollars:** meeting extraction broke ("Louie's not in the meeting") when the $10
      budget ran out; job-log AI also ran out last week. Reload + add to next month's
      invoice. Consider a low-balance guard/alert so it fails loudly, not silently.
- [ ] **Job-site meetings:** put Banana Boy in PM job-site meetings; lowest bar = collect
      transcript + hand-tune, then connect Q&A back to data ("they asked about stair five →
      here's the status"). PMs have meetings this week to trial.
- [x] **Avatar research:** avatar-on-bot only works in org meetings + needs a separate
      flow → overkill; keep the plain "circle with BB in it."

**Branch:** `feature/meeting-bot` (existing calendar-recall work)

---

## Front-half gap (to fill in)

Recording started mid-meeting. Known references to earlier discussion not fully captured:
- The "meeting yesterday" where the green DWL date was hard to read.
- J-view was discussed previously by phone with Bill — Daniel wanted more clarification
  on scope/timeline (no demo yet).

Add front-half items here as recalled.
