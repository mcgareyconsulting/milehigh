# Release Summary — May 23, 2026

A set of improvements went live today across the Job Log, Drafting Workload,
drawing markup, reporting, and the Procore integration. Highlights below are
grouped by the area of the app they affect.

---

## Scheduling visibility (Job Log)

**Start-install dates are now color-coded by schedule health.**
Instead of a flat red, the *Start install* cell tells you at a glance where a
release stands:

- **Red** — marked ASAP.
- **Green** — a hard date set for today or in the future (on track).
- **Yellow** — a hard date that has already passed (needs attention).

Formula-driven and empty dates keep their normal appearance. This makes
slipping schedules jump out without having to read every date.

## Install progress tracking (Job Log)

**Install progress now drives the install stages automatically.**
Entering a percentage in the *Install Prog* column moves a release into
**Install Start**; marking it complete (`X`) moves it to **Install Complete**.
The two are kept in sync both ways, so the stage and the progress column always
agree. "Install Complete" is now the dedicated finish marker for installation,
keeping it distinct from the general "Complete" stage and preventing accidental
cross-effects between the two.

## Drafting Workload restyling

The Drafting Workload board received a visual refresh, including smarter column
filters that size themselves to their contents for easier scanning and
selection.

---

## Drawing markup — shape tools

**The PDF markup tool now supports shapes.**
In addition to the existing pen and text annotations, you can now draw:

- **Lines, arrows, boxes, and circles**
- A **stroke thickness** control (Thin / Medium / Thick), shared by the pen and shapes
- A **Delete** button to remove a selected annotation

It's built for tablets: one-finger panning, two-finger pinch-to-zoom, and
large touch targets. All shapes save with the drawing and behave like any
other markup.

---

## Reporting & navigation

**Monthly invoicing report.**
A new monthly invoicing report is available to the accounting contact (and to
administrators), giving a focused view without needing full admin access.

**Hamburger navigation menu.**
Navigation was consolidated into a cleaner hamburger-style menu.

---

## Behind the scenes — Procore reliability

**A reconciliation safety net for Procore submittals.**
Procore occasionally sends rapid bursts of duplicate webhook notifications, and
on rare occasions a real change could be missed when those duplicates were
filtered out, or when Procore had not yet finished saving the update.

Every submittal notification now schedules a short follow-up re-check (about a
minute later) that re-reads the submittal directly from Procore and applies
anything the live notification missed. Repeated notifications collapse into a
single re-check, and any change that the safety net "rescues" is logged so it
can be reviewed. The result: ball-in-court, status, title, and submittal-manager
changes are far less likely to be dropped.

---

## Deployment

These changes were promoted through staging and released to production today.

| PR | Title |
|----|-------|
| #209 | Procore webhook reconciliation worker |
| #210 | Monthly invoicing report and hamburger menu |
| #212 | PDF markup shape tools |
| #213 | Start-install cell coloring by schedule health |
| #214 | Install start / install progress behavior |
| #215 | Drafting Workload restyling |
