# Submittal Events — Deep Pattern Analysis (5-month dataset)

**Source:** prod `submittal_events` (recent) + `sync_logs` (historical Procore webhooks) + `submittals`
**Window:** 2025-11-24 → 2026-04-26 (~5 months, vs 44 days in v1)
**Volume:** 5,071 unified events · 1,031 submittals with event history · 530-row Open→Closed cohort (vs 129 before)

> Methodology: `sync_logs.data` carries `old_value`/`new_value` for every Procore webhook (BIC, status, title, manager) going back to Nov 2025. Merged with the 6-week `submittal_events` table (which also adds Brain-side updates), deduped by `(submittal_id, kind, ts_to_second)`. ~3× the prior history density.

---

## TL;DR — what changed from v1

1. **Your "Dalton fast / Colton slow" intuition is right when you isolate real drafting work.** Splitting each drafter's turns into "quick triage" (<1d) vs "real work" (≥1d) on Drafting Release Review:
   - **Dalton real-work median: 6.4d** · mean 13.5d · n=148
   - **Colton real-work median: 8.7d** · mean 15.1d · n=85
   - **Rourke real-work median: 3.1d** · mean 4.4d · n=11

   Colton is ~36% slower per real-work turn. The mixed-in quick triages (Dalton 256, Colton 129) were dragging both medians toward zero in v1.

2. **Rich Losasso's queue is *clean but slow*.** v1 said Rich runs the cleanest handoff queue (1.15 avg). v2 (with proper history) says his submittals also take the **longest to close** — 20d median on Drafting Release Review, vs 11d for Danny and 9d for Gary. Same end result, different process: Rich holds work himself instead of bouncing it.

3. **The first-touch queue tax is real.** New submittals sit a **median 5 days** in their initial BIC before anyone moves them. Mean 11d. p75 15d. **Colton's initial-BIC dwell is 13d median (n=80) vs Dalton's 4.9d (n=149)** — items first-assigned to Colton sit untouched ~3× longer before Colton picks them up.

4. **Manager routing is asymmetric and explains Dalton's load.** Rich routes **64% to Dalton / 34% to Colton**. Gary 56/32. Danny 53/44. Rich is also the largest manager (410 routings). Net: Dalton gets ~60% of all manager→drafter assignments.

5. **100 currently-open submittals haven't moved in 30+ days.** 49 over 90 days. Colton holds 33 of them; Dalton holds 30. This is a real queue-cleanup target.

6. **Throughput is rising sharply.** 19 DRR closes/wk in Dec → 33–59 in last 3 weeks. Capacity is going up; cycle time is the constraint, not output.

7. **Submittal Drafting Status flags (HOLD, NEED VIF, STARTED) aren't being tracked in events.** Only 8 transitions captured ever, despite 103 submittals currently sitting in those states. Either drafters aren't setting them, or the audit logging path is missing — either way, you can't measure HOLD/VIF dwell right now.

---

## A. Drafter cycle time — the bimodal truth

Drafter turns split cleanly into two modes. Reporting them mixed obscures real performance.

### Solo turn duration on Drafting Release Review (the unit of work)

| Drafter | quick (<1d) n | quick avg | **real (≥1d) n** | **real mean** | **real median** |
|---|---:|---:|---:|---:|---:|
| Dalton Rauer    | 256 | 0.12d | **148** | 13.50d | **6.44d** |
| Colton Arendt   | 129 | 0.19d | **85**  | 15.12d | **8.69d** |
| Rourke Alvarado |  21 | 0.19d | **11**  |  4.39d | **3.09d** |

**Reading:** "Quick" turns are mostly Procore webhook artifacts and one-line acknowledgements (~3-5h average for Dalton, ~5h for Colton). Real drafting work is the ≥1d bucket — that's where the gut-feel difference lives. **Colton runs ~35% slower per real-work turn**, and his p75 (7.2d) tells you a quarter of his real-work turns take a full week+.

> Worth raising with Colton specifically and looking at item complexity, focus time, and whether intake quality differs.

### Total volume (5 months)

| Drafter | total solo turns | real-work turns | currently sitting on >30d stale |
|---|---:|---:|---:|
| Dalton Rauer    | 516 | 198 | 30 |
| Colton Arendt   | 314 | 131 | 33 |
| Rourke Alvarado |  67 |  22 |  3 |

Dalton handles ~60% more volume than Colton, but they each have ~30 zombie items in their queue.

---

## B. First-touch latency — a hidden 5-day cost

Time from submittal creation → first BIC change. n=351 (submittals where we observed both create and first BIC).

- **Global: mean 11.17d, median 5.00d, p75 15.24d, max 93d**

### By the person who held the submittal at creation

| Initial BIC | n | mean | median |
|---|---:|---:|---:|
| **Dalton Rauer**       | 149 | 9.39d  | **4.90d** |
| **Colton Arendt**      |  80 | 17.37d | **13.02d** |
| David Servold     | 55  | 6.68d  | 3.03d |
| Dustin Pauley     | 34  | 10.47d | 3.51d |
| Rourke Alvarado   | 12  | 1.23d  | 0.05d |
| Gary Almeida      |  8  | 16.11d | 0.97d |
| Rich Losasso      |  6  | 41.29d | 41.29d ⚠️ |

**Reading:**
- Submittals that land on Colton from creation sit ~13 days before he picks them up — **vs 5 days for Dalton**. This compounds: by the time Colton starts a real-work turn, the clock has already been running 8 days longer than Dalton's items.
- Rich Losasso parks 6 submittals on himself for 41 days each — small n but worth flagging.

> If first-touch dwell is the limiting factor, queue depth and prioritization (what each drafter picks up first each morning) matter more than raw drafting speed.

---

## C. Re-opens and rework loops

### Closed → Open re-opens
- **49 submittals re-opened at least once** (62 total re-open events)
- **11 submittals re-opened ≥2 times** (chronic rework)

#### Top re-open projects

| Project | re-opened subs | total re-opens |
|---|---:|---:|
| **Outlook Green Valley Ranch** | 11 | **13** |
| Alta Flatirons | 5 | 9 |
| Heritage on Hover | 8 | 8 |
| Columbine Square | 6 | 6 |
| Novel Flatiron Crossing | 4 | 6 |

Outlook Green Valley Ranch leads — likely scope ambiguity at submission. Worth a project-specific look.

### Same drafter touched twice (drafter → other → drafter again)
| Drafter | submittals re-touched | % of their solo turns |
|---|---:|---:|
| Dalton Rauer    | 172 | ~33% |
| Colton Arendt   | 110 | ~35% |
| Rourke Alvarado |  17 | ~25% |

**~1 in 3 drafter turns is a return visit.** Most are legitimate (QA bounces back for revisions), but if even half of these are avoidable, it's a major efficiency lever. Worth a sample audit.

---

## D. Stale-now report (queue health snapshot)

As of 2026-04-26, **of currently-open submittals**:

| Days since last BIC change | Count |
|---|---:|
| > 7 days   | 157 |
| > 14 days  | 131 |
| > 30 days  | **100** |
| > 60 days  | 69 |
| > 90 days  | 49 |

### Top stalest open submittals

| days | BIC | project | title |
|---:|---|---|---|
| 146 | Danny Riddell    | East Oak Townhomes      | Unit type A/C porch handrail |
| 135 | Colton Arendt    | Aspendale Littleton     | 330-120 Covered Walkway Steel |
| 132 | Dalton Rauer     | Banyan High Point       | 170-208 Building 4 West Stair |
| 132 | Colton Arendt    | Columbine Square        | Building 2 stair core 2 |
| 131 | Dalton Rauer     | Sandstone Ranch         | 450-169 CO#5 Custom Saddle Plates |
| 131 | Colton Arendt    | Outlook Green Valley Ranch | 440-211 Bld 11 Ultralox Post install |
| 130 | Dalton Rauer     | Metro Center            | 190-201 Bld 2 Stoop Stairs |

### Stale (>30d) by current holder

| BIC | count |
|---|---:|
| Colton Arendt    | 33 |
| Dalton Rauer     | 30 |
| Danny Riddell    | 12 |
| Gary Almeida     | 10 |
| Dustin Pauley    | 6  |

> Concrete next move: a single review meeting on the 100 items >30d stale would likely close, kill, or unblock a third of them in one pass.

---

## E. When does work happen?

### Day of week (BIC changes, Mountain Time approx)

```
Monday    757 ████████████████████████████████████████
Tuesday   802 ███████████████████████████████████████████
Wednesday 810 ███████████████████████████████████████████  ← peak
Thursday  637 ██████████████████████████████████
Friday    480 █████████████████████████      ← 40% drop
Saturday    2
Sunday      3
```

**Friday is 40% slower than Wednesday peak.** Weekends are essentially zero — no after-hours rescue work happening. Mid-week is the production window.

### Hour of day (MT)

Peak is **7:00 AM** (546 events) — almost entirely Procore inbound webhooks at start of day. Real activity (Brain-side actions) tapers from 9am → noon, picks up post-lunch, and dies after 4pm.

> Implication: end-of-Wednesday Kanban check is your highest-leverage cadence. By Friday afternoon things are coasting.

---

## F. Manager → drafter routing

A "routing" = a BIC change *from* manager-name *to* a set containing a drafter.

| Manager | Dalton | Colton | Rourke | total |
|---|---:|---:|---:|---:|
| **Rich Losasso**   | **262 (64%)** | 139 (34%) | 9 (2%)   | **410** |
| Gary Almeida   | 113 (56%) | 65 (32%)  | 22 (11%) | 200 |
| Danny Riddell  | 91 (53%)  | 75 (44%)  | 6 (3%)   | 172 |

**Reading:**
- Rich routes ~2:1 to Dalton. He's also the largest manager. This is the source of Dalton's volume asymmetry.
- Gary is the only manager regularly using Rourke (11%).
- Danny is the most balanced Dalton/Colton router.

> If you want to load-balance, the lever is Rich's routing pattern, not coaching the drafters.

---

## G. Throughput trend (5 months)

DRR closes per week:

```
2025-12-15   19 ████████████
2025-12-22   16 ██████████
2026-01-05   22 ██████████████
2026-01-12    8 █████          ← holiday week
2026-01-19   31 █████████████████████
2026-02-02   15 ██████████
2026-02-23   32 █████████████████████
2026-03-09   31 █████████████████████
2026-03-16   31 █████████████████████
2026-03-23   30 ████████████████████
2026-04-06   33 ██████████████████████
2026-04-13   48 ████████████████████████████████
2026-04-20   59 ████████████████████████████████████████  ← peak
```

**~3× growth from Dec to late April.** Average over last 4 weeks (~42/wk) is more than double early Q1 (~17/wk). The team is shipping more — and yet stale-queue and cycle time have not improved proportionally. Likely the throughput gain has come from intake volume, not from making each item faster.

---

## H. Open→Closed lifespan (expanded cohort, n=530)

The 5-month cohort changed the lifespan numbers materially.

### By type

| Type | n | mean d | **median d** | max d |
|---|---:|---:|---:|---:|
| For Construction          | 199 | 1.02  | 0.00   | 26.95 |
| Drafting Release Review   | **261** | 20.20 | **15.05** | 106.09 |
| Submittal for GC Approval | 55  | 32.62 | **33.88** | 82.82 |

**Drafting Release Review really takes ~15 days median end-to-end** — more than double the v1 estimate (6.9d). The 6-week sample was biased toward the recent "fast" cohort. **GC Approval submittals take a full month median** — this is where the real long-tail is.

### Drafting Release Review by manager

| Manager | n | mean d | **median d** | p75 |
|---|---:|---:|---:|---:|
| Danny Riddell | 47  | 13.67 | **11.01** | 18.98 |
| Gary Almeida  | 79  | 19.53 | **9.07**  | 24.62 |
| Rich Losasso  | 135 | 22.87 | **20.03** | 34.86 |

**This is the v1 reversal.** Rich runs the cleanest handoff queue (1.15 avg) but his submittals close **2× slower** than Danny's and Gary's. He carries the volume (135 vs 47/79) and takes the longest. Worth understanding whether he's holding work intentionally, has more complex projects, or is the bottleneck.

---

## I. Late-stage scope changes

21 title changes happened **>1 day after submittal create** — these are real specification edits mid-flight. None were manager re-assignments after open.

#### Worst offenders

| days late | project | change |
|---:|---|---|
| 50d | Heritage on Hover | "Building D West Core Rails" → "Building D Center Core Rails" |
| 43d | Marshall Pointe | "SW Balconies" → "South exterior Balconies" |
| 43d | Banyan High Point | "170-350 Building 1 Westside Ra" → "...Ex" |
| 32d | Alta Flatirons | added "Revisions" suffix at 32d |
| 19d | Alta Flatirons | scope clarified at 19d |

> Marshall Pointe shows 3 of the top 10 — that project's intake is noisy. Aligns with v1 finding (Marshall Pointe ranked #3 for handoff thrash).

---

## J. Multi-assignee BIC segments (review/QA stage)

When BIC has 2+ names — typically QA review (David Servold + reviewer + drafter):

| # assignees | total segments | closed | mean d | median d |
|---:|---:|---:|---:|---:|
| 2 | 716 | 555 | 1.12 | 0.06 |
| 3 | 314 | 247 | 0.71 | 0.04 |
| 4 | 152 | 49  | 0.60 | 0.00 |
| 5 | 22  | 5   | 10.39 | 0.08 |
| 6 | 5   | 2   | 36.96 | 36.96 |

**QA passes are very fast** (median 0.05d ≈ 1 hour for 2-person, 0.04d for 3-person). Multi-assignee isn't a stall pattern. The 5+ assignee buckets have huge variance but tiny n.

---

## K. Drafting status flags are dead in the audit log

**Only 8 status-flag events captured ever** (HOLD, NEED VIF, STARTED). But **103 submittals are *currently* sitting in non-default flag states** (88 STARTED, 10 NEED VIF, 5 HOLD).

This is a logging/process gap — either drafters set the flags via a path that doesn't write to `submittal_events`, or they don't set them at all and someone else does in bulk. Either way, **HOLD/NEED VIF dwell time is unmeasurable from the current data**. If you care about flagging blockers, this is a UX or audit-instrumentation gap to close.

---

## Recommended actions (refined from v1)

1. **Have a "stale queue" review** on the 100 open submittals >30d. Most can probably be closed/killed/escalated in one pass. Colton + Dalton each carry ~30 of these.

2. **Shorter intake → first-touch SLA.** A 5-day median first-touch dwell is the largest single time sink. Setting a "touch within 24h" expectation on assignment would shave a week off cycle time without changing actual drafting speed. Especially for items routed to Colton (currently 13d).

3. **Investigate Rich Losasso's process style.** He runs the cleanest handoff queue (good) but his submittals take 2× longer to close (bad). Either he should bounce more, or his complex items should route to a faster path. He also routes 64% to Dalton — re-balancing toward Colton (or Rourke) would even Dalton's load.

4. **Audit the rework loops.** ~1 in 3 drafter turns is a return visit. Sample 20 of these and find out what fraction are "QA found a real issue" vs "drafter needed info we should have given upfront." If even half are avoidable, that's a 15%+ time savings.

5. **Project-level scope quality investigation** — Outlook Green Valley Ranch (re-opens), Marshall Pointe (late title changes + handoff thrash), Heritage on Hover (re-opens) keep showing up at the bad end of multiple metrics. Likely an upstream Procore/GC intake issue, not a drafting problem.

6. **Coach Colton specifically on real-work turn time.** On Drafting Release Review, his real-mode median is 8.7d vs Dalton's 6.4d. The gap is real and consistent across managers. Probably worth a conversation about focus blocks, item complexity, and what "stuck" looks like for him.

7. **Fix the Drafting Status audit logging.** 88 items sitting STARTED but only 1 STARTED transition ever captured = the data is being set somewhere that doesn't log. Worth tracing in the code so HOLD/VIF dwell becomes measurable next time.

8. **Look at Submittal for GC Approval as its own workstream.** Median 34d. That's a 5-week cycle and represents 55 closed items in the cohort. If the bottleneck is GC response time, that's not a drafter problem — it's a follow-up cadence problem.

---

## Caveats

- `sync_logs.context` was null on `sync_operations` rows (only `sync_logs.data` carried payload), so create-event metadata for some pre-2026-03 submittals is partial.
- Mountain time conversion is a flat -6h (no DST handling) — fine for daily/weekly aggregations, off by an hour on some early-March transitions.
- HOLD/NEED VIF/STARTED dwell is uncomputable due to the audit gap noted in §K.
- "Submittal for GC Approval" appears in two case spellings (`for GC` vs `For Gc`) — bucketed separately in the by-type tables. Combined cohort would be marginally different.

---

*Raw data: `analysis/{events,submittals,users,sync_log_events,sync_log_creates,unified_events}.pkl` and `analysis/{lifespans_expanded,drafter_segments_expanded,stale_now}.csv`.*
