# BB Rules Reference — What Banana Boy Checks and Works From

**For:** MHMW shop, drafting, and management
**Purpose:** This is the single source of truth for the rules BB (Banana Boy) uses when
it reviews drawing sets and answers questions. Every rule below came from MHMW's own
documents. **If anything here is wrong, outdated, or missing — mark it up.** Corrections
to this document get built into BB.

**Status key:**
- ✅ **Confirmed** — taken directly from your documents, no interpretation needed
- ⚠️ **Interpreted** — we filled a gap or resolved a conflict between documents; check our reading
- ❓ **Open question** — BB is NOT acting on this yet; needs an answer from the shop

**Source documents** (from the knowledge packet, kept in `source-pdfs/`):

| Short name | File | Pages |
| :--- | :--- | :--- |
| CODE TABLE | `Code Requrements.pdf` | 1 |
| CODE SHEETS | `Codes and Fasteners.pdf` | 4 |
| MHMW 101 | `MHMW 101.pdf` — compilation: pp. 1–2 = abbreviations/lumber, p. 3 = CODE TABLE, pp. 4–7 = CODE SHEETS | 7 |
| PARTS BOOK | `Typical parts.pdf` — drawing F\<N\> = page N | 25 |
| FOOTPADS | `Typ. Footpad Drawings.PDF` | 5 |
| DRR FLOW | `DRR Work flow.pdf` | 1 |
| SUBMITTAL FLOW | `Submittal for GC workflow.pdf` | 1 |

---

## 1. Open Questions — Please Answer These First

These are the items where your documents were unclear, incomplete, or disagreed with
each other. BB either guessed conservatively or left the item out until someone confirms.

### ❓ Q1. Guard opening limits — where does the band start: 34" or 36"?

> **Source:** CODE SHEETS pp. 1–2 (= MHMW 101 pp. 4–5), "Opening Limitations" box

Your "Opening Limitations" box says:

> 0"–36" = <4" max opening
> 36"–42" = <4⅜" max opening

The 2021 IBC draws this line at **34"**, not 36". Our other code reference says flat
4" all the way up. **We told BB your chart governs** (4" up to 36", 4⅜" from 36"–42").

**→ Is the 36" boundary intentional (your standard), or should it be 34"?** _______

### ❓ Q2. Under-stair dimensions — what do the `36"` and `<27"` callouts mean?

> **Source:** CODE SHEETS p. 1 (= MHMW 101 p. 4), stair section, dims below the
> stringer next to the "80" Min Headroom Clearance" callout

The stair section shows `36"` and `<27"` dimensions under the stair, next to the
80" min headroom note. Our best guess: this is your under-stair barrier rule (ADA
treats anything with a leading edge between 27" and 80" off the floor as a
head-strike hazard, and a cane rail below 27" fixes it — you have a cane-rail
footpad, FP3 on FOOTPADS p. 1). **BB is not checking anything based on these dims yet.**

**→ What is the rule here, in one or two sentences?** _______

### ❓ Q3. Missing supplier part numbers

> **Source:** PARTS BOOK p. 23 (sheet F23) and p. 25 (sheet F25) — both say
> "Ordered Part ###" with the number never filled in

| Sheet / page | Part | Supplier / part # |
| :--- | :--- | :--- |
| F23 (PARTS BOOK p. 23) | Typ. Spring Closure | **?** _______ |
| F25 (PARTS BOOK p. 25) | Cane Bolt Assembly (18") | **?** _______ |

### ❓ Q4. Ramp handrail trigger — one condition or two?

> **Sources that disagree:**
> - CODE TABLE p. 1 (= MHMW 101 p. 3), Multi-Family column: "when overall rise of
>   ramp exceeds 6"" — rise only
> - CODE SHEETS p. 3 (= MHMW 101 p. 6), site-handrail sheet "When Required" box:
>   "At Any Ramp Where Overall Rise Is Greater Than 6" **and slope is 5% (2.86°) or
>   greater**" — rise **and** slope

We told BB: both conditions (5% is what makes it a "ramp" at all; over 6" of rise is
what triggers the handrail).

**→ Is that right?** _______

---

## 2. Stair Rules (Multi-Family unless noted)

> **Sources:** CODE TABLE p. 1 (= MHMW 101 p. 3); CODE SHEETS p. 1 stair elevation +
> Detail A (= MHMW 101 p. 4). S9 comes from BB's review history, not this packet.

BB checks every stair flight in a For-Construction set against these:

| # | Rule | Value | Status |
| :--- | :--- | :--- | :--- |
| S1 | Riser height | 4" min – 7" max (typ. build ~6⅞", CODE SHEETS p. 1 Detail A) | ✅ |
| S2 | Tread run | 11" min — **MHMW builds 11-1/16" min** so 11" clear survives tolerance (CODE TABLE p. 1 note; CODE SHEETS p. 1 Detail A) | ✅ |
| S3 | Tread overhang (nosing) | 1¼" max (CODE TABLE p. 1) | ✅ |
| S4 | Rise variation in one flight | ⅜" max (CODE TABLE p. 1; CODE SHEETS p. 1 Detail A box) | ✅ |
| S5 | Tread slope | ¼" per foot max, any direction (CODE TABLE p. 1; CODE SHEETS p. 1 Detail A box) | ✅ |
| S6 | Headroom | 80" (6'-8") min (CODE TABLE p. 1; CODE SHEETS p. 1) | ✅ |
| S7 | Max flight height | 144" (12') floor-to-floor before a landing (CODE SHEETS p. 1 stair elevation) | ✅ |
| S8 | Typical tread construction | 2¼" × 12" precast tread on standard tread clip, 16 ga. closed riser (CODE SHEETS p. 1 Detail A) | ✅ |
| S9 | **Terminal rise check** | Where a flight lands on an existing pad/slab (no pour), BB computes the first rise itself: terminal clip rise + tread thickness (2¼" typ.) — and flags it if over 7". The riser schedule alone is not trusted there. | ✅ (proven on job 590-674) |
| S10 | Stringer-to-wall gap | ¼" both sides (CODE SHEETS p. 1 plan section) | ✅ |
| S11 | Single-family differs | SFD: 7¾" max rise, 10" min run, ¾"–1¼" overhang (CODE TABLE p. 1, Single-Family column). BB establishes single- vs multi-family before applying limits. | ✅ |

## 3. Guard (Guardrail) Rules

> **Sources:** CODE TABLE p. 1 (= MHMW 101 p. 3); CODE SHEETS pp. 1–2 (= MHMW 101
> pp. 4–5). G6 comes from the Division 05 industry-code reference, not this packet.

| # | Rule | Value | Status |
| :--- | :--- | :--- | :--- |
| G1 | When a guard is required | Fall over 30", or within 36" of a 30" fall (CODE TABLE p. 1) | ✅ |
| G2 | Fall-protection geometry | Needed where grade/floor drops **more than 30" vertically within 36" horizontally** of the edge; not needed if the drop within that 36" band stays under 30" (CODE SHEETS p. 2 diagrams) | ✅ |
| G3 | Landing guard height | **42½" min** (multi-family build value; code min 42") · 36½" min single-family (CODE TABLE p. 1; CODE SHEETS p. 2 ">42" [42½"]" callout) | ✅ |
| G4 | Opening limits | 0"–36": under 4" · 36"–42": under 4⅜" (CODE SHEETS pp. 1–2 box) | ⚠️ see **Q1** |
| G5 | Stair triangle | The triangle at riser/tread/bottom rail may pass up to a 6" sphere (industry standard) | ✅ |
| G6 | Loads | 50 lb/ft along top rail, and separately a 200 lb point load anywhere — BB looks for post spacing/anchor details that can't show this (Division 05 reference) | ✅ |
| G7 | "Reduce by ¼" | Bracketed values on drawings (e.g. [42½"]) are MHMW build targets sitting ¼"+ tighter than code minimums ("MHMW Std. Reduce By ¼"", CODE SHEETS pp. 1–2) | ✅ |

## 4. Handrail Rules

> **Sources:** CODE TABLE p. 1 (= MHMW 101 p. 3); CODE SHEETS pp. 1 & 3 (= MHMW 101
> pp. 4 & 6). H8 comes from the Division 05 industry-code reference.

| # | Rule | Value | Status |
| :--- | :--- | :--- | :--- |
| H1 | Height | 34"–38" above nosing/floor — **MHMW build target [36"]** (CODE SHEETS pp. 1, 3) | ✅ |
| H2 | Wall handrail (stair wall) | One side only, direct path of travel; no extensions required but must end at least vertical of top/bottom nose; 1½" min clearance (CODE TABLE p. 1; CODE SHEETS p. 1 section) | ✅ |
| H3 | Grab rail (on guardrail) | Both sides; 13" extensions past top and bottom tread; center rail continuous between flights; 1½" min clearance (CODE TABLE p. 1; CODE SHEETS p. 1) | ✅ |
| H4 | Extensions | 12" code min — **MHMW builds [13"]** — unless continuous with the rail above/below (CODE SHEETS pp. 1, 3 "12" Min [13"]") | ✅ |
| H5 | Returns | Must return to wall/guardrail/floor, ¼" max gap, unless continuous (CODE SHEETS pp. 1, 3) | ✅ |
| H6 | Clear width | Grab-rail-to-wall must be ≥ stair clear width, stringer to stringer (CODE SHEETS p. 1 plan) | ✅ |
| H7 | When required | 2+ rises (single rise = no handrail, CODE SHEETS p. 3); ramps per **Q4** · single-family: 4+ rises (CODE TABLE p. 1) | ⚠️ see **Q4** |
| H8 | Graspability | Round rail OD 1¼"–2"; non-round perimeter 4"–6¼" (Division 05 reference) | ✅ |

## 5. Fastener Rules — the fastener must match the material it goes into

> **Sources:** CODE SHEETS p. 4 fastener chart (= MHMW 101 p. 7); PARTS BOOK p. 2
> (sheet F2) for the footpad substrate callouts.

BB flags any detail whose fastener doesn't match its substrate.

| Goes into | Correct fastener | Hole oversize |
| :--- | :--- | :--- |
| **Wood** | Lag screw · Simpson SDS (¼"Ø only) | 1/16"–⅛" · 1/16" |
| **Steel** | Self-tapping / Tek screw | 1/16" |
| **Concrete / masonry** | Simpson Titen HD · wedge anchor | ⅛" · 1/16" |
| **Drywall** | Toggle bolt | 1/16"–⅛" |

Applied to your standard parts:

- **FP42.3 / FP44.3** footpads = SDS = **wood** mount · **FP42.5 / FP44.5** = Titen HD/lag = **concrete** mount ("Mounting Material Typ." on PARTS BOOK p. 2, sheet F2) ✅
- **TCS** tread clip **welds** to steel stringers (PARTS BOOK p. 7, F7) · **TCW** **bolts** to wood stringers (p. 8, F8) — swapped is a defect ✅

## 6. Standard Parts BB Recognizes

> **Sources:** PARTS BOOK pp. 1–25 (sheets F1–F25); FOOTPADS pp. 1–5.

BB reads these codes on drawings:

- **Footpads** (F1–F3; FOOTPADS pp. 1–5): FP3, FP42.3, FP44.3, FP42.5, FP44.5 — `.3` = SDS/wood, `.5` = Titen-or-lag/concrete
- **Saddle clips** (F12–F20): SC15.3/.5 (1½" tube), SC2.3/.5 (2" tube), `-B` = bottom, CSC = corner
- **Stringer plates** (F6): SPB (bottom, ½"Ø wedge/lag), SPT (top, ¾"Ø lag/Titen/through) — two-part sheet
- **Tread clips** (F7–F8): TCS (weld-on, steel), TCW (bolt-on, wood)
- **Rail brackets** (F4–F5, F9–F11): WM-RD, GR-RD (pipe), GR-SQ (square/rect tube), bent saddles for 1½" tube
- **Gate hardware** (F21–F25): 4" HD hinge, Keedex lock box, spring closure (**Q3**), gravity latch + bar catch, 18" cane bolt (**Q3**)

## 7. Reading Conventions BB Uses

> **Sources:** MHMW 101 pp. 1–2 (= `Abbreviations and Lumber.pdf` pp. 1–2);
> DRR FLOW p. 1 for print labeling.

- Abbreviations per MHMW 101 p. 1 (TS, HSS, TOS/BOS, TOC/BOC, AFF, UNO, T&B, WHR, LHU/RHU, …)
- Dimensional lumber is smaller than nominal (2×4 = 1½"×3½"); engineered lumber (LVL/Glulam) is true-to-nominal (MHMW 101 p. 2)
- Ledger = fastened to building; lintel = bears on brick, not fastened (MHMW 101 p. 1)
- Fabrication prints = "F" pages, erection prints = "E" pages; Release # on every print (DRR FLOW p. 1)
- Weld symbols: BB reads standard AWS symbols (reference charts kept in the office — `Weld Symbol Chart 1.pdf`, `Weld Symbol Simplified.pdf`; not part of BB's rulebook)

## 8. Process Knowledge BB Uses (for questions, not drawing review)

> **Sources:** SUBMITTAL FLOW p. 1; DRR FLOW p. 1.

- **Submittal path** (SUBMITTAL FLOW): Arch + structural drawings + quote → submittal → Procore workflow → PM distributes to GC/Architect/Structural → returned submittal
- **DRR path** (DRR FLOW): returned submittal + field measurements → drawings → Job Start doc creates the **Release #** → Drafting Cover Sheet + PDFs to Procore → revise-and-resubmit / approved-as-noted / approved → **FC Release**
- Cloud all major changes and RFIs on submittals; complete submittals are critical (SUBMITTAL FLOW)

---

## 9. How to Change These Rules

1. Mark up this document (paper or PDF) — cross out, correct, add.
2. Get it back to Daniel. Changes go into BB's rulebook, and this document is reissued
   so it always matches what BB actually does.
3. New failure modes are welcome: "we've made this mistake before" in a couple of
   sentences is enough to become a BB check.

| Rev | Date | Change |
| :--- | :--- | :--- |
| 1 | 2026-07-20 | First issue, from the bbknowledge_03 packet + existing BB rules. Source citations added; dropped an erroneous sheet-numbering question (SPB/SPT correctly share sheet F6). |
