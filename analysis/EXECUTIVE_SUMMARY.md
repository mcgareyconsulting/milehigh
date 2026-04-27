# Operations Data — Executive Summary

**Prepared for COO review · Drafting and Shop Flow Analysis**
**Window analyzed:** 5 months (November 2025 – April 2026)

Two separate datasets, same workforce: ~1,300 submittals through drafting and ~750 releases through the shop.

---

## The Headline

The team's **throughput has roughly tripled** in five months (17 → 53 per week on submittals; 17 → 42 per week on shop closures), but **cycle time has not improved proportionally**. We are shipping more by working harder and on larger volume, not faster. There are three concrete, addressable reasons why — none of them require hiring or systems changes to start moving.

---

## Three Issues to Act On This Quarter

### 1. The cycle-time bottleneck is shipping, not the shop. Most leaders assume the opposite.

Median time from "Released" to "Complete":

- **All in-shop fabrication steps combined (Cut → Fit → Weld → Paint): ~6 days**
- **Storage and shipping tail (Store at MHMW + Shipping Completed): ~26 days**
- **Two-thirds of total cycle time happens *after* fabrication is done.**

The shop is genuinely fast. The post-fabrication handoff is where work sits. Welded QC is the only in-shop stage with real dwell (5.3 days median, 12 days at the 75th percentile). On top of that, **19 releases were marked "Complete" then reverted to "Shipping Completed"** — a UI/data-flow bug that can be fixed in code.

**Short-term lever:** A focused review of the storage-to-ship handoff cadence, plus auditing the 19 reversions for the underlying bug. This is probably the single biggest cycle-time win available to the business.

---

### 2. The drafting queue is leaking work — not because drafters are slow, because items sit untouched.

- **100 open submittals have not moved in 30+ days. 49 over 90 days.** The shop side has 2.
- **First-touch latency: 5 days median, 11 days mean.** New submittals sit in their initial assignee's queue 5 days before *anyone* picks them up.
- **Items first-assigned to one of the senior drafters sit 13 days untouched** — nearly 3× longer than items first-assigned to the other (4.9 days). By the time the slower-to-touch drafter starts real work, the clock has run a week longer than his counterpart's.
- **Roughly 1 in 3 drafter turns is a return visit** (drafter → other → same drafter again). Some of this is legitimate QA bounce-back; some is "drafter needed information that should have been provided upfront."

**Short-term levers:**
- A single 4-hour stale-queue review meeting on the 100 oldest items would likely close, kill, or unblock 30+ of them.
- A "touch within 24 hours" intake SLA on new assignments would shave roughly 5 days off median cycle time without changing actual drafting speed.

---

### 3. One project — Outlook Green Valley Ranch — is dragging the whole organization's metrics.

This single project showed up at the bad end of *every* metric across both reports:

- **Largest project by release volume** (121 releases, 16% of total)
- **Second-slowest project lifespan** (52.6 days median, vs. 24 days on the fastest comparable project)
- **Leads submittal re-opens** (13 re-open events across 11 distinct submittals)
- **Three separate releases** in the regression-heavy top 10 list
- **Number-one stalest open submittal** plus multiple in the top 15
- **Multiple reworked items** appearing on stale-now lists

Whatever is happening with that project's general-contractor scope, intake quality, or contract structure is propagating into every downstream metric. The drafters and shop look slower than they actually are because Outlook Green Valley Ranch is in the denominator everywhere.

**Short-term lever:** A project-level retrospective on Outlook Green Valley Ranch is likely worth more than any per-drafter or per-stage intervention. Treat it as a case study, not background noise.

---

## Other Items Worth Knowing (Lower Urgency)

- **Volume asymmetry:** The lead drafter handles approximately 2× the volume of his counterpart in both stages, driven by the lead PM routing 58–64% of work to him. Not necessarily wrong — but if load balancing is desired, that's the lever (a routing pattern, not a coaching issue).

- **PM effect on cycle time differs by stage:** One PM's submittals close 2× slower than another's at the drafting stage. Once items hit the shop, all PMs converge at ~49 days. Whatever is happening pre-Released does not compound through fabrication.

- **Drafter speed gap is real but smaller than it feels:** On real drafting work (excluding quick triage), one senior drafter runs ~36% slower than the other. Through the shop, that gap shrinks to ~10%. Worth a coaching conversation, not a structural change.

- **Friday is the most under-used day** in the shop (78% drop from Thursday peak). Capacity already exists; it is a scheduling and expectation question.

- **Audit-logging gap:** 103 submittals are currently flagged HOLD, NEED VIF, or STARTED, but only 8 transitions have ever been captured in the audit trail. We cannot measure how long items actually sit in those flag states — likely a UI path that does not write to the audit table.

- **`collision_resolution_cascade` generates 42% of all priority changes.** Mostly automated noise, but worth confirming it is not producing user-visible queue instability.

---

## Suggested Next Research Passes

1. **Outlook Green Valley Ranch deep dive** — pull every event, every BIC change, every stage move for that one project and look for the pattern. (Probably the single highest-ROI follow-up.)

2. **Sample 20 of the 299 rework loops** to estimate what fraction are avoidable info-gap bounces vs. legitimate revisions. This quantifies the prize on tightening intake.

3. **Welded QC bottleneck** — pull the 17 stalest QC items and look for common cause (drafter, project, or item type).

4. **"Complete → Shipping Completed" 19 reversions** — trace in code; this is probably a quick fix.

5. **Re-run cycle-time numbers in 60–90 days.** The 5-month dataset is just barely enough for the per-drafter and per-PM cuts. Another quarter of data will firm up SLA-grade targets.

---

*Underlying data and supporting reports are available on request: initial submittals analysis (44-day window), expanded submittals analysis (5-month window), and shop-flow analysis (5.5-month window). Happy to drill into any of the above.*
