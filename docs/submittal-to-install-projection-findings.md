# Projecting Install Dates from the Submittal Pipeline — Findings & Recommendation

**Prepared for:** Mile High Metal Works
**Date:** May 25, 2026
**Status:** Feasibility review (based on live production data, ~11 weeks of tracked history)

---

## The question

Today the Job Log projects a **Start Install** date for every release that's already in the fab queue. The furthest-out release sets the end of our visible install horizon.

You asked whether we can push that horizon further back — estimating install dates for work that hasn't become a release yet, while it's still moving through the **submittal pipeline**. If we can, the schedule stops "ending at the last release" and starts reflecting what's actually coming down the drafting pipe.

We reviewed the submittal and submittal-history data to see what's actually supportable. Short answer: **yes for the last stage, not yet for the earlier ones.**

---

## How the pipeline actually works in the data

Every scope of work moves through three submittal phases before it becomes a release:

```
   Drafting Release       Submittal for          For Construction        Job Log
   Review (DRR)    ──▶    GC Approval (GC)  ──▶   (FC)             ──▶    Release
   ~39 open               ~122 open               ~128 open
```

An important detail we confirmed: these are **three separate records in Procore, not one record changing phase.** A new submittal is created at each phase. The For-Construction record — and the matching Job Log release — is only created once the scope reaches the For-Construction phase. That's exactly why a release lines up with FC: the release is *born* at FC.

There are roughly **290 open submittals** spread across the three phases right now — real inventory that will turn into releases and, eventually, installs.

---

## What we can estimate with confidence: FC → Release

The handoff from **For Construction to a Job Log release is a clean, well-behaved gate.** Two things make it trustworthy:

1. **The stage is clean.** A For-Construction submittal follows a simple path (Open → Closed). Out of 411 For-Construction submittals, only **one** ever took a messy, back-and-forth path. The rest are orderly.

2. **The timing is tight and consistent.** From the moment a For-Construction submittal closes to when its release appears, the lag is:

   | | Typical | Average | Most cases within | Longest seen |
   |---|---|---|---|---|
   | FC closes → release created | same day | **~3 days** | ~6 days | ~4 weeks |

That ~3 day average is small and stable enough to **reverse-engineer a release date** the moment a submittal flips to For Construction. In plain terms: *when a submittal becomes For Construction, we can reasonably predict its release date, then feed that into the existing scheduling math to project a Start Install date* — extending the horizon beyond today's last release.

This alone is a meaningful win: it gives the install schedule a forward look for the ~128 scopes currently sitting in For Construction.

---

## What needs tightening first: the earlier stages (DRR & GC)

To project install dates for work further upstream — submittals still at Drafting Release Review or GC Approval — we'd need to know how long a scope takes to travel *through* those earlier gates. **The data can't tell us that reliably yet**, for one structural reason:

- Because each phase is a **separate Procore record with no shared ID linking them**, we can't reliably follow one scope from DRR → GC → FC. When we tried to match them up by project and title, only about **9% of scopes** lined up cleanly — about 112 of roughly 1,290 scopes (titles get reworded or contain typos between phases). We can see the phases as *piles of inventory*, but we can't trace a single piece of work across all three gates.

So the earlier stages give us a rough sense of backlog volume, but not dependable per-submittal timing. Projecting install dates that far back today would mean wide error bars we wouldn't want to put in front of the field.

### How to tighten it
The fix is about cleaning up the upstream stages so each gate is as clean as the FC gate already is. Likely paths:

- **Find or add a linking field in Procore** — a spec section, package number, or parent-submittal reference that ties the three phases of one scope together. If that field already exists in Procore, the entire funnel becomes traceable and we can measure true stage-to-stage timing.
- **Tighten stage discipline** — consistent titling and status hygiene through DRR and GC so the phases connect automatically.
- **Accumulate more history** — our current view is roughly an 8-week window of staging data. More months of clean history sharpens every estimate.

---

## Recommendation

1. **Build the FC → Install projection now.** It rests on a clean gate and a stable ~3–4 day handoff. This extends the Job Log's install horizon to cover everything currently in For Construction, with honest, defensible dates.

2. **Treat DRR/GC as a "further-out backlog" indicator** for now — show the volume coming, but don't promise dates we can't back up.

3. **Decide on upstream linkage.** If Procore carries a field that ties a scope's three submittals together, we can extend clean stage-gate timing all the way back to Drafting Release Review — turning the whole funnel into a reliable forward schedule.

---

## Caveats (so the numbers are read correctly)

- Findings are based on **live production data**, about **11 weeks** of tracked history (mid-March through late-May 2026). More months of history will continue to sharpen the numbers.
- The ~3 day FC→release figure comes from the subset of releases created *within* our tracking window (about 50–100 clean pairs); it's directionally solid and consistent with our earlier staging read, but worth re-confirming as more history accrues.
- "When a release was created" is inferred from its first recorded change, since releases don't carry an explicit creation timestamp. This is a reasonable proxy, not an exact clock.

---

*Next step on our end: prototype the For-Construction → Start Install projection against the sandbox so your team can eyeball the dates before we commit it to the live Job Log.*
