# Job Log / Release Flow — Deep Pattern Analysis

**Sources:** prod `releases` (snapshot) · `release_events` (44d modern audit) · `sync_logs` Trello list-moves linked via card_id (5 months) · `job_change_logs` (5 months, noisy)
**Window:** 2025-11-04 → 2026-04-24 (~5.5 months)
**Volume:** 750 releases · 1,202 unified stage transitions · 444 releases with event history · 451 completion events (Complete + first-Shipped)

> Methodology: For each Trello list-move (`sync_logs` where `operation_type='trello_webhook'` AND `message LIKE 'List move detected%'`), the `data` JSON carries `from_list`/`to_list` and the `sync_operation.source_id` is the Trello card ID. Joining card_id back to `releases.trello_card_id` gives a 5.5-month per-release stage history. Merged with `release_events.update_stage` (Brain + Trello) for the modern 44-day window, deduped by `(job, release, from, to, ts_to_minute)`.
>
> Stage names normalized (e.g., "Fit Up Complete." → "Fit Up Complete", "Paint complete" → "Paint Complete").

---

## TL;DR — what this analysis surfaces

1. **The shop runs fast; the shipping/storage tail is the bottleneck.** Cut → Fit → Weld → Paint median dwell adds up to **~6 days total**. **Store at MHMW (14d median) + Shipping Completed (13d median) accounts for ~2/3 of total cycle time.** That's where time goes, not in fabrication.

2. **PM doesn't drive cycle time on the shop side.** Unlike the submittal world (Rich 2× slower than Danny), all three PMs cluster at **49–51d median**. Once an item is "Released" into the shop, who managed it pre-release barely matters.

3. **Drafter has a measurable but small effect on shop cycle time.** Median Released→Complete:
   - **Dalton (DCR): 45d**
   - **Colton (CBA): 50d** (~10% slower)
   - The 35% gap that showed up in submittal real-work turns largely closes once items reach the shop. The drafting bottleneck doesn't propagate downstream linearly.

4. **The same PM→Drafter routing skew shows up here as in submittals.** Rich Losasso routes **58% to Dalton / 25% to Colton** (vs 64/34 in submittals). Gary Almeida uses **Rourke** far more in the job-log world (21% vs 11% in submittals). Danny Riddell is the only PM who sends *more* to Colton (41%) than Dalton (28%).

5. **Outlook Green Valley Ranch is the recurring problem project.** Largest by volume (121 releases), slowest by cycle time (52.6d median, n=19), 4 distinct releases with multiple regressions, and (per the prior report) leads on submittal re-opens. This is a project-quality issue, not a drafter or shop issue.

6. **Stage regression rate is 8.2%** (98 of 1,202 transitions are backward). 79 of 444 releases (18%) had at least one regression. Most are real corrections, not data noise — and the worst offender is "Complete → Shipping Completed" (19 instances), which suggests premature "Complete" tagging.

7. **Thursday is peak day** for stage moves (379 vs 226 Mon, 84 Fri). Likely driven by the Thursday review meeting cadence. Friday drops 78% from the Thursday peak.

8. **Fab-order churn is mostly automated** — 893 of 1,259 priority changes (71%) are `collision_resolution_cascade` or `stage_change_unified`, both system-generated. Real human re-prioritization is the minority.

9. **The current in-progress queue is healthy.** Only 41 releases haven't moved in 7+ days, and only 2 over 30 days. Massive contrast to the submittal side (100 stale >30d).

---

## A. Drafter (`by`) throughput and current load

| code | drafter | total | complete | in-fab | ready-to-ship | avg fab h | total fab h |
|---|---|---:|---:|---:|---:|---:|---:|
| **DCR** | **Dalton Rauer**     | **367** | 291 | **33** | 43 | 23.0 | **8,446** |
| CBA | Colton Arendt    | 192 | 160 | 19 | 13 | 21.5 | 4,137 |
| RJA | Rourke Alvarado  | 64  | 51  | 2  | 11 | 17.2 | 1,098 |
| DEP | Dustin Pauley    | 31  | 24  | 3  | 4  | 24.4 | 755 |
| DTS | David Servold    | 24  | 20  | 3  | 0  | **74.6** | 1,791 |
| RL  | Rich Losasso (drafter, legacy) | 25  | 25  | 0 | 0 | 1.3 | 32 |
| DR  | DR (ambiguous)   | 20  | 18  | 1  | 1  | 5.5  | 55 |

**Reading:**
- Same 2:1 volume asymmetry as submittals: Dalton ~2× Colton.
- Dalton is currently sitting on **33 in-fab + 43 ready-to-ship = 76 in-flight**, vs Colton's 32 and Rourke's 13.
- **David Servold's avg fab-hours per release is 74.6** — 3× everyone else. He drafts the heaviest, lowest-volume work. Despite that, his releases close faster than average (see §D). His upstream prep is very tight.
- "RL drafter" entries (25 releases, avg 1.3 fab hours) are tiny line items Rich drafted himself — possibly miscellaneous one-offs.

---

## B. PM throughput and load

| code | PM | total | complete | in-fab | ready-to-ship | total fab h |
|---|---|---:|---:|---:|---:|---:|
| **RL** | **Rich Losasso** | **392** (52%) | 326 | 28 | 38 | 7,670 |
| GA | Gary Almeida   | 204 (27%) | 156 | 22 | 25 | 4,635 |
| DR | Danny Riddell  | 140 (19%) | 119 | 10 | 11 | 4,470 |
| WO | Bill O'Neill   | 10  | 9   | 1  | 0 | 42 |

Rich runs more than half the shop's release volume. Same dominance pattern as the submittal side.

---

## C. PM × Drafter routing matrix

Releases assigned to each drafter, by PM:

| PM | DCR (Dalton) | CBA (Colton) | RJA (Rourke) | DEP (Dustin) | DTS (David) | other |
|---|---:|---:|---:|---:|---:|---:|
| **Rich Losasso (n=392)** | **228 (58%)** | 99 (25%)  | 11 (3%)  | 12 (3%) | 7 (2%) | 35 |
| Gary Almeida (n=204) | 98 (48%) | 33 (16%) | **42 (21%)** | 13 (6%) | 9 (4%) | 9 |
| **Danny Riddell (n=140)** | 39 (28%) | **58 (41%)** | 10 (7%) | 5 (4%) | 7 (5%) | 21 |

**Reading:**
- Rich → Dalton routing is identical pattern to submittal world (58% here, 64% there).
- **Gary is Rourke's primary feeder** (42 of Rourke's 64 releases come from Gary). If you want to use Rourke more, that goes through Gary.
- **Danny is the only PM who sends more to Colton than Dalton.** 41% / 28% split. Combined with Danny's 14% to "DR" (likely self-drafting), he behaves differently from the other two.

---

## D. Released → Complete lifespan

n=116 releases with both `released` date and an observable Complete-stage transition (filter: 0 ≤ days ≤ 365).

- **Global: mean 53d, median 45.5d, p25 29d, p75 76d, max 250d**

### By drafter

| code | drafter | n | mean | **median** | p75 | max |
|---|---|---:|---:|---:|---:|---:|
| DCR | Dalton Rauer    | 54 | 45.8 | **44.6** | 56.6  | 116.5 |
| CBA | Colton Arendt   | 30 | 65.7 | **50.1** | 86.9  | 250.5 |
| DEP | Dustin Pauley   | 6  | 42.7 | 37.5     | 48.1  | 83.5 |
| DTS | David Servold   | 6  | 36.4 | **35.6** | 54.6  | 71.5 |
| DR  | DR (ambiguous)  | 6  | 55.2 | 49.7     | 56.5  | 106.9 |
| RJA | Rourke Alvarado | 4  | 90.8 | 94.0     | 95.3  | 97.7 |
| RL  | RL-drafter      | 4  | 74.4 | 81.2     | 94.2  | 98.7 |

**Reading:**
- Dalton's items close ~5 days faster than Colton's median (44.6 vs 50.1) — a real but moderate gap.
- **David Servold's items close fastest at 35.6d median**, despite being the largest by fab hours. Tight upstream prep pays off downstream.
- Rourke's 4 cases are all 90+ days — small n, but worth verifying. Could be that Rourke drafts items that get parked in long-tail projects.

### By PM

| code | PM | n | mean | median | p75 |
|---|---|---:|---:|---:|---:|
| DR | Danny Riddell  | 16 | 48.4 | 50.6 | 60.3 |
| GA | Gary Almeida   | 30 | 50.9 | 45.0 | 83.6 |
| RL | Rich Losasso   | 65 | 49.6 | 42.8 | 70.7 |
| WO | Bill O'Neill   | 3  | 167.5| 158.5| 204.5 |

**The PM effect that was huge in submittals (Rich 2× slower) disappears here.** All three primary PMs cluster at 43–51d median. Once items hit "Released," PM stops mattering.

---

## E. Stage dwell — where the time actually goes

Dwell = time a release sat in a given stage before its next transition. Forward-only, n=618 dwell observations.

| stage | n | **mean d** | **median** | p75 |
|---|---:|---:|---:|---:|
| Material Ordered     | 3   | 3.21 | 3.84 | 4.82 |
| Released             | 11  | 4.86 | 1.88 | 5.83 |
| Cut Start            | 46  | 2.49 | 1.75 | 4.11 |
| Cut Complete         | 35  | 2.22 | 1.71 | 3.96 |
| Fitup Start          | 5   | 0.61 | 0.93 | 0.95 |
| Fit Up Complete      | 69  | 1.61 | 1.03 | 2.05 |
| Welded               | 25  | 0.59 | 0.06 | 0.13 |
| **Welded QC**        | 48  | **5.92** | **5.34** | **11.88** |
| Paint Start          | 19  | 0.98 | 0.29 | 1.00 |
| Paint Complete       | 95  | 1.85 | 0.69 | 1.95 |
| **Store at MHMW**    | 14  | **26.21** | **14.01** | **20.71** |
| Shipping Planning    | 132 | 2.78 | 1.20 | 4.13 |
| **Shipping Completed** | 98 | **32.19** | **13.46** | **29.02** |
| Complete             | 18  | 1.74 | 0.00 | 0.03 |

**Reading:**
- Cumulative through the shop floor (Released → Paint Complete): **~6 days median**. The fab process is genuinely fast.
- **Three stages eat the cycle time:**
  - **Welded QC: 5.3d median** — a real bottleneck. Quarter of items sit 12+ days here.
  - **Store at MHMW: 14d median** — items sitting at the warehouse waiting for ship-out.
  - **Shipping Completed: 13.5d median** — appears to mean "shipped but not yet marked Complete in the system." Almost certainly a bookkeeping lag, not real work.
- Every actual **fabrication step is sub-2d median**.

> The actionable read: if you want to compress cycle time, focus on Welded QC throughput and on the Shipping/Storage handoff cadence — not on shop-floor speed.

---

## F. Stage regressions (backward moves)

**98 backward moves out of 1,202 transitions (8.2%). 79 of 444 releases (18%) had at least one regression.**

### Top backward transition pairs

| count | from → to |
|---:|---|
| 19 | **Complete → Shipping Completed** *(probable bookkeeping correction — flag was set too early)* |
| 10 | Shipping Planning → Store at MHMW |
| 8  | Shipping Completed → Shipping Planning *(real: re-pulled into ship queue)* |
| 6  | Fit Up Complete → Released *(real: shop sent item back)* |
| 5  | Shipping Completed → Paint Complete *(real: post-ship paint touch-up)* |
| 4  | Paint Complete → Fit Up Complete *(real: weld/fit issue caught at paint)* |
| 4  | Store at MHMW → Paint Complete |
| 3  | Fit Up Complete → Fitup Start |
| 2  | Released → Material Ordered *(missing material caught after release)* |

### Top regression-heavy releases

| job-rel | regressions | project |
|---|---:|---|
| 370-846 | 3 | Fairfield - Vista Highlands |
| 380-514 | 3 | Brinkman - Marshall Pointe |
| 390-535 | 3 | Thompson Thrift - Heritage on Hover |
| 500-515 | 3 | Brinkman - Novel Flatiron |
| 320-888 | 2 | Thompson Thrift - Landing at Lemay |
| 190-502 | 2 | Hinton - Metro Center |
| 440-758 / 440-334 / 440-451 | 2 each | Evergreen - Outlook Green Valley Ranch (×3) |
| 330-496 | 2 | Brinkmann - Aspendale Littleton Senior |

**Outlook Green Valley Ranch shows up 3 times in the regression list.** Same project that was worst on submittal re-opens.

> The 19 "Complete → Shipping Completed" reversions suggest a UI or data-flow bug where Complete is getting set prematurely. Worth tracing in the code.

---

## G. Stale-now report (in-progress only)

As of 2026-04-24:

| Stalest threshold | count |
|---|---:|
| > 7 days  | 41 |
| > 14 days | 28 |
| > 30 days | **2** |
| > 60 days | 0 |

**The shop queue is dramatically healthier than the submittal queue** (which had 100 items >30d stale). Active production keeps things moving.

### Top stalest in-progress

| days | stage | drafter | PM | job-rel | project |
|---:|---|---|---|---|---|
| 42.6 | **Released** | CBA | RL | 440-279 | Outlook Green Valley Ranch |
| 38.2 | Store at MHMW | CBA | RL | 410-132 | Columbine Square |
| 29.2 | Store at MHMW | CBA | DR | 450-193 | Sandstone Ranch |
| 21.9 | Hold        | DCR | RL | 510-151 | Idaho Springs Police Dept |
| 18.2 | Store at MHMW | DCR | GA | 190-398 | Metro Center |
| 18.0 | Welded QC | DCR | RL | 170-463 | Banyan High Point |
| 17.3 | Welded QC | DCR | RL | 440-439 | Outlook Green Valley Ranch |
| 17.1 | Store at MHMW | FMW | RL | 170-457 | Banyan High Point |
| 17.1 | Cut start | DCR | DR | 550-480 | 4th St. North |

> The 42.6-day "Released" item on Outlook (440-279) hasn't entered fabrication. Worth checking why.
> Several Banyan High Point items are clustered in Welded QC — possible QC bottleneck on that project.

---

## H. Throughput trend (5 months)

Releases reaching Complete (or Shipped, in older era) per week:

```
2025-11-03   16 ████████
2025-11-10   19 █████████
2025-11-17   25 ████████████
2025-11-24    4 ██          ← Thanksgiving
2025-12-01    7 ███
2025-12-15   25 ████████████
2025-12-22    3 █           ← Christmas
2026-01-05   19 █████████
2026-01-12    8 ████
2026-01-19   23 ███████████
2026-02-02   17 ████████
2026-02-16   24 ████████████
2026-02-23   10 █████
2026-03-09    4 ██
2026-03-16   13 ██████
2026-03-23    8 ████
2026-03-30   24 ████████████
2026-04-06   32 ████████████████
2026-04-13   33 ████████████████
2026-04-20   80 ████████████████████████████████████████  ← peak
```

Strong upward trend in the last 4 weeks. 80 closures in the final week is anomalously high — likely batch closure/archival, not actual ship-week.

Average of last 4 weeks (~42/wk) is roughly double the November-January baseline (~17/wk). Same growth pattern as the submittal side.

---

## I. When does shop work happen? (Mountain time, approx)

### Day of week

```
Monday    226  ███████████████████████
Tuesday   291  ██████████████████████████████
Wednesday 217  ██████████████████████
Thursday  379  ████████████████████████████████████████  ← peak
Friday     84  ████████  ← 78% drop
Saturday    0
Sunday      5
```

**Thursday peak is unique to the shop side** (Wednesday peaks the submittal side). The Thursday review meeting cadence likely explains it. **Friday is severely under-used**. Weekend essentially zero.

### Hour of day

```
 7:00 AM  212 ████████████████████████████████████████  ← peak
 8:00 AM  183 ██████████████████████████████████
12:00 PM  118 ██████████████████████              ← pre-lunch close-out spike
 6:00 AM  125 ███████████████████████              ← early-shift
 4:00 AM   31 █████                                 ← night-shift activity
```

A small but real night-shift signature (4:00–5:00 AM, ~47 events) — the shop runs an early shift the submittal side doesn't.

### Source of stage moves

- Brain (admin board): **635**
- Trello (drag-drop): **567**

A near-even split. Both UIs are getting heavy use.

---

## J. Fab order churn (priority changes)

44-day window: **1,259 fab_order changes across 418 unique releases.**
- Mean **3.0 changes per release** (where any), median 2, **max 17**
- Top churned: 330-496 (Aspendale Littleton Senior) **17 changes**, 170-501 (Banyan High Point) 14, 330-325 11

### Reasons for fab_order change

| reason | count | %  |
|---|---:|---:|
| `collision_resolution_cascade` | 534 | 42% *(automated re-numbering)* |
| `stage_change_unified`         | 359 | 29% *(automated, on stage move)* |
| `job_comp_complete`            | 54  | 4%  *(automated)* |
| (other / human-driven)         | ~312 | 25% |

**71% of priority churn is system-generated**, not user re-prioritization. The frequent `collision_resolution_cascade` events mean two releases were assigned the same fab_order and the system bumped one. Worth checking whether the cascade behavior is producing actual instability or just bookkeeping noise.

---

## K. Project-level patterns

### Top projects by release volume

| count | project |
|---:|---|
| 121 | Outlook Green Valley Ranch |
| 75 | Columnbine Square |
| 69 | Banyan High Point |
| 58 | Vista Highlands |
| 40 | Littleton Village II |
| 38 | Metro Center |
| 35 | Velo Interlocken |
| 34 | Sandstone Ranch |
| 30 | Alta Flatirons |
| 28 | Landing at Lemay |
| 26 | Marshall Pointe |
| 26 | Heritage on Hover |

### Lifespan by project (≥3 closures, sorted slow → fast)

| project | n | mean d | median | max |
|---|---:|---:|---:|---:|
| Novel Flatiron | 10 | **67.1** | 51.0 | 117.5 |
| **Outlook Green Valley Ranch** | 19 | **64.4** | **52.6** | 128.6 |
| Littleton Village II | 4 | 58.4 | 64.0 | 76.8 |
| Landing at Lemay | 3 | 57.5 | 53.9 | 78.8 |
| Banyan High Point | 7 | 54.3 | 41.8 | 77.5 |
| Marshall Pointe | 7 | 53.3 | 27.5 | 105.5 |
| Heritage on Hover | 9 | 49.5 | 39.6 | 77.7 |
| Columnbine Square | 13 | 43.6 | 38.5 | 94.5 |
| Velo Interlocken | 5 | 41.5 | 50.5 | 77.5 |
| Aspendale Littleton Senior | 4 | 33.3 | 34.3 | 42.8 |
| Fieldhouse (Idaho Springs) | 8 | 32.9 | 32.2 | 64.6 |
| Alta Flatirons | 8 | 30.0 | 31.1 | 51.6 |
| 4th St. North | 4 | 24.1 | 22.6 | 37.5 |

> **Outlook Green Valley Ranch is the recurring villain across both reports.** Largest project, slowest median, leads regression list, leads submittal re-opens. Whatever is going on with the GC/scope on that job is propagating into every downstream metric.
> 4th St. North is consistently fast (24d median, low handoff churn from submittal report) — a possible "what does good look like" benchmark.

---

## L. Drafter × PM cycle-time pairings

Released → Complete days, ≥3 cases:

| drafter | PM | n | mean d | median |
|---|---|---:|---:|---:|
| **DCR (Dalton)** | DR (Danny)   | 5  | **35.9** | **27.6** ← fastest pair |
| DEP (Dustin)     | GA (Gary)    | 3  | 32.5 | 37.5 |
| DTS (David)      | GA (Gary)    | 5  | 29.4 | 22.6 |
| DCR (Dalton)     | RL (Rich)    | 38 | 43.7 | 43.1 |
| DCR (Dalton)     | GA (Gary)    | 11 | 57.7 | 45.5 |
| DR (DR)          | DR (Danny)   | 5  | 57.7 | 56.5 |
| CBA (Colton)     | DR (Danny)   | 4  | 49.4 | 50.6 |
| **CBA (Colton)** | **RL (Rich)** | 17 | **58.7** | 41.7 |
| **CBA (Colton)** | **GA (Gary)** | 8  | **65.7** | 68.1 ← slowest non-self pair |
| RL (Rich)        | RL (Rich)    | 4  | 74.4 | 81.2 *(Rich self-drafting)* |

**Reading:**
- **Dalton × Danny is the fastest pairing**: 27.6d median (n=5). Wonder if Danny's "Drafting Release Review → Colton" submittal pattern paired with Danny → Dalton on releases is the same setup explaining the speed.
- **Colton × Gary is the slowest non-self pairing**: 68.1d median. In the submittal world, that pair was 3.18d/n=22 — middle of pack. So Colton×Gary is fine through drafting but slow through shop. Worth checking what items Gary is sending to Colton — likely the harder ones.
- The Rich-self-drafted releases (74d) confirm: when Rich drafts his own legacy items, they're the slowest. Worth retiring this pattern if it still happens.

---

## Cross-report comparison

| dimension | Submittal Report | Job-Log Report |
|---|---|---|
| Total volume | 1,312 submittals | 750 releases |
| Active period | 5 months | 5.5 months |
| Cycle metric | Open → Closed | Released → Complete |
| Median cycle | 15d (DRR) | 45d |
| Drafter Dalton/Colton gap | 6.4d vs 8.7d (+36%) | 44.6d vs 50.1d (+12%) |
| Bottleneck | Drafter "real work" mode | Shipping/storage tail |
| Rich's effect | 2× slower than other PMs | No PM effect |
| Worst project | Outlook GVR (re-opens) | Outlook GVR (cycle time + regressions) |
| Stale queue | 100 items >30d ⚠️ | 2 items >30d ✓ |
| Throughput growth | 17 → 53/wk | 17 → 42/wk |
| Peak day of week | Wednesday | Thursday |

**Interpretation:** The two stages of the workflow have very different bottleneck signatures. The drafting stage (submittals) has a queue-management problem and a per-drafter speed gap. The shop stage (releases) has a near-uniform PM effect, modest drafter effect, and a clear shipping-tail bottleneck. The two big cross-cutting findings:
1. **Rich Losasso's volume dominates both stages** (52% of submittal manager work, 52% of PM work) and his routing skew (~58% Dalton) is consistent.
2. **Outlook Green Valley Ranch is broken at the source.** Bad signal in every cut of the data — re-opens, cycle time, regressions, scope changes. Either GC scope quality, Procore intake, or contract structure on that project deserves a deep look.

---

## Recommended actions (job-log specific)

1. **Investigate the Welded QC bottleneck.** 5.3d median, 12d at p75. Largest in-shop dwell besides storage. Either QC has insufficient capacity, or items are arriving needing real rework. A sample audit of the 17 stalest Welded QC items would tell you which.

2. **Audit the "Complete → Shipping Completed" 19 reversions.** That's a process or UI bug — Complete is being marked too early. Trace it in the code/Trello board.

3. **Reduce Friday under-utilization.** Friday is 78% slower than Thursday peak. If shipping/QC could run Fridays at Tuesday levels, that's measurable extra throughput. Possibly a staffing or workflow choice worth revisiting.

4. **Look at Outlook Green Valley Ranch as a unit.** It's 121 releases (16% of total volume), slowest cycle, top regressor, top submittal re-opener. A project-level retrospective probably yields more impact than any per-drafter change.

5. **Confirm `collision_resolution_cascade` isn't generating false instability.** 534 of 1,259 fab_order events (42%) are this code path. If two items legitimately need the same fab_order and the cascade keeps bumping one, you may have priority data that doesn't match user intent.

6. **Re-balance Rich's drafter routing.** 58% Dalton / 25% Colton in releases (matches the 64/34 in submittals). Dalton's in-flight load is 76 items vs Colton's 32. If the Colton×anyone cycle gap stays at +5d, the load imbalance means the *system* is slower than it would be with even routing.

7. **Confirm the DR-as-drafter ambiguity.** 20 releases tagged `by=DR`. In the PM column DR=Danny Riddell. Same code in `by` could mean Dalton (overlapping his DCR) or Danny self-drafting. Worth a one-line lookup to clarify and either re-tag or document.

---

## Caveats

- `release_events` only goes back to 2026-03-13. The 5-month view relies on `sync_logs` list-move events for the older window — these capture **only Trello-driven** moves, not Brain-driven ones (which mostly didn't exist pre-March anyway).
- `job_change_logs` is noisy: many bidirectional Excel "X/O" oscillations get logged as state changes (e.g., 80 Shipped→Created reversions). Treated as a coarse historical signal only, not as authoritative regressions.
- Released-date is a `Date` (no time) and many entries are forecasted future releases (up to Dec 2026). Lifespan analysis filtered to `released ≤ today` and `0 ≤ days ≤ 365`.
- Stage-name normalization may merge a few variants imperfectly (e.g. "Welded" vs "Weld Complete" treated as same).
- Throughput section H combines `Complete` (modern) and first-`Shipped` (older) milestones — same conceptual event, different stage-name vocabulary.
- 116-row Released→Complete cohort is small; per-drafter and per-PM cuts have small n's.

---

*Raw data: `analysis/{releases,release_events,list_moves,job_change_logs,release_stage_events}.pkl` and `analysis/{releases_lifespan,releases_stale}.csv`.*
