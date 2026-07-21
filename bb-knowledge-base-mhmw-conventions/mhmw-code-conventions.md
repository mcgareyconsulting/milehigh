# MHMW Code Conventions — Stairs, Guards, Handrails, Fall Protection

MHMW's **applied build standard**: how the shop dimensions stairs, guards, and
handrails to satisfy code, including the shop's own tolerances and preferences.

This is the company-specific *convention* layer that sits **on top of** the generic
code reference in [`../bb-knowledge-base-division-05-metal-codes/`](../bb-knowledge-base-division-05-metal-codes/division-05-misc-metals-knowledge-base.md)
(IBC 2021 / ADA 2010 / AISC / AWS). Where the two differ, the division-05 KB gives
the *code minimum*; this file gives what MHMW actually builds to. When both apply,
MHMW's tighter value governs the shop drawing.

Sources: `Code Requrements.pdf`, `Codes and Fasteners.pdf` (pp. 1–3), `MHMW 101.pdf` (p. 3).

---

## Single-Family Dwelling (SFD) vs. Multi-Family Building (MFB)

The governing values differ by occupancy. **Always establish SFD vs. MFB first** —
most of the numbers below split on it.

| Requirement | Single-Family Dwelling | Multi-Family Building |
| :--- | :--- | :--- |
| Landing guardrail height (min, AFF) | 36½" | 42½" |
| Stair stringer rise | 7¾" max | 4"–7" |
| Stair stringer run (min) | 10" | 11" |
| Tread overhang (nosing) | ¾"–1¼" (no overhang needed if run > 11") | 1¼" max |
| Handrails required when | 4 or more rises; ramp slope > 1"/ft (8.33%, 4.8°) | 2 or more rises; ramp overall rise > 6" |

> **MHMW "Reduce By ¼" " standard:** stated heights are built slightly tighter than
> the code minimum (e.g. a 42½" guard target already includes MHMW's margin over the
> 42" code minimum). On a drawing, `[42½"]` in brackets is the MHMW build value for a
> ">42"" code requirement.

---

## Guardrails (Guards)

- **When required:** where a potential fall is higher than 30", **or** within 36" of
  a 30" fall.
- **Fall-protection geometry:** fall protection is **needed** where the grade/floor
  drops **more than 30" vertically within 36" horizontally** from the edge. If the
  grade/floor does **not** drop more than 30" within that 36" horizontal band, fall
  protection is **not** needed (grade may keep dropping farther out).
- **Sphere test:** the guard infill cannot allow passage of a **4" sphere**.
- **Graduated opening limits (MHMW):**
  - `0"–36"` above walking surface → **< 4"** max opening
  - `36"–42"` above walking surface → **< 4⅜"** max opening

  > **Discrepancy note (band boundary):** IBC 2021 §1015.4 draws its opening band at
  > **34"** (4" sphere up to 34"; larger allowed above), and the division-05 KB states a
  > flat 4" limit all the way to guard height. MHMW's chart uses a **36"** boundary with
  > 4⅜" above — stricter than IBC in the 34"–36" band, slightly looser than the
  > division-05 flat-4" simplification in the 36"–42" band. **MHMW's chart governs shop
  > practice**; treat a 4"–4⅜" opening at 36"–42" as compliant per MHMW standard.
- **Balcony vs. patio rail:** a balcony rail (above grade level) and a patio rail (at
  grade level) are distinguished by whether the guarded surface is above or at grade.
- Landing guardrail heights: **36½" min (SFD) / 42½" min (MFB)** AFF; the `>42" [42½"]`
  callout is the MFB build value.

---

## Handrails

Height band 34"–38" AFF in every context; **MHMW build target is [36"]**.

Three handrail contexts, each with distinct rules:

1. **Wall handrail (on a stair wall)** — 34"–38" AFF. Required on **only one** side of
   the stairs, aligned with the direct path of travel. Does **not** need extensions past
   the top/bottom treads, but must end at least at the vertical of the top and bottom
   nose. Min **1½" clearance** from any object.
2. **Grab rail (on a guardrail)** — 34"–38" AFF, with **13" extensions** past the top
   tread and 13" past the bottom tread. Required on **both** sides of the stairs, with
   the **center grab rail continuous** between flights. Min **1½" clearance**.
3. **Site rail (not at a stair/guard)** — same 34"–38" AFF band; standalone site
   handrail, not part of a stair or guard system.

- **Handrail extensions:** 12" min at top and bottom (MHMW builds **[13"]**), **unless
  continuous** with the handrail above/below across a landing.
- **Return:** handrails must return to wall / guardrail / floor (¼" gap max) unless
  continuous.
- **Grab-rail-to-wall clear width** must be equal to or greater than the stair clear
  width (guard rail to wall ≥ stringer-to-stringer clear width).
- **When required (MFB):** at 2 or more rises; at any ramp where overall rise > 6" and
  slope ≥ 5% (2.86°). A **single rise = handrail not needed**.

  > **Discrepancy note (ramp trigger):** the SFD/MFB table gives the MFB ramp trigger as
  > "overall rise > 6"" alone, while the site-handrail sheet adds "**and** slope is 5%
  > (2.86°) or greater". Read the 5% as the threshold at which a sloped walk *is* a ramp
  > (ADA's 1:20), and the >6" rise as the handrail trigger — both conditions apply. The
  > SFD column's separate "slope exceeds 1"/ft (8.33%)" is the steeper IRC
  > single-family threshold, not a conflict.

---

## Stair Geometry (MFB build standard)

- **Rise:** 4"–7" (MHMW builds ~6⅞").
- **Run:** 11" min. **MHMW preference: run 11-1/16" min**, to guarantee the 11" clear
  minimum is maintained after tolerances.
- **Rise uniformity:** rise height may not vary more than **⅜" in a single flight**.
- **Tread slope:** treads can slope **no more than ¼"/ft in any direction**.
- **Headroom:** **80" (6'-8") minimum** headroom clearance.
- **Max flight height:** 144" (12') max floor-to-floor before an intermediate landing.
- **Tread / riser construction (typ.):** **2¼" × 12" precast tread** (other sizes
  available) on a **standard tread clip**, over a **16 ga. closed riser** ("16 Ga.
  Closed Riser Plan"). Nose/heel per the tread-transition detail.
- **Stringer-to-wall fit-up:** **¼" gap** between stringer and wall, both sides (per
  the plan/section detail on the codes sheet).

> **Un-interpreted annotation (confirm with the shop):** the stair section on the
> codes sheet also carries `36"` and `<27"` vertical dims alongside the "80\" Min
> Headroom Clearance" callout under the stair. This is consistent with an under-stair
> protruding-object / cane-detection barrier convention (ADA: leading edges between
> 27" and 80" AFF are protruding objects; FP3 is the *cane rail* footpad), but the
> sheet doesn't state the rule. Not distilled into prompt rules until confirmed.

> **Terminal-rise caution (cross-reference):** the uniform riser schedule is only
> trustworthy where each flight terminates as the schedule assumes. Compute the
> terminal (first) rise independently as `terminal_clip_rise + tread_thickness` (MHMW
> standard precast tread = 2¼") and compare to the 7" max. See the
> `stair-terminal-rise-over-max` rule in `app/brain/pdf_review/rules.py`.

---

## Quick reference — hard limits

| Item | Limit |
| :--- | :--- |
| Guard required | fall > 30", or within 36" of a 30" fall |
| Fall protection trigger | grade drops > 30" vertically within 36" horizontally |
| Guard opening (0"–36") | < 4" |
| Guard opening (36"–42") | < 4⅜" |
| Sphere test | 4" sphere cannot pass |
| Rise (MFB) | 4"–7" |
| Run (MFB) | 11" min (MHMW: 11-1/16") |
| Rise variance / flight | ⅜" max |
| Tread slope | ¼"/ft max, any direction |
| Headroom | 80" min |
| Handrail height | 34"–38" AFF |
| Handrail extension | 12" min (MHMW: 13"), unless continuous |
| Handrail clearance | 1½" min from any object |
| Max flight (floor-to-floor) | 144" (12') |
